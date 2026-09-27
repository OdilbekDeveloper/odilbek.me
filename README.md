# odilbek.me

The personal career platform of **Odilbek Shavkatov**: software, AI/automation, languages and
international communication.

It is not a portfolio template. It is a small **career operating system**: one set of
career data, presented through several professional profiles, with generated resumes,
privacy-friendly analytics, campaign attribution, and a contact pipeline, all managed from a
custom dashboard.

> **Status: Phase 1, foundation.** A production-shaped Django skeleton: settings, PostgreSQL,
> the custom user model, a health check, CI and the production image. The portfolio itself is
> built from Phase 2 onward. See [`docs/ROADMAP.md`](docs/ROADMAP.md).

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
0 Specification ✓   1 Foundation ✓   2 Data model + content ← next   3 Design system
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
