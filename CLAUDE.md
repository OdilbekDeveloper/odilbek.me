# odilbek.me — Claude Instructions

## Product

odilbek.me is Odilbek Shavkatov's personal career platform: a public website plus a custom
dashboard. It presents several professional profiles (Backend Developer, Korean
Translator/Interpreter, later others) over **one set of reusable career data**. It generates
resumes, records privacy-friendly aggregated analytics with campaign attribution, and delivers
contact requests to Telegram.

Visitors should infer competence from **evidence, not claims**. Measure every design and content
decision against that.

## Current phase

> **PHASE 0 — Specification in repo.** Documentation and repository governance only.
> No application code, dependencies, models, templates or deployments exist yet.

`docs/ROADMAP.md` defines the phases.

**Later-phase work is forbidden. If a task appears to require functionality belonging to a later
phase, stop and ask before implementing it**, even when it would be quick.

## Source of truth

Read the relevant document before implementing. If code and docs disagree, stop and ask which is
right; do not silently "fix" either.

| Doc | Covers |
|---|---|
| `docs/ARCHITECTURE.md` | system, apps and dependency direction, layering, frontend, dashboard, i18n, auth, contact, resumes, URLs |
| `docs/DATA_MODEL.md` | models, fields, constraints, visibility semantics |
| `docs/ROADMAP.md` | phases, scope, tests and definition of done per phase |
| `docs/DESIGN.md` | UX architecture, design system, accessibility |
| `docs/SECURITY.md` | security controls, secrets, personal-data rules, required security tests |
| `docs/ANALYTICS.md` | events, hashing, attribution, retention |
| `docs/DEPLOYMENT.md` | environments, Railway, Cloudflare, R2, env vars, backups |
| `docs/DECISIONS.md` | why things are the way they are. **Log any deviation here before implementing it** |

## Repository map

Now:
```
CLAUDE.md  README.md  .gitignore  .gitattributes
docs/      the specification (above)
```

Planned (each part is created in its phase, **never earlier**):
```
config/settings/{base,dev,test,prod}.py   env-driven settings                     Phase 1
apps/core/        abstract models, SiteSettings, MediaAsset, markdown, slugs       Phase 1–2
apps/accounts/    custom User, allauth adapters                                   Phase 1, 5
apps/career/      master data: skills, projects, experience, education, …         Phase 2
apps/profiles/    profiles, sections, profile↔item links, page assembly           Phase 2, 4
apps/dashboard/   custom CMS: views, forms, templates — no models                 Phase 5–6
apps/contact/     messages, spam checks, notifiers                                Phase 7
apps/resumes/     curated resumes, files, PDF rendering                           Phase 8
apps/analytics/   events, salts, sources, campaigns, beacon                       Phase 9
apps/blog/        posts, tags                                                     Phase 13
templates/  static/  locale/
```

## Core principles

1. **Master data vs curated views.** `career` holds what is true. Profiles and resumes are views
   that reference master data through ordered link tables with optional per-view overrides.
   Never duplicate a project, job or skill to show it differently; override on the link row.
2. **Evidence over claims.** Skill strength is derived from data (projects, roles, years), never
   self-rated.
3. **Profiles are data, not code.** Creating a profile, ordering sections, selecting items,
   accent, hero variant, SEO and resumes are all done in the dashboard. Only a new *kind* of
   section or hero treatment is code.
4. **Server-rendered first.** Django templates + HTMX; Alpine (CSP build) or vanilla JS for small
   state. No SPA framework.
5. **Simple infrastructure.** One Django monolith, PostgreSQL, and no queue or Redis in the MVP.
6. **Privacy by construction.** Cookieless analytics; no IPs, user agents or cross-day
   identifiers stored.

## Key technology decisions

Rationale for each is in `docs/DECISIONS.md`.

- **Framework:** Django 6.1 on Python 3.13, with PostgreSQL in every environment.
- **Multilingual:** django-modeltranslation (`en` default, `ko` at launch, `uz` Latin after launch).
- **Frontend:** Django templates + HTMX, Alpine.js CSP build / vanilla JS, and Tailwind v4 via the
  standalone CLI (no Node).
- **Auth:** django-allauth with MFA; a custom `accounts.User`.
- **Content and resumes:** Markdown (markdown-it-py + nh3) with live preview; WeasyPrint for PDFs.
- **Hosting:** Railway, with Cloudflare in front and R2 for media and backups.
- **Tooling:** uv, ruff, pytest, Docker, GitHub Actions.

Do not add a dependency without a one-line justification. If the dependency is architectural,
add a `DECISIONS.md` entry too.

## Hard rules

- **Public reads must go through selectors, and publication/visibility rules must be enforced
  structurally.** Public views and templates obtain content only via `apps/<app>/selectors.py`,
  built on each model's `QuerySet.public()` (published, listed, selected for the profile). No
  public view queries a model manager directly. Draft preview (`include_drafts=True`) is passed
  only after a staff check.
