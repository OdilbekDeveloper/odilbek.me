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

---

## Phase 1

### D-029 · MIT for the software; personal materials excluded
**Status:** Confirmed · 2026-09-27
**Decision:** The software in this repository (source code, configuration, build files) is
released under the MIT License (`LICENSE`). Odilbek's personal materials are **not** covered and
remain all rights reserved unless an item is explicitly licensed otherwise. That covers biography,
career information, CV/resume content, photographs, personal documents, and personal branding and
brand assets, whether they appear in the repository or on the website.
**Why:** The code is shared as evidence of competence; a person's identity and career record are
not reusable material.
**Consequences:** It supersedes the Phase 0 README line "no license chosen". Real career content
still never enters the repository (D-002, D-026); the exclusion also covers anything on the website.

### D-030 · The Tailwind source CSS lives outside `static/`
**Status:** Accepted · 2026-09-27 · *Corrects `ARCHITECTURE.md`, which placed it at `static/css/app.css`.*
**Decision:** The Tailwind source is `assets/css/app.css`. The build writes
`static/css/tailwind.css`, which is generated and git-ignored.
**Why:** Anything under `static/` is collected. The production manifest storage then rewrites the
source file and fails on its `@import "tailwindcss";` (django-tailwind-cli warns about exactly
this, as `W001`), so `collectstatic` breaks.
**Consequences:** Source detection is explicit (`@source` for `templates/` and `apps/`), not
automatic.

### D-031 · The planned stack, verified before locking
**Status:** Accepted · 2026-09-27
**Decision:** Every package in the plan was installed together at its latest version in a scratch
project on Python 3.13 + Django 6.1.1 and exercised, not just imported. **No version change was
needed.** Each phase locks only the packages it uses.

