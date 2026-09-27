# ROADMAP

```
PHASE 0   Specification in repo                    ✅ done
    ↓
PHASE 1   Foundation + walking skeleton            ✅ done · first Railway deploy awaits approval (D-032)
    ↓
PHASE 2   Career data model + initial content      ← CURRENT · built, demo dataset ✅; real content awaits source material
    ↓
PHASE 3   Design system + public shell
    ↓
PHASE 4   Public pages from data
    ↓
PHASE 5   Auth + dashboard core
    ↓
PHASE 6   Profile editor
    ↓
PHASE 7   Contact + Telegram
    ↓
PHASE 8   Resumes
    ↓
PHASE 9   Analytics + campaigns
    ↓
PHASE 10  Production launch                        ═══ MVP complete, odilbek.me live
    ↓
PHASE 11  Career map
    ↓
PHASE 12  Hardening, performance, Google login, Uzbek content
    ↓
PHASE 13  Blog
    ↓
PHASE 14  Polish + later features
```

## Rules

1. **Later-phase work is forbidden.** If a task appears to require functionality that belongs to
   a later phase, stop and ask before implementing it, even when it would be quick. This rule
   prevents scope explosion.
2. **One phase = one branch = one PR**, with CI green before merge. Big phases (2, 4, 5, 6) are
   split into sessions, each ending in a reviewable commit.
3. **Plan first.** Every phase or session starts in plan mode. Decisions that are Odilbek's to
   make are asked, not defaulted.
4. **Definition of done** (from Phase 1): all commands in `CLAUDE.md` pass, UI changes are
   screenshot-reviewed, and docs are updated with any deviation logged in `DECISIONS.md`.
5. **When a phase is merged,** move the `← CURRENT` marker here and update "Current phase" in
   `CLAUDE.md` in the same PR.

Why the order: i18n fields exist in the data model from the start (retrofitting translations
means rewriting every form); security settings are in the foundation, not at the end; referral
tracking is part of analytics ingestion, so they share a phase.

---

## Phase 0: Specification in repo ✅

- **Objective:** the approved architecture becomes this repository's source of truth.
- **Delivers:** `docs/*.md`, `CLAUDE.md`, `README.md`, `.gitignore`, `.gitattributes`, and git initialised.
- **Not included:** any application code or dependencies, and `.env.example` (created in Phase 1
  with the settings that read it).
- **Done:** Odilbek has reviewed the docs; the diff has no secrets or personal data; committed.

## Phase 1: Foundation and walking skeleton ✅

- **Objective:** a production-shaped, empty application, ready to deploy to a Railway URL (not
  the domain). The deployment itself waits for Odilbek's approval to create the paid project (D-032).
