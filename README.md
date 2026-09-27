# odilbek.me

The personal career platform of **Odilbek Shavkatov**: software, AI/automation, languages and
international communication.

It is not a portfolio template. It is a small **career operating system**: one set of
career data, presented through several professional profiles, with generated resumes,
privacy-friendly analytics, campaign attribution, and a contact pipeline, all managed from a
custom dashboard.

> **Status: Phase 2, career data model: in progress.** The data layer exists:
> - career master data, and profiles with sections and ordered links, translated (EN/KO/UZ)
> - the image pipeline, and publication rules enforced by the database
> - a temporary Django admin
> - fictional demo data (`seed_demo`) and the tooling that loads real content as unpublished
>   drafts (`draft_content`)
>
> The real content has **not** been loaded yet: it waits for the private source material. There
> are no public pages until Phases 3–4; the site still serves a placeholder. See
> [`docs/ROADMAP.md`](docs/ROADMAP.md).

## What it does

- **Profiles:**
  - `/developer/`, `/translator/`, and later `/ai-automation/` and more
  - each is a curated view of the same underlying projects, experience, skills and education, so
    a developer visitor sees developer evidence and a translation client sees translation evidence
  - new profiles are created in the dashboard, without code
- **A neutral homepage** that introduces the person first, then routes visitors to the
  profile that matters to them.
- **Evidence over claims:** skill strength is derived from real projects and roles, and claims
  link to their proof.
- **Resumes:** uploaded PDFs and PDFs generated from the same career data, per profile and
  language, downloadable without a contact gate.
- **Analytics:** cookieless and aggregated, with same-day funnels from source → profile →
  project → CV → contact, and reusable campaign links (`?ref=…`).
- **Contact:** a form stored in the database, shown in the dashboard, and notified via Telegram.
- **Languages:** English and Korean at launch; the architecture supports Uzbek.
- **A career map** built from the actual relationships in the data (after launch).

## Architecture in one picture

```
Visitor → Cloudflare → Railway (Django + PostgreSQL) → Cloudflare R2 (media, backups)
                                    └→ Telegram Bot API (notifications)

career data (master) ──▶ Profiles (website views)
                     └─▶ Resumes  (paper views)
```

One Django monolith with server-rendered templates. Master data exists once; profiles and
resumes reference it through ordered links with per-view overrides. Details:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.13, Django 6.1, PostgreSQL |
| Frontend | Django templates, HTMX, Alpine.js (CSP build) / vanilla JS, Tailwind CSS v4 (standalone CLI) |
| i18n | django-modeltranslation (en, ko, uz) + gettext |
| Auth | django-allauth with TOTP MFA (Google login later) |
| Content | Markdown (markdown-it-py + nh3) |
| PDF | WeasyPrint |
| Hosting | Railway, Cloudflare, Cloudflare R2 |
| Tooling | uv, ruff, pytest, Docker, GitHub Actions |

Why each was chosen, and what was rejected: [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Local development

Requirements: [uv](https://docs.astral.sh/uv/) and Docker. uv installs Python 3.13 if needed.

```
uv sync                                        # project-local .venv, locked dependencies
cp .env.example .env                           # then set DJANGO_SECRET_KEY; never commit .env
docker compose up -d db                        # PostgreSQL 18
uv run python manage.py predeploy              # migrate + create the cache table
uv run python manage.py tailwind runserver     # Django with the Tailwind watcher
```

On Windows with a non-UTF-8 console code page (e.g. Korean, cp949), set `PYTHONUTF8=1` first;
otherwise the Tailwind watcher's output cannot be decoded.

**Entering content (temporary admin, until the Phase 5 dashboard):**

```
uv run python manage.py createsuperuser        # a local staff account
```

The admin is at http://localhost:8000/admin/ (the segment is `DJANGO_ADMIN_PATH`). It is never
mounted in production before Phase 5 (`DJANGO_ADMIN_ENABLED`, see
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)). Records are published only through its
*Publish selected* action, which refuses anything that still contains a `TODO(odilbek)` marker.

**Demo data** is fictional ("Alex Demo", `demo-` slugs). It lives in a **separate database**,
because `seed_demo` refuses to touch one that holds real content:

```
docker compose exec db createdb -U portfolio portfolio_demo
export DATABASE_URL=postgres://portfolio:portfolio@localhost:5432/portfolio_demo
uv run python manage.py predeploy
uv run python manage.py seed_demo              # --reset removes it again
```

(PowerShell: `$env:DATABASE_URL = "…"` instead of `export`.) A variable set in the shell wins
over `.env`, so unset it again (or open a new shell) to return to the main database.

**Real content** is drafted from private sources into the git-ignored `content-import/` folder
and loaded as **unpublished** drafts for review. It never enters git:

```
uv run python manage.py draft_content --dry-run    # validate the manifest, write nothing
uv run python manage.py draft_content              # create the drafts
```

See [`docs/CONTENT_IMPORT.md`](docs/CONTENT_IMPORT.md).

**Checks** (the definition of done; CI runs the same):

```
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
```

**The production image locally:** `docker compose --profile full up --build` serves it at
http://localhost:8000. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Roadmap

```
0 Specification ✓   1 Foundation ✓   2 Data model + content ← current   3 Design system
4 Public pages   5 Dashboard   6 Profile editor   7 Contact + Telegram   8 Resumes
9 Analytics + campaigns   10 Launch (MVP)   11 Career map   12 Hardening   13 Blog   14 Polish
```

Full detail, including per-phase tests and definitions of done: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Working in this repository

For contributors and Claude Code sessions alike:

1. **Read [`CLAUDE.md`](CLAUDE.md) first.** It holds the current phase, the hard rules and the
   definition of done.
2. **Stay inside the current phase.** Later-phase work is forbidden; if something seems to need
   it, stop and ask.
3. **Plan before implementing**, and ask the owner about decisions that are theirs to make.
4. **The docs are the source of truth.** If you change behaviour, update the docs. If you depart
   from them, record why in [`docs/DECISIONS.md`](docs/DECISIONS.md) first.
5. **Keep it public-safe.** This repository is public: no secrets, credentials, personal contact
   details or real CV content in code, docs or fixtures. Real content lives in the database.
6. **Never invent career facts.** Drafted content is marked as a draft, created unpublished,
   and reviewed by the owner before publication.

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | system, apps, layering, frontend, dashboard, i18n, auth, contact, resumes, URLs |
| [DATA_MODEL](docs/DATA_MODEL.md) | models, constraints, visibility rules |
| [ROADMAP](docs/ROADMAP.md) | phases and definitions of done |
| [DESIGN](docs/DESIGN.md) | UX architecture and design system |
| [SECURITY](docs/SECURITY.md) | controls, secrets, personal data, required tests |
| [ANALYTICS](docs/ANALYTICS.md) | what is tracked, how, and for how long |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | environments, hosting, configuration, backups |
| [CONTENT_IMPORT](docs/CONTENT_IMPORT.md) | how real content is drafted and loaded as unpublished records |
| [DECISIONS](docs/DECISIONS.md) | decision log |

## License

The **software** in this repository (its source code, configuration and build files) is released
under the [MIT License](LICENSE).

The MIT License does **not** cover Odilbek Shavkatov's personal materials, whether they appear
in this repository or on the website it serves:

- biography and other personal text
- career information, including CV/resume content
- photographs
- personal documents
- personal branding and brand assets

These remain all rights reserved unless a specific item is explicitly licensed otherwise.
