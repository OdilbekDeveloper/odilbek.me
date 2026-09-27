# DECISIONS

A lightweight architecture decision log. Each entry records **what** was decided, **why**, what
was **rejected**, and what it **commits us to**.

Rules:

- **Append-only.** A decision is never edited to mean something else. To change one, add a new
  entry that supersedes it and mark the old one `Superseded by D-0NN`.
- **Log before you deviate.** Any implementation that departs from `docs/` gets an entry here
  *before* the code is written, and the affected doc is updated in the same change.
- **Status:** `Confirmed` means Odilbek chose it explicitly. `Accepted` means it is a technical
  default in the approved plan, open to override.

---

## Confirmed with Odilbek (2026-09-27)

| Question | Answer | Entry |
|---|---|---|
| Languages at launch | English + Korean | D-013 |
| Uzbek | Supported by the architecture, Latin script only; content after launch | D-014 |
| Media storage | Cloudflare R2 | D-008 |
| Analytics | Cookieless, same-day attribution | D-016 |
| Launch timing | After the full MVP (Phases 0–10) | D-025 |
| Rich text | Markdown + live preview | D-017 |
| Django line | 6.1 | D-003 |
| Photo | Prominent in the hero | D-023 |
| Visual direction | Compare editorial vs technical-minimal in Phase 3 | D-024 |
| Initial content | Drafted from CVs + project READMEs, unpublished, reviewed | D-026 |

---

## Process

### D-001 · Staged implementation with strict phase discipline
**Status:** Confirmed · 2026-09-27
**Decision:** Build in the phases defined in `docs/ROADMAP.md`. Each phase is planned (plan
mode), approved, implemented, verified against the definition of done, reviewed, and merged as
its own branch and PR. **Later-phase work is forbidden**; if a task appears to need it, stop and ask.
**Why:** One enormous prompt produces an unreviewable result. Small phases keep every change
understandable, testable and reversible, and the same rule kept earlier projects in scope.
**Rejected:** Building everything at once; "quick" pulls of later-phase features into earlier phases.
**Consequences:** Some phases ship deliberately incomplete (e.g. uploaded CV links before the
resume generator). `CLAUDE.md` names the current phase and must be updated when it changes.

### D-002 · Public GitHub repository
**Status:** Confirmed · 2026-09-27
**Decision:** The source code is public.
**Why:** The code is itself evidence of competence, and nothing in the design depends on secrecy.
**Consequences:** No secrets, credentials, personal contact details, local machine paths or
private infrastructure identifiers may ever be committed. Configuration comes from environment
variables, real career content lives only in the database and R2, `content-import/` is
git-ignored, and CI runs a secret scanner. See `docs/SECURITY.md`.

---

## Platform

### D-003 · Django 6.1
**Status:** Confirmed · 2026-09-27
**Decision:** Start on Django 6.1 (current stable, Aug 2026) with Python 3.13.
**Why:** It has built-in Content Security Policy support, template partials (one template
serves a full page and its HTMX fragments), and the tasks API if background work ever grows.
**Rejected:** Django 5.2 LTS. It would need `django-csp` and `django-template-partials` to get
the same features.
**Consequences:** Upgrade to the 6.2 LTS (expected April 2027). A few packages declare support
only up to 6.0 in their metadata; Phase 1 verifies they work, and 6.0 is the fallback if one doesn't.

### D-004 · Server-rendered frontend: Django templates + HTMX + Alpine (CSP build) / vanilla JS
**Status:** Confirmed · 2026-09-27
**Decision:** Pages are Django templates. HTMX handles partial updates, mainly in the dashboard.
Alpine.js, **CSP build only**, handles small UI state. Vanilla JS modules handle the analytics
beacon, the theme toggle and the career map. **No React/Next.js. No DRF in the MVP.**
**Why:** This is a content site where SEO and speed matter, built by someone strongest in Python
and Django. Server rendering keeps one language and one mental model. The CSP build of Alpine
lets the Content Security Policy forbid `eval`.
**Rejected:** Next.js/React (fashion, not need: a second runtime, build chain and state model);
standard Alpine (requires `unsafe-eval`); DRF now (nothing consumes an API).
**Consequences:** Alpine components are registered with `Alpine.data()` in static files, not as
inline expressions. `htmx.config.allowEval = false`. DRF is added only when a real API client exists.