| Package | Verified | Notes |
|---|---|---|
| Django 6.1.1 on Python 3.13 | ✔ | Built-in CSP (`SECURE_CSP[_REPORT_ONLY]`); the nonce is lazy and appears only when a template uses it |
| PostgreSQL 18 (Railway's current version) + psycopg 3.3 | ✔ | Local Docker and CI use the same major |
| django-modeltranslation 0.20.6 | ✔ | columns, migrations, English fallback |
| django-allauth 65.19.4 (account, MFA, Google) | ✔ | |
| django-htmx 1.29, django-tailwind-cli 4.8.1 + Tailwind 4.3.3 | ✔ | Tailwind binary pinned, not "latest" |
| whitenoise 6.12, django-environ 0.14, pytest-django 4.14 | ✔ | Metadata declares Django ≤ 6.0 / 5.2, but they work on 6.1 |
| django-storages 1.14.6 (S3 API for R2) | ✔ | Metadata stale (last release Apr 2025); URL generation verified |
| markdown-it-py 4.2 + nh3 0.3.7 | ✔ | Phase 4: render with raw HTML disabled (`html=False`), nh3 as the second layer |
| WeasyPrint 70 on Debian 13 (`python:3.13-slim`) | ✔ | `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`; Hangul and `oʻ gʻ` embed and extract correctly with a CJK font |
| django-ratelimit 4.1.0 | ✔ | Works on the DB cache, but **no release since July 2023**. Phase 7 decides: keep it, or a small in-house limiter on the cache |
| argon2-cffi, httpx, Pillow, factory-boy | ✔ / import | factory-boy is exercised in Phase 2 |

**Consequences:** The Phase 1 image installs WeasyPrint's system libraries now. The fonts are the
self-hosted families chosen in Phase 3, not distribution fonts.

### D-032 · The first Railway deployment waits for spending approval
**Status:** Accepted · 2026-09-27 · *Amends Phase 1's definition of done in `ROADMAP.md`.*
**Decision:** Phase 1 delivers everything needed to deploy (`Dockerfile`, `railway.toml`,
`predeploy`, `/healthz/`, production settings). CI builds the production image, boots it the way
Railway runs it, and smoke-tests it on every push. **Creating the Railway project**, which starts
billing, happens only once Odilbek approves it.
**Why:** Creating a paid service is Odilbek's spending decision (D-006), and nothing in Phases 2–6
depends on a live deployment.
**Consequences:** The deployment must happen before Phase 7, whose definition of done needs a real
Telegram notification from the Railway deployment.

---

## Phase 2

### D-033 · A project's primary profile lives on its link row
**Status:** Accepted · 2026-09-27 · *Resolves `DATA_MODEL.md` open question 1.*
**Decision:** `ProfileProject.is_primary` (at most one per project, enforced by a partial unique
index) replaces the planned `Project.primary_profile` foreign key.
**Why:** The foreign key would make `career` depend on `profiles`, breaking the one-way dependency
rule. The link row also guarantees integrity: a project's primary profile always actually shows it.
**Consequences:** `profiles.services.set_primary_profile(project, profile)` moves the flag.

### D-034 · The media pipeline: Pillow alone, re-encode everything, AVIF and WebP variants
**Status:** Accepted · 2026-09-27
**Decision:** `apps/core/media.py` is the only way a file becomes a `MediaAsset`.
- Size is checked before reading; the type comes from magic bytes; the extension must be
  allowlisted and agree with them; the declared content type must not contradict them.
- Images must contain no active content anywhere, and their container must end where the image
  ends: a PNG with data after IEND, a JPEG trailed by an archive or executable, or a WebP or AVIF
  whose structure doesn't cover the file exactly is rejected.
- Pillow must fully decode the image, within 50 megapixels; animated images are refused.
- The stored image is rebuilt from pixels alone after applying the EXIF orientation and converting
  to sRGB, so no EXIF, GPS, XMP or ICC data survives.
- Variants in AVIF and WebP at 480/960/1440/1920 px, never wider than the source; an image
  narrower than 480 px gets one variant at its own width. Resized, never cropped, so the focal
  point stays valid.
- Stored names are random tokens; the uploaded name is never used. Deleting an asset deletes its
  files, after commit.
- PDFs (≤ 5 MB) are stored as uploaded after checking the header, the end marker and the absence
  of scripts, launch actions and embedded files. They are staff-only uploads served from a separate
  origin; deeper PDF handling is decided with resumes in Phase 8.
- `sha256` is of the uploaded bytes: the same file uploaded twice is the same asset.
**Why:** Pillow 12.3's own wheels encode AVIF and WebP and include LittleCMS on Windows and Linux,
verified in the production image, so no separate AVIF plugin is needed.
**Consequences:** Processing is synchronous (a staff action; no queue, D-022). A validation step
(`prepare`) runs before anything is written, so the admin shows errors on the form.

### D-035 · Publication integrity is enforced by the database and a single service
**Status:** Accepted · 2026-09-27
**Decision:** `is_published` is not editable in any form. Records are published only through
`apps.core.services.publish()`, which the admin's actions call. PostgreSQL enforces:
- a published record has `published_at`;
- **a published record contains no `TODO(odilbek` marker** in any language of its own text
  (case-insensitive), and an enabled profile section contains none either;
- a project needs a summary, an experience entry a start date, and a profile a headline to be
  published (a draft may lack them; an empty end date means "current", so a start is required).

The service also refuses when related text the record displays still has a marker: link-row
overrides, project image captions and alt text, the hero image, and the site settings.
**Why:** The marker is how drafts flag facts the sources did not establish. A constraint holds for
admin edits, bulk `QuerySet.update()` calls and the shell alike.

### D-036 · List fields are PostgreSQL arrays
**Status:** Accepted · 2026-09-27 · *Clarifies `DATA_MODEL.md` ("JSON list").*
**Decision:** `Profile.languages` and `LanguagePair.modes` are `ArrayField`s of short strings, with
`django.contrib.postgres` installed.
**Why:** Typed, and constrained directly: `languages` must contain `en` and be a subset of the site
languages; `modes` must be non-empty and known. The project is PostgreSQL-only (D-005).

### D-037 · Phase 2 schema clarifications
**Status:** Accepted · 2026-09-27
- **At most one home and one about profile** are enforced by the database. That a home profile
  *exists* is a content requirement: only a migration creating one could enforce it, and content
  never goes in migrations.
- **Reserved slugs apply to role profiles**, which live at the URL root; home and about have fixed
  routes. The database checks the static list; `clean()` also checks the admin path configured for
  the environment, which only the application knows.
- **Section types** are the Phase 2 set; `career_map` (Phase 11) and `blog_posts` (Phase 13) are
  added in their phases. Only home profiles may have a `profile_router` section; this cross-table
  rule is validated in `clean()` and the services.
- **The accent token set and per-section layout variants** hold a single `default` value until
  Phase 3 and Phase 4 design them; the database enforces the layout map.
- **`Profile.default_resume`** arrives with the `Resume` model in Phase 8.
- **Blank means "not stated"**: site availability and a project's status may be empty rather than
  default to a claim.
- **English is required at the database level too** (not NULL, not blank) wherever the original
  field is required; Korean and Uzbek columns are always optional.
- **`ImportedRecord`** (core) records which record the draft import created for which manifest
  key: provenance only, never content (D-039).

### D-038 · The temporary admin
**Status:** Accepted · 2026-09-27
**Decision:** Django admin, with modeltranslation's plain `TranslationAdmin` (language fields shown
side by side), is the content editor until the dashboard (Phase 5). It is mounted at
`DJANGO_ADMIN_PATH` (default `admin/`) and **not mounted in production** until Phase 5 puts it
behind allauth with MFA (`DJANGO_ADMIN_ENABLED`, default off in production settings).
**Rejected:** The tabbed translation admin, which loads jQuery UI from a CDN (against the
self-hosting and CSP rules).