- **Tasks:**
  - uv project with Django 6.1; verify the key packages work on 6.1 (fallback 6.0, logged)
  - settings split (`base/dev/test/prod`) driven by django-environ; `.env.example` with placeholders
  - **custom `User`** before the first migration; Argon2
  - PostgreSQL via `docker-compose.yml` for local development (no SQLite)
  - WhiteNoise; Tailwind CLI pipeline (source in `assets/`, D-030); a minimal `base.html` placeholder page
  - `/healthz/`; security settings baseline; CSP in report-only; 404/500 templates
  - `manage.py predeploy` (migrate + createcachetable)
  - multi-stage, non-root Dockerfile including WeasyPrint system libraries (fonts arrive with
    Phase 3's self-hosted families, D-031); `railway.toml`
  - CI: ruff lint and format, `makemigrations --check`, `check --deploy`, pytest against a
    Postgres service, a production-image boot and smoke test, gitleaks, pip-audit; Dependabot
  - *gated (D-032):* a Railway project with web + Postgres
- **Tests:**
  - settings load in every environment; production refuses to start without its required
    variables or on a non-PostgreSQL database, and passes `check --deploy`
  - `/healthz/` returns 200, and 503 without leaking why when the database is unreachable
  - security headers are present; CSP is report-only and strict
  - `AUTH_USER_MODEL` is `accounts.User`; emails are required and unique regardless of case
  - every top-level route segment is a reserved slug
  - 404 and 500 pages render; nothing is indexed before launch
- **Done:** `docker compose up db` plus `uv run python manage.py runserver` shows the placeholder;
  CI is green, including the production image booting and serving over the proxy's HTTPS. The
  first Railway deployment follows Odilbek's approval (D-032), any time before Phase 7.
- **Depends on:** Phase 0.

## Phase 2: Career data model and initial content (2 sessions) ← CURRENT

- **Objective:** all master data, profile, section and link models, translated and administrable,
  with Odilbek's real content drafted.
- **Status:** in progress, on branch `phase-2/career-data`.
  - **Session A:** done.
  - **Demo dataset:** done. `seed_demo` loads a complete fictional career through the same
    importer (D-042), so Phases 3–4 have realistic content to build against.
  - **Session B:** the tooling is done, but the drafting has not started. It waits for
    Odilbek's private source material:
    - CVs (EN, and KO if one exists)
    - 2–4 portraits, at least one formal
    - the list of projects to include, where their READMEs are, and which may be public
  - **The definition of done below is therefore not met yet.** It asks for Odilbek's real
    data as reviewed drafts. The demo dataset is fictional by design and cannot stand in for it.
    Everything else in this phase is complete.
- **Session A: models** ✅
  - models and constraints from `DATA_MODEL.md`; `QuerySet.public()` on every public model
  - modeltranslation registration
  - `MediaAsset` validation and re-encoding, focal point, and AVIF/WebP variants on upload
    (MVP work because of the hero photo, D-023, D-034)
  - Django admin with `TranslationAdmin` as the temporary content editor (D-038)
  - `manage.py seed_demo` with **fictional** data for development and tests (D-040): now a
    complete demo dataset loaded through the importer, removable by provenance (D-042)
  - resolve the open questions in `DATA_MODEL.md` (D-033, D-037)
- **Session B: content drafting**
  - Odilbek puts CVs and portraits in `content-import/` (git-ignored)
  - Claude reads them, plus the READMEs of projects Odilbek names, and drafts a manifest
    (`content-import/draft.json`) in which every record cites its source. `manage.py
    draft_content` validates it and loads **unpublished** records into the local database
    (D-039, `CONTENT_IMPORT.md`). The command and its tests are done ✅; the manifest is not.
  - missing facts become visible `TODO(odilbek):` placeholders; nothing is invented; no personal
    data reaches git
  - Odilbek reviews everything in admin
- **Tests** ✅ (all present and passing):
  - constraints: one home, reserved slugs, unique links, section type allowed per kind
  - `public()` hides unpublished and unlisted items correctly
  - upload validation rejects oversize files, wrong magic bytes, SVG and polyglots, and strips EXIF/GPS
  - variants are generated at the right widths and never upscaled
  - translation fallback
  - `draft_content` creates only unpublished rows
  - the demo dataset: complete, repeatable, removable by provenance, and never mixed with real
    content (`tests/test_seed_demo.py`)
- **Done:** real data sits in the local database as reviewed drafts; migrations are clean.
- **Depends on:** Phase 1.

## Phase 3: Design system and public shell

- **Objective:** a visual foundation Odilbek approves before pages are built on it.
- **Tasks:**
  - tokens for light, dark and accents; self-hosted fonts (verify Hangul and `ʻ`); type and spacing scales
  - header and footer; profile switcher (desktop segmented control, mobile bottom sheet); theme
    toggle; language switcher
  - components: button, link, chip, evidence strip, section header, list rows, a responsive
    `<picture>` with focal-point crops, form fields, notice
  - hero variants (`portrait`, `split`, `bilingual`, `statement`) using the real photo
  - **two directions side by side** (editorial vs technical-minimal) on a dev-only `/_styleguide/`
  - View Transitions opt-in
- **Tests:**
  - template rendering smoke tests
  - the picture component emits width, height, `srcset` and `sizes`
  - axe on the styleguide
- **Done:** Odilbek picks a direction from screenshots at 375/768/1280 px × light/dark × EN/KO
  (UZ spot-checked for `ʻ`); the mobile hero stays within its image budget.
- **Depends on:** Phase 1, plus the portrait from Phase 2 session B.

## Phase 4: Public pages from data (2–3 sessions)

- **Objective:** the real site, rendered entirely from the database.
- **Tasks:**
  - pages: `/`, `/about/`, `/<profile>/`, `/projects/` (HTMX filter), `/projects/<slug>/`, `/skills/<slug>/`
  - section rendering: evidence strip and derived metrics, citations (`[[project:slug]]`),
    availability and local time, language-pair matrix, contact channels
  - i18n routing, hreflang, per-profile language availability, Korean UI strings
  - SEO: titles, meta descriptions, Open Graph, canonical (drops `ref`/`utm_*`), sitemap with
    alternates, robots.txt, JSON-LD (Person, ProfilePage, CreativeWork, BreadcrumbList)
  - simple links to uploaded CVs (replaced in Phase 8)
- **Tests:**
  - page assembly respects section order, enablement, per-profile selection and overrides
  - an item hidden on one profile never appears there
  - drafts never render publicly; `?preview=1` works for staff only
  - query-count ceilings (no N+1)
  - an unavailable language redirects
  - canonical and hreflang are correct; the sitemap excludes unlisted items
- **Done:**
  - developer profile in EN, translator profile in EN + KO, Korean UI strings complete
  - Uzbek routes work but are not offered
  - Lighthouse SEO and accessibility ≥ 95; mobile LCP ≤ 2.5 s with the hero photo
- **Depends on:** Phases 2 and 3.

## Phase 5: Auth and dashboard core (2 sessions)

- **Objective:** manage all master data without Django admin.
- **Tasks:**
  - allauth password login and TOTP MFA; closed signup; admin login through allauth
  - `StaffRequired`; dashboard shell and navigation
  - CRUD for projects, experience, education, skills, categories, services, language pairs,
    channels, media and settings, with language tabs and Markdown preview
  - publish toggles; reordering (Sortable + ↑/↓); media library with required alt text and a
    focal-point picker
  - translation-completeness view
- **Tests:**
  - **every URL in the `dashboard` namespace refuses anonymous and non-staff users**
  - MFA is required under production settings
  - per-language form validation
  - reordering persists; publish toggles work
- **Done:** all content is editable from `/dashboard/`.
- **Depends on:** Phases 2 and 4.

## Phase 6: Profile editor (2 sessions)

- **Objective:** create and compose profiles without code.
- **Tasks:**
  - profile CRUD: hero, accent, variant, languages, CTA, contact variant, SEO
  - section add/enable/order/configure, with layout variants validated per type
  - item pickers per kind: search, order, featured flag, overrides
  - "Preview as visitor"
- **Tests:**
  - a profile created in the dashboard renders at `/<slug>/`
  - a reserved slug is rejected
  - invalid section or variant combinations are rejected
  - overrides render on their own profile only
- **Done:** Odilbek builds a throwaway third profile end-to-end in the UI, then deletes it.
- **Depends on:** Phase 5.

## Phase 7: Contact and Telegram

- **Objective:** leads arrive reliably; spam doesn't.
- **Tasks:**
  - contact form variants (HTMX swap)
  - Turnstile, honeypot, timing token, rate limit
  - `ContactMessage`; notifier interface with Telegram and Null implementations; outbox retry in `maintenance`
  - dashboard inbox with statuses; "send test notification"
- **Tests:**
  - a valid submission is stored and notified (fake notifier)
  - a Telegram failure still stores the message, marks it for retry, and the retry succeeds
  - honeypot, timing, Turnstile failure and rate limit each block or flag
  - HTML is escaped in the Telegram text
  - no live network calls
- **Done:** a real Telegram notification arrives from the Railway deployment.
- **Depends on:** Phases 4 and 5.

## Phase 8: Resumes

- **Objective:** uploaded and generated CVs that share the master data.
- **Tasks:**
  - resume models; "copy selection from profile"; context builder; HTML template and print CSS
  - live preview; WeasyPrint generation per language; `data_hash` staleness; the upload path
  - public `/resume/<profile>/` and `/resume/<profile>.pdf` with language fallback and friendly filenames
- **Tests:**
  - the selection determines content and overrides apply
  - the hash changes when source data changes
  - generation produces a valid PDF containing Hangul text (CI/Docker; skipped locally only
    without Pango)
  - language fallback; an unpublished resume returns 404
- **Done:** Odilbek downloads a developer CV (EN) and translator CVs (EN, and KO with photo)
  worth sending.
- **Depends on:** Phases 5 and 6.

## Phase 9: Analytics and campaigns

- **Objective:** know what works, without surveillance (`ANALYTICS.md`).
- **Tasks:**
  - `Event`, `DailySalt`, `Source`, `Campaign`
  - beacon endpoint; hashing; salt rotation; attribution; source seeding; GPC; retention
  - server-side events for resume downloads and contact submissions
  - dashboard reports, per-campaign funnels, adoption of unregistered refs, campaign link builder
- **Tests:**
  - no IP or UA is persisted
  - hashes are stable within a day and change across days; a deleted salt makes them unrecoverable
  - attribution precedence: ref > UTM > same-day inheritance > referrer > direct
  - staff and bots are excluded; malformed or oversized payloads are rejected
  - funnel math is correct on fixture data
- **Done:** a test campaign link is traced correctly through the funnel in the dashboard.
- **Depends on:** Phases 4, 7 and 8.

## Phase 10: Production launch (MVP complete)

- **Objective:** odilbek.me live, secure and backed up (`DEPLOYMENT.md`).
- **Tasks:**
  - Cloudflare DNS for the apex and `media.`; Full (strict) TLS
  - origin-lock Transform Rule; WAF and rate-limit rule; Turnstile keys
  - R2: a public media bucket on `media.odilbek.me`, and a private backup bucket with lifecycle rules
  - Railway custom domain and cron service; nightly `pg_dump` to R2; **a restore rehearsal**
  - CSP enforced; HSTS
  - privacy page (EN + KO); uptime monitor; optional Sentry
  - publish the reviewed content (developer EN; translator EN + KO); final `/security-review`
- **Tests:**
  - the origin lock rejects and allows correctly; a request bypassing Cloudflare gets 403
  - externally: security-header and TLS scanner grades; a restored backup boots the app
- **Done:** the end-to-end launch check in `DEPLOYMENT.md` passes, and Odilbek shares the link.
- **Depends on:** Phases 1–9.

## Phase 11: Career map

- **What:** the graph-builder selector, `/map/`, the `career_map` section, `map.js`, and the
  mobile drill-down (`DESIGN.md`).
- **Tests:**
  - only public items appear
  - edges match the relations
  - profile scoping works
  - the no-JS fallback is fully navigable
- **Note:** it has no dependency on Phases 7–10.

## Phase 12: Hardening and performance

- Google login (email allowlist; CSP `form-action` allows `accounts.google.com`).
- Uzbek content and `locale/uz` UI strings (can run any time after launch).
- Fragment/page caching with invalidation on save.
- Playwright E2E for critical flows with axe; an NVDA pass; Lighthouse budgets.
- A query audit and a load smoke test.

## Phase 13: Blog

`Post` and `Tag` with one row per language linked by translation groups; a dashboard editor;
RSS; BlogPosting JSON-LD; the `blog_posts` section type.

## Phase 14: Polish and later features

Each is its own small PR:
- command palette (⌘K)
- bilingual translation-sample viewer
- auto-generated Open Graph images
- JSON Resume export (`/resume/<slug>.json`)
- a full Korean-convention resume template (자기소개, Korean date and name conventions)
- testimonials
- a full JSON data export

---

## Feature register

| Feature | Why | Complexity | Phase |
|---|---|---|---|
| Evidence strip, derived skill metrics | Competence inferred from data, not self-rated bars | Low | 4 |
| Claims carry citations | `[[project:slug]]` in intros links a claim to its proof | Low | 4 |
| Availability and local time | Clients across timezones need it | Low | 4 |
| Language-pair matrix | The key evidence on a translator page | Low | 4 |
| Unlisted projects | Share NDA-sensitive work by link only | Low | 2 |
| Contact form variants | Better leads, fewer emails back and forth | Medium | 7 |
| Web resume | A printable HTML CV, free with generated resumes | Low | 8 |
| Campaign link builder | Pick a profile and ref, copy the URL, see its funnel | Low | 9 |
| Privacy / colophon page | Trust, and shows competence | Low | 10 |
| Career map | Relations from the database, not a decorative graph | Medium | 11 |
| Command palette, bilingual samples, OG images, JSON Resume, testimonials | Later polish | Low–Med | 14 |
| "Ask my career" AI | Considered, **not planned**: high gimmick risk; revisit only with an AI profile, and it must cite sources | High | — |

**Deliberately avoided:** skill percentage bars, typing-effect heroes, terminal cosplay,
particles/WebGL, visitor counters, auto-playing media.
