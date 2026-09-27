# ARCHITECTURE

How the system is shaped and why. The models are in `DATA_MODEL.md`, the analytics pipeline in
`ANALYTICS.md`, the security controls in `SECURITY.md`, and hosting in `DEPLOYMENT.md`.

## 1. System

```
Visitor
  → Cloudflare      DNS · TLS (Full strict) · WAF · rate-limit rule · Turnstile · cache for static/media
  → Railway         web:  gunicorn + Django 6.1 + WhiteNoise
                    db:   PostgreSQL (private network only)
                    cron: manage.py maintenance (every 10 min)
  → Cloudflare R2   media.odilbek.me (uploads, resume PDFs) · private bucket (DB backups)
  → Telegram        Bot API, outbound only, server-side
```

It is **one Django monolith**: no microservices, task queue or Redis in the MVP (D-022), and no
public API. HTMX endpoints return HTML fragments; DRF is added only when a real API consumer
exists (D-004).

## 2. Conceptual model

```
                ┌───────────────────────── master data (career) ─────────────────────────┐
                │ Skill · Project · Experience · Education · Service · LanguagePair · …  │
                └────────────────────────────────▲───────────────────────────────────────┘
                              ordered link tables with per-view overrides
                   ┌─────────────────────────────┴─────────────────────────────┐
          Profiles (website views)                                  Resumes (paper views)
   home · about · developer · translator · …            curated selections per profile, per language
```

- **Master data is what is true.** A project, job or skill exists exactly once.
- **Views decide what to show whom.** A profile or resume links to master items in an order,
  optionally overriding their text for that view. Hiding an item from one profile never
  affects another.
- **Home and About are Profiles** (`kind=home`, `kind=about`), so the section system, SEO and
  analytics are reused rather than duplicated as special pages (D-011).
- **Profiles are data.** A new profile needs no code; a new *kind* of section or hero
  treatment does.

## 3. Django apps

| App | Owns | May depend on |
|---|---|---|
| `core` | abstract bases, `SiteSettings`, `MediaAsset` + image pipeline, Markdown renderer, reserved slugs, middleware, SEO helpers, template tags, `predeploy` / `maintenance` commands | — |
| `accounts` | custom `User`, allauth adapters, MFA enforcement | core |
| `career` | master data + public project/skill views | core |
| `profiles` | `Profile`, `ProfileSection`, profile link tables, page assembly, career-graph builder, public profile views | core, career |
| `resumes` | `Resume`, resume link tables, `ResumeFile`, rendering, PDF, public download | core, career, profiles |
| `analytics` | `Event`, `DailySalt`, `Source`, `Campaign`, beacon ingest, attribution, reports | core, career, profiles, resumes |
| `contact` | `ContactMessage`, form variants, spam checks, notifiers | core, profiles, analytics |
| `blog` | `Post`, `Tag` (Phase 13) | core, profiles |
| `dashboard` | the CMS: views, forms, templates. **No models** | everything |

**Dependency direction is one-way.** Nothing depends on `dashboard`. `career` must not import
from `profiles` (see the open question on `Project.primary_profile` in `DATA_MODEL.md`).

**Planned repository layout** (created from Phase 1; do not create early):

```
config/settings/{base,dev,test,prod}.py   config/urls.py   config/wsgi.py
apps/<app>/{models,selectors,services,views,urls,forms,admin,translation}.py
templates/{base.html, components/, public/, dashboard/, resume/}
static/{css/app.css, js/, vendor/, fonts/}   locale/{ko,uz}/
```

## 4. Layering rules

- **Views are thin.** They validate input, call a selector or service, and render.
- **Reads go through `selectors.py`.** Public views and templates obtain content **only** through
  selectors, and selectors build on each model's `QuerySet.public()`. That method encodes the
  visibility rules (published, listed, and selected for the profile in question). No public view
  touches a model manager directly. This makes visibility **structural**: a draft cannot leak
  because a developer forgot a filter.
- **Writes go through `services.py`.** Examples: reordering, copying a profile's selection into
  a resume, generating a PDF, recording an event, notifying.
- **Draft preview** is the only exception to `public()`. A selector accepts `include_drafts=True`,
  which a view may pass **only after** verifying a staff user and `?preview=1`. Such responses
  carry `Cache-Control: no-store`.
- **No profile-specific logic** anywhere (Python, templates, CSS, JS). Differences between
  profiles are fields: hero variant, accent, contact form variant, section configuration.

## 5. Frontend

- **Django templates** with Django 6 template partials (`{% partialdef %}`), so one template
  renders both a full page and its HTMX fragments.
- **Tailwind v4** with CSS-first `@theme` tokens, built by the standalone CLI (D-010). **Never
  build class names from database values.** Per-profile accents use `data-accent` and CSS variables.
- **HTMX** for the dashboard and a few public interactions (project filters, contact form
  variants). Set `htmx.config.allowEval = false` and `includeIndicatorStyles = false`.
- **Alpine.js, CSP build**, for small state (menus, tabs, bottom sheets), with components
  registered via `Alpine.data()` in static files.