### D-039 · Real content is drafted into a manifest, then loaded as unpublished drafts
**Status:** Accepted · 2026-09-27
**Decision:** Reading CVs and READMEs and deciding what they establish is drafting work, not code:
its output is a JSON manifest in the git-ignored `content-import/`, in which every record cites its
source. `manage.py draft_content` validates that manifest strictly (any error aborts before
anything is written) and loads it. Every record is unpublished; a year-only date or a missing end
date becomes a `TODO(odilbek)` note; published records are never modified; drafts deleted since an
import are never recreated. The format is in `docs/CONTENT_IMPORT.md`.
**Rejected:** Parsing CVs automatically, which would need guesswork or an AI system, and would
invent structure the sources don't state.

### D-040 · Demo content is fictional and never mixes with real content
**Status:** Accepted · 2026-09-27 · *Superseded by D-042.*
**Decision:** `manage.py seed_demo` creates an obviously fictional site ("Alex Demo", `demo-`
slugs, `@example.com`), published through the publish service, and removes it with `--reset`. It
refuses to run on a database holding any real content; demo work uses a separate database.

### D-041 · Test data comes from plain helper functions, not factory-boy
**Status:** Accepted · 2026-09-27 · *Amends D-031's note that factory-boy would be exercised in
Phase 2.*
**Decision:** The Phase 2 tests build their fictional records and synthetic files with small
functions in `tests/helpers.py`. factory-boy was not added.
**Why:** The helpers are short, explicit about every field that matters to a test, and keep the
fictional data in one reviewable file. A factory library would add a dependency without removing
code.
**Consequences:** factory-boy stays in the planned list (`ARCHITECTURE.md` §13) and is added only
if a later phase's tests need it, with a line of justification.

### D-042 · The demo dataset goes through the importer and is tracked by provenance
**Status:** Accepted · 2026-09-27 · *Supersedes D-040.*
**Decision:** `seed_demo` loads a complete fictional career ("Alex Demo") from
`apps/profiles/demo_data/`:
- a schema-1 manifest, run through the same importer as real drafts
- then a review step: per-profile wording, galleries, SEO, availability, and publishing everything
  except six records kept as drafts

`ImportedRecord.origin` (`draft` or `demo`) marks every record it creates, and
`seed_demo --reset` deletes exactly those. Slugs are realistic (`developer`, `translator`,
`ai-automation`) rather than prefixed with `demo-`.
**Why:**
- Phases 3 and 4 need varied, realistic content to design and test against before the real
  content exists: long titles, Korean text, hidden records, galleries, overrides.
- Loading through the importer exercises the same validation, media pipeline and provenance as
  real content. The manifest also serves as a complete example of the format.
- Provenance, not a naming convention, identifies demo records. The data can look real and still
  be removed exactly.
**Consequences:**
- **Demo and real content never share a database.** `seed_demo` refuses a database holding
  career content it did not create, and `draft_content` refuses one holding the demo.
- **Never on the real site.** Only the development and test settings allow seeding
  (`DEMO_CONTENT_ALLOWED`).
- **The importer processes each image once**, and skips images it has already imported.
- **A re-run changes nothing.** To pick up changes to the files, reset and seed again.