### D-005 · PostgreSQL in every environment
**Status:** Confirmed · 2026-09-27
**Decision:** PostgreSQL locally (Docker), in CI (service container), and in production (Railway).
**Why:** Constraints, JSON fields, indexes and query behaviour must be identical wherever tests run.
**Rejected:** SQLite for development or tests (behaviour drift).
**Consequences:** Local development needs Docker running for the database.

### D-006 · Railway hosting
**Status:** Confirmed · 2026-09-27
**Decision:** Run a web service (gunicorn + Django), a Railway PostgreSQL service on private
networking, and a cron service for scheduled maintenance, all in one Railway project.
**Why:** Odilbek already uses Railway. It is inexpensive at this scale, deploys from a
Dockerfile, and runs migrations in a pre-deploy step so a failed migration never serves traffic.
**Consequences:** The container disk is ephemeral, so uploads must go to object storage (D-008).
Use one web replica, and never expose the database through a public TCP proxy.

### D-007 · Cloudflare in front
**Status:** Confirmed · 2026-09-27
**Decision:** Cloudflare provides DNS, TLS (Full strict), WAF, rate-limit rules, Turnstile, and
caching of static assets and media. An origin-lock header proves requests came through Cloudflare.
**Why:** It absorbs most abusive traffic for free, and Turnstile is a privacy-friendly CAPTCHA alternative.
**Consequences:** Client IPs come from `CF-Connecting-IP`, which is trusted only when the origin
header is valid. Nothing is described as DDoS-proof.