- **Vanilla JS modules:** `track.js` (analytics beacon, ~1 KB), `theme.js`, `switcher.js`,
  `map.js` (career map), `dashboard.js`.
- **Vendored, pinned, self-hosted** third-party JS (`static/vendor/`): htmx, Alpine CSP,
  SortableJS. No CDNs.
- **Static files** are served by WhiteNoise with hashed, compressed filenames and cached by Cloudflare.

## 6. Dashboard

- A custom `/dashboard/` for staff only (D-018). Django admin stays at a secret path
  (`DJANGO_ADMIN_PATH`) as a back-office; its login redirects to allauth.
- **Plain class-based views** per entity (List/Create/Update/Delete) plus a few small mixins:
  `StaffRequired`, `HtmxPartial`, `Reorder`, `TogglePublish`. **This is not a generic CMS
  framework or page builder.**
- **Forms:**
  - ModelForms with **language tabs** (EN required; KO/UZ optional)
  - a live Markdown preview (HTMX)
  - character counters with recommended lengths, to keep project pages short
- **Ordering:** SortableJS drag-and-drop posts the ordered ids; the `Reorder` mixin saves them
  with `bulk_update`. Every sortable list also has keyboard-accessible ↑/↓ buttons.
- **Item pickers** attach master items to a profile or resume (search as you type), with order,
  featured flag and override fields.
- **Settings** shows each integration as configured or not (Telegram, Turnstile, R2) and offers
  a "send test notification" action. **Secret values are never displayed.**

## 7. Multilingual

- **Languages:** `en` (default, **no URL prefix**), `ko` (`/ko/…`), `uz` (`/uz/…`, Latin), via
  `i18n_patterns(prefix_default_language=False)` (D-013, D-014).
- **Content:** django-modeltranslation columns (`field_en/_ko/_uz`) with fallback to English.
  Only `_en` is required (D-015).
- **UI strings:** gettext `.po` files in `locale/`. The dashboard UI is English-only (D-028).
- **Slugs are not translated.** URLs differ only by prefix, which keeps hreflang simple.
- **Per-profile availability:** `Profile.languages` lists the languages a profile is published
  in. The language switcher offers only those, and requesting another redirects (302) to English.
- **No automatic redirect by `Accept-Language`**, because it breaks crawlers and shared links.
  Instead a subtle notice offers the visitor's language when a version exists.
- **Blog exception:** one `Post` row per language, linked by `translation_group`.
- **Korean typography** (`word-break: keep-all`, taller line-height) is specified in `DESIGN.md`.

## 8. Authentication

- A custom `accounts.User` from the first migration. Code uses `get_user_model()` /
  `settings.AUTH_USER_MODEL`, never `auth.User`.
- **django-allauth** (D-027):
  - password login and **TOTP MFA** with recovery codes, required for staff in production
  - Google login in Phase 12
  - **signup closed** (`is_open_for_signup → False`); Google may only log into an existing staff
    user whose email is in `DASHBOARD_ALLOWED_EMAILS`
- **Login protection:** allauth's login-failure rate limits (cache-backed) and a Cloudflare
  rate-limit rule on `/accounts/login/`.
- **Passwords and cookies:** Argon2 password hashing. Session cookies are Secure, HttpOnly,
  SameSite=Lax and **host-only**, so they are never sent to `media.odilbek.me`.
- **No outgoing email in the MVP.** Password reset uses `manage.py changepassword` or Google login.

## 9. Contact and notifications

1. **Form variants.** `/contact/?for=<profile>` renders the variant set on that profile
   (`contact_form_variant`). The code knows variants, not profiles:
   - `general`
   - `project_inquiry`: type, timeline, budget range
   - `language_request`: language pair, mode, date, location, volume
2. **Defences:**
   - CSRF, length caps, email validation, control-character stripping
   - a honeypot and a signed time-to-submit token (≥ 3 s)
   - Cloudflare **Turnstile**, verified server-side
   - a rate limit of 5 per hour per IP
   - suspicious submissions are stored as `status=spam`, never silently dropped