- **Writes go through services.** Views validate, call a selector or service, and render.
- **No profile-specific logic.** Never branch on a profile's slug, name or id in Python,
  templates, CSS or JS. Profile differences are fields (variant, accent, form variant, sections).
- **Never build Tailwind class names from database values.** Per-profile styling uses `data-*`
  attributes and CSS variables from a fixed token set.
- **Reserve every new top-level URL segment** in the reserved-slug list in the same change; a
  test enforces it.
- **The User model is `accounts.User`.** Use `get_user_model()` / `settings.AUTH_USER_MODEL`,
  never `auth.User`.
- **App dependencies point one way** (`docs/ARCHITECTURE.md` §3). Nothing imports from `dashboard`.
- **Never invent personal career facts, dates, metrics, clients, project claims, credentials, or
  experience.** Draft content must be clearly marked as draft and reviewed by Odilbek before
  publication. Drafted records are always created **unpublished**. A missing fact gets a visible
  `TODO(odilbek): …` placeholder, never a plausible guess.
- **Real career content is data, not code.** It is entered in admin or the dashboard, or loaded
  from `content-import/` (git-ignored) into the database. It never goes into fixtures,
  migrations, tests or docs.
- **Ask, don't default.** When planning, ask Odilbek about decisions that are theirs to make
  (product, UX, languages, cost, privacy, identity) instead of silently choosing.

## Security rules

- **Secrets:**
  - there are no secrets in code, docs, tests, fixtures or commit history; configuration comes
    from environment variables
  - `.env` is git-ignored, and `.env.example` holds placeholders only
- **The repository is public.** Review every diff before committing for:
  - secrets and tokens
  - personal contact details
  - local machine paths
  - private infrastructure identifiers
- **Markdown** renders only through the shared sanitizing renderer. Never mark user-authored
  content `|safe` otherwise.
- **Uploads** are staff-only:
  - allowlisted types and sizes, with a magic-byte check
  - images are re-encoded, which strips EXIF/GPS
  - no SVG
- **Every dashboard URL requires staff.** A test walks the whole `dashboard` URL namespace.
- **No anonymous request may trigger expensive work** such as PDF generation.
- **Strict CSP:**
  - no inline scripts without a nonce
  - no `eval`: use the Alpine CSP build and set `htmx.config.allowEval = false`
- Full detail: `docs/SECURITY.md`.

## Testing rules

- **Database:** pytest + pytest-django against **real PostgreSQL** (Docker locally, a service
  container in CI). No SQLite substitute.
- **No live network calls:** no test may call Telegram, Turnstile, Google or R2. Use the
  Null/fake implementations.
- **Structural rules are tested before the features that could break them:** visibility,
  dashboard auth, reserved slugs.
- **Query counts:** page-assembly tests assert query-count ceilings, so N+1 queries fail.
- **Fixtures** use obviously fictional data only.
- **PDF tests** run in CI/Docker. They are skipped locally only when Pango is unavailable.

## Definition of done

**Phase 0:** docs reviewed by Odilbek, no secrets or personal data in the diff, committed.

**From Phase 1 onward, every one of these must pass before a task is done:**
```
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check --deploy --settings=config.settings.prod   # needs prod-like env vars; enforced in CI
```

Also required:
- UI changes are screenshot-reviewed (375 / 768 / 1280 px, light and dark, EN and KO)
- the docs are updated when behaviour changes, with any deviation logged in `docs/DECISIONS.md`
- the diff is reviewed for scope, secrets and personal data

## Workflow

1. Read this file, `docs/ROADMAP.md`, and the docs for the area.
2. Inspect the existing code.
3. Plan in plan mode, and ask about decisions that are Odilbek's to make.
4. Implement the smallest correct change within the current phase.
5. Run the definition of done.
6. Review the diff.
7. Work on one branch and one PR per phase, and commit only when asked.

Do not rewrite unrelated code. When a phase is merged, update "Current phase" here and the
marker in `docs/ROADMAP.md`.

## Roadmap

```
PHASE 0   Specification in repo                          ← CURRENT
PHASE 1   Foundation + walking skeleton
PHASE 2   Career data model + initial content
PHASE 3   Design system + public shell
PHASE 4   Public pages from data
PHASE 5   Auth + dashboard core
PHASE 6   Profile editor
PHASE 7   Contact + Telegram
PHASE 8   Resumes
PHASE 9   Analytics + campaigns
PHASE 10  Production launch                              ═══ MVP complete
PHASE 11  Career map
PHASE 12  Hardening, performance, Google login, Uzbek content
PHASE 13  Blog
PHASE 14  Polish + later features
```