### D-008 · Cloudflare R2 for media and backups
**Status:** Confirmed · 2026-09-27
**Decision:** Store user-uploaded media and resume PDFs in a public R2 bucket served at
`media.odilbek.me` via `django-storages` (S3 API). Store database backups in a separate private
R2 bucket. Use the local filesystem in development.
**Why:** No egress fees, a CDN in front, and uploads served from a separate origin from the app.
**Rejected:** A Railway volume (ties the app to one replica and to the Railway plan's backups);
a Railway bucket (private by default, so files need proxying or presigned URLs).
**Consequences:** Cloudflare requires a payment method on the account even for the free tier.
Switching providers is a settings change, not a code change.

### D-009 · Tooling: uv, ruff, pytest, Docker
**Status:** Accepted · 2026-09-27
**Decision:** Use `uv` with `pyproject.toml` + `uv.lock`, ruff for lint and format (line length
100; `E,F,I,UP,B`), pytest with pytest-django, a multi-stage non-root Dockerfile, and GitHub Actions CI.
**Why:** These are the conventions already proven in Odilbek's other projects.

### D-010 · Tailwind CSS v4 via the standalone CLI
**Status:** Accepted · 2026-09-27
**Decision:** Build Tailwind v4 with its standalone binary through `django-tailwind-cli`.
Design tokens are defined CSS-first.
**Why:** No Node.js in the build or the image.
**Consequences:** **Tailwind class names are never built from database values.** Per-profile
styling uses `data-*` attributes and CSS variables from a fixed token set.

---

## Domain model

### D-011 · Profile-specific career views over shared master data
**Status:** Confirmed · 2026-09-27
**Decision:** The `career` app holds master data (skills, projects, experience, education,
services, language pairs, contact channels). **Profiles** and **resumes** are curated views that
reference it through ordered link tables with optional per-view text overrides. Home (`/`) and
About (`/about/`) are Profiles of `kind=home` and `kind=about`, so they reuse the section
system, SEO fields and analytics.
**Why:** The same job or project must be able to appear on several profiles, worded differently,
without duplicating the underlying record.
**Rejected:** Duplicated records per profile; hard-coded Home/About pages.
**Consequences:** No code may branch on a profile's slug or name. Creating a profile needs no
code; a new *kind* of section or hero treatment does, which is intentional because it is design work.

### D-012 · Root-level profile slugs
**Status:** Confirmed · 2026-09-27
**Decision:** Role profiles live at the URL root: `/developer/`, `/translator/`.
**Why:** Short, shareable, campaign-friendly URLs.
**Rejected:** `/p/developer/`.
**Consequences:** A reserved-slug validator blocks collisions with routes and language codes,
and a test fails if a new top-level route isn't reserved. See `docs/ARCHITECTURE.md`.

### D-013 · English + Korean at launch
**Status:** Confirmed · 2026-09-27
**Decision:** At launch the developer profile is complete in English (Korean optional), and the
translator profile plus the Korean UI strings are complete in Korean.
**Consequences:** Phases 4, 8 and 10 are "done" only when these language versions are complete.

### D-014 · Uzbek supported by the architecture, Latin script, content after launch
**Status:** Confirmed · 2026-09-27
**Decision:** The data model, routing (`/uz/…`) and forms support Uzbek from the start, in
**Latin script only** (one `uz` locale). Uzbek content and UI strings are added after launch.
**Rejected:** Adding Cyrillic as a fourth locale.
**Consequences:** Fonts must render `oʻ gʻ` (U+02BB), which is verified in Phase 3. A profile
offers Uzbek only once its `languages` list includes it.

### D-015 · Multilingual content with django-modeltranslation
**Status:** Accepted · 2026-09-27
**Decision:** Use field-level translation columns (`title_en`, `title_ko`, `title_uz`) with
English fallback. Only English is required. UI strings use gettext. Slugs are not translated.
Blog posts are the exception: one row per language, linked by a `translation_group`.
**Why:** With three fixed languages, columns are the simplest to query, order and edit. The ORM
and ModelForms work transparently, and there are no joins.
**Rejected:** django-parler (translation tables, joins, harder custom forms); a JSON dict per
field (no per-language validation, awkward forms).
**Consequences:** A fourth language means a migration plus form tabs, which is rare and
acceptable. Switching *approach* later would mean rewriting every model and form.

---

## Features

### D-016 · Cookieless, same-day analytics
**Status:** Confirmed · 2026-09-27
**Decision:** First-party, aggregated analytics with **no cookies**. Visitors are counted with
`sha256(daily random salt ‖ IP ‖ UA ‖ host)`. The salt is deleted after its day, and IPs and
user agents are never stored. See `docs/ANALYTICS.md`.
**Why:** It respects privacy by construction, needs no consent banner, and still answers "which
source leads to CV downloads and contact".
**Rejected:** A first-party cookie with consent (more invasive, needs a banner, and tracks only
consenting visitors in detail).
**Consequences:** Funnels link only same-day activity. A visitor who arrives Monday and returns
Tuesday counts twice. A contact message still records its campaign.

### D-017 · Markdown + live preview for long text
**Status:** Confirmed · 2026-09-27
**Decision:** Long text is Markdown, rendered by markdown-it-py and sanitized by nh3, with a live
preview in the dashboard.
**Why:** Clean, portable, safe output. The same source renders on the site and in PDF resumes.
**Rejected:** A WYSIWYG editor (heavy JavaScript dependency, messy HTML, poor reuse in PDFs).

### D-018 · Custom dashboard; Django admin as back-office
**Status:** Confirmed · 2026-09-27
**Decision:** Content is managed in a custom `/dashboard/` built from plain class-based views,
ModelForms with language tabs, HTMX, and SortableJS drag-and-drop (with keyboard ↑/↓
alternatives). Django admin remains at a secret path, behind the same login.
**Why:** The workflows (profile composition, item pickers with overrides, resume preview,
analytics, inbox) don't fit the admin's model-centric UI.
**Rejected:** Admin-only; a generic CMS framework or page builder.
**Consequences:** Keep explicit per-entity views with small shared mixins, not a meta-framework.
The dashboard UI is English-only (D-028).

### D-019 · Uploaded and generated resumes behind one URL
**Status:** Confirmed · 2026-09-27
**Decision:** Each profile's default resume is served at `/resume/<profile>.pdf`, whether it is
an uploaded PDF or generated from the database. There is one file per language, no contact
gate, and every download is counted.
**Why:** Shared links never break when a profile switches from an uploaded to a generated CV.

### D-020 · Curated resumes
**Status:** Confirmed · 2026-09-27
**Decision:** A generated resume has **its own** ordered selection of projects, experience,
skills and education, with per-row overrides. "Copy selection from profile" seeds it.
**Why:** What belongs on a one- or two-page CV differs from what belongs on the website.
**Rejected:** Live inheritance from the profile (two code paths, and silent changes to a
curated CV when the profile is edited).
**Consequences:** Staleness is detected with a hash of the resume's input data. The dashboard
shows "Outdated · Regenerate".

### D-021 · WeasyPrint for PDF generation
**Status:** Confirmed · 2026-09-27
**Decision:** Render resume HTML/CSS to PDF with WeasyPrint. PDFs are generated only by staff
and stored; public requests never trigger rendering.
**Why:** One HTML template serves the preview, the web resume and the PDF. It is light compared
with a headless browser.
**Rejected:** Playwright/Chromium (~400 MB image); ReportLab (no HTML reuse).
**Consequences:** The Docker image needs Pango libraries and local Hangul fonts. PDF work runs in
Docker on Windows, and PDF tests run in CI.

### D-022 · No Redis or Celery in the MVP
**Status:** Confirmed · 2026-09-27
**Decision:** No task queue or Redis. Rate limits and allauth throttles use Django's database
cache. Telegram notifications use an **outbox**: the send happens after commit with a timeout,
and the scheduled `maintenance` command retries failures. PDF generation is a synchronous staff action.
**Why:** The workload is tiny, and every extra service is cost and operational surface.
**Consequences:** The DB cache is not atomic, so a burst may let a few extra requests past a rate
limit, which is acceptable at this scale. `REDIS_URL` becomes a drop-in if abuse appears.

---

## Identity and content

### D-023 · Prominent hero photo
**Status:** Confirmed · 2026-09-27
**Decision:** A portrait is part of the first impression on home and profile pages. Each image
stores a focal point; profiles may override the default portrait.
**Consequences:** Responsive AVIF/WebP variants and the `<picture>` component are **MVP work**,
not polish, because the photo is the page's largest element (LCP). The design must avoid the
"photo + big name + skill chips" template look; the rules are in `docs/DESIGN.md`.

### D-024 · Visual direction chosen by comparison in Phase 3
**Status:** Confirmed · 2026-09-27
**Decision:** Phase 3 renders two directions (*editorial* and *technical-minimal*) with the real
photo, in EN/KO and light/dark, and Odilbek picks from screenshots.

### D-025 · Launch after the full MVP
**Status:** Confirmed · 2026-09-27
**Decision:** odilbek.me goes live at the end of Phase 10, with analytics and campaigns already
running. The career map follows in Phase 11 and has no dependency on launch.

### D-026 · Initial content drafted from CVs and project READMEs
**Status:** Confirmed · 2026-09-27
**Decision:** In Phase 2, content is drafted from CVs and photos Odilbek places in the git-ignored
`content-import/` folder, and from the READMEs of projects Odilbek names. It is loaded directly
into the database as **unpublished** records.
**Consequences:** Nothing personal enters git. **Personal career facts are never invented**:
missing facts become visible `TODO(odilbek):` placeholders, and nothing is published until
Odilbek reviews it. Operational details of other systems are summarised at the capability level.

### D-027 · Authentication: django-allauth with MFA, closed signup, custom User
**Status:** Accepted · 2026-09-27
**Decision:** A custom `User` model exists from the first migration. django-allauth provides
password login, TOTP MFA (required for staff in production) and Google login (Phase 12).
Signup is closed; Google may only log into an existing staff user on an email allowlist.
Passwords are hashed with Argon2.
**Why:** It is mature and secure, has built-in login rate limiting, and saves writing auth by hand.
**Consequences:** There is no outgoing email in the MVP; password reset is via
`manage.py changepassword` or Google login.

### D-028 · Dashboard UI in English only
**Status:** Accepted · 2026-09-27
**Decision:** The dashboard's own interface (labels, navigation, messages) is English. Content
fields are editable in all three languages through language tabs.
**Why:** The dashboard has one user; translating it would be cost with no benefit.