3. **Storage.** A `ContactMessage` records the profile, variant `details` (JSON validated by the
   variant's form), language, campaign, source and visitor hash.
4. **Notification (outbox).** After commit, the configured notifier sends. `TelegramNotifier`
   calls `sendMessage` with a 5 s timeout, HTML-escaped content and a link to the dashboard
   message, then records `notified_at` or `notify_error`. The `maintenance` command retries
   unsent messages, so a Telegram outage never loses a lead or breaks the form.
5. **Secrets.** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` exist only as server environment
   variables. `NullNotifier` runs in development and tests.

## 10. Resumes

- **One public URL per profile:** `/resume/<profile>.pdf` serves the profile's **default**
  resume, whether uploaded or generated (D-019). `/resume/<profile>/` is the HTML version.
- **Uploaded:** a validated PDF per language, stored as `ResumeFile(origin=uploaded)`.
- **Generated:** the resume's own curated selection (D-020), with overrides on each row and at
  resume level.
  - `resumes/services.py` builds a plain context dict from the selection, master data and
    `SiteSettings`.
  - One template (`templates/resume/<template>.html` plus print CSS with `@page` and embedded
    fonts) renders the dashboard's live preview (iframe), the public HTML resume, and the PDF
    via **WeasyPrint** (D-021).
  - Generated PDFs are stored as `ResumeFile(origin=generated, language)`.
- **Staleness:** `data_hash = sha256(serialized context + template version)`. The dashboard
  compares it with the current data and shows "Outdated · Regenerate". No signals are needed.
- **Download:**
  - picks the current file for the request language, falling back to English (404 if none)
  - records `resume_download`
  - 302-redirects to the media URL, with `no-store` on the redirect so every download is counted
    while the file itself is CDN-cached
  - uses a friendly filename, e.g. `Odilbek-Shavkatov-Backend-Developer-CV-EN.pdf`
- **PDF generation is a staff action only.** A public request never renders a PDF.

## 11. Background work

There is no queue. A single command, `manage.py maintenance`, runs on a Railway cron schedule
(every 10 min) and performs whatever work is due:

- retry unsent contact notifications (every run)
- delete past analytics salts and expired events (daily)
- `pg_dump` to the private R2 bucket (nightly)

Each job records when it last ran, so running it more often is harmless.

## 12. URL architecture

**Public** (inside `i18n_patterns`: unprefixed is English, then `/ko/…` and `/uz/…`)

| Route | Purpose |
|---|---|
| `/` | Home: introduction and "where should we start?" router (`kind=home` profile) |
| `/about/` | The whole person (`kind=about` profile) |
| `/<profile-slug>/` | Role profiles: `/developer/`, `/translator/`, later `/ai-automation/` |
| `/projects/` | Listed projects, with HTMX filters `?profile=` and `?skill=` |
| `/projects/<slug>/` | Project detail. An unlisted project is reachable here only, `noindex` |
| `/skills/<slug>/` | Skill evidence page (the no-JS target for career map nodes) |
| `/map/` | Career map (Phase 11) |
| `/resume/<profile-slug>/` | HTML resume |
| `/resume/<profile-slug>.pdf` | PDF in the current language (EN fallback), counted server-side |
| `/contact/` | Contact form and channels; `?for=<profile-slug>` selects the variant |
| `/privacy/` | What the site collects, in plain words |
| `/blog/…` | Phase 13 |

**Outside `i18n_patterns`:** `/e/` (analytics beacon, POST only), `/sitemap.xml`, `/robots.txt`,
`/.well-known/security.txt`, `/healthz/`, `/accounts/…` (allauth), `/<DJANGO_ADMIN_PATH>/`,
`/dashboard/…`.

**Reserved profile slugs.** Language codes and every top-level route segment are rejected by the
profile slug validator:

```
en ko uz about projects skills map resume contact privacy blog dashboard accounts admin
e api static media healthz sitemap.xml robots.txt .well-known _styleguide
```

A test fails when a top-level route exists that is not on this list.

**Canonical URLs** drop `ref` and `utm_*`. The beacon also removes them from the address bar
(`history.replaceState`), so a shared link does not carry someone else's attribution.

**Dashboard** (English UI, not language-prefixed)

```
/dashboard/                                overview: KPIs, new messages, stale resumes, drafts, missing translations
/dashboard/profiles/[new|<id>/]            tabs: Hero · Sections · Content · Contact · SEO
/dashboard/profiles/<id>/sections/         order, enable, configure
/dashboard/profiles/<id>/items/<kind>/     pick, order, feature, override
/dashboard/{projects,experience,education,skills,services,language-pairs,channels,media}/
/dashboard/resumes/[<id>/[preview|generate]/]   and uploads
/dashboard/analytics/                      overview · profiles · projects · sources · funnel
/dashboard/campaigns/[new|<id>/]           link builder · per-campaign report
/dashboard/messages/[<id>/]                inbox
/dashboard/translations/                   completeness matrix
/dashboard/settings/                       identity, availability, SEO defaults, integration status
```

## 13. Planned dependencies

Each dependency needs a reason. Adding one that isn't listed needs a line of justification, and
an entry in `DECISIONS.md` if it is architectural.

| Package | Why |
|---|---|
| django 6.1, psycopg[binary], gunicorn | core |
| django-environ | environment-driven settings, `DATABASE_URL` parsing |
| whitenoise | hashed, compressed static files without nginx |
| django-htmx | `request.htmx`, partial rendering |
| django-tailwind-cli | Tailwind v4 standalone binary, so there is no Node |
| django-modeltranslation | field-level translations |
| django-allauth[mfa,socialaccount], argon2-cffi | login, MFA, Google, rate limits, password hashing |
| django-storages[s3] | R2 media storage |
| Pillow | image validation, re-encoding, variants |
| markdown-it-py, nh3 | Markdown rendering, HTML sanitization |
| weasyprint | HTML/CSS → PDF |
| httpx | Telegram and Turnstile calls with timeouts |
| django-ratelimit | rate limits on contact and the beacon |
| *dev:* pytest, pytest-django, factory-boy, pytest-cov, ruff, django-debug-toolbar | tests and linting |
