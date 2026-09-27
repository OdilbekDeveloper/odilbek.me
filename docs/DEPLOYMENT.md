# DEPLOYMENT

Hosting, environments, configuration and operations. **Nothing is deployed yet.** Phase 1 built
everything a deployment needs and CI boots the production image on every push. The first Railway
deployment waits for Odilbek to approve creating the paid project (D-032), and Phase 10 puts the
site on odilbek.me. Sections 1–4 describe what exists; later sections are the plan until their
phase makes them real. Phase 2 added no infrastructure. Its only deployment-relevant changes are
the admin variables (section 7) and local media storage (section 2).

## 1. Topology

```
                  ┌───────────────────────── Cloudflare ─────────────────────────┐
Visitor ─ HTTPS ─▶│ DNS · TLS Full (strict) · WAF · rate-limit rule · Turnstile  │
                  │ Transform Rule adds X-Origin-Verify · caches static + media   │
                  └──────────────┬──────────────────────────────┬────────────────┘
                                 │                              │
                    odilbek.me   ▼                 media.odilbek.me
              ┌──────────── Railway project ────────┐     ┌──── Cloudflare R2 ────┐
              │ web   gunicorn + Django + WhiteNoise│     │ public media bucket    │
              │ cron  manage.py maintenance (10 min)│────▶│ private backup bucket  │
              │ db    PostgreSQL (private network)  │     └────────────────────────┘
              └─────────────────────────────────────┘
                                 │ outbound only
                                 ▼
                          Telegram Bot API
```

## 2. Environments

| Environment | Where | Database | Media | Settings module |
|---|---|---|---|---|
| Local | Windows host, Django native via `uv` | Postgres in Docker | local filesystem (`media/`, git-ignored) | `config.settings.dev` |
| Test / CI | GitHub Actions (Ubuntu) | Postgres service container | a temporary folder per test | `config.settings.test` |
| Production | Railway | Railway Postgres | R2 (Phase 10) | `config.settings.prod` |

A staging environment (a second Railway environment) is optional and can be added after launch.

**Media before Phase 10.** Uploads go to `MEDIA_ROOT` on the local filesystem, and development
serves them at `/media/` (only with `DEBUG` on). Production has no media storage yet. Its only
upload path, the admin, is not mounted there, and the container's filesystem would not survive
a redeploy anyway. R2 arrives with Phase 10, together with `media.odilbek.me`.

## 3. Local development

- **Python 3.13 via `uv`**, with a project-local `.venv` (never a shared venv):
  ```
  uv sync
  cp .env.example .env                           # set DJANGO_SECRET_KEY
  docker compose up -d db                        # PostgreSQL 18
  uv run python manage.py predeploy              # migrate + createcachetable
  uv run python manage.py tailwind runserver     # runserver plus the Tailwind watcher
  ```
- **The temporary admin** (until Phase 5): `uv run python manage.py createsuperuser`, then
  http://localhost:8000/admin/. It is mounted because `DJANGO_ADMIN_ENABLED` defaults to `True` in
  development.
- **Demo data** goes in a separate database, because `seed_demo` refuses one that holds real
  content: `docker compose exec db createdb -U portfolio portfolio_demo`, then run `predeploy`
  and `seed_demo` with `DATABASE_URL` pointing at it. A variable set in the shell wins over `.env`.
  `seed_demo --reset` removes the demo content.
- **Real content** is loaded locally with `draft_content` from the git-ignored `content-import/`
  folder, as unpublished drafts (`CONTENT_IMPORT.md`). It reaches production only once the
  dashboard (Phase 5) and R2 (Phase 10) exist. How it gets there is decided then.
- **Settings:** `manage.py` defaults to `config.settings.dev`; pytest always uses
  `config.settings.test` (`--ds`); the Docker image sets `config.settings.prod`. Only dev and
  test read `.env`. Production reads its real environment only.
- **PostgreSQL 18 runs in Docker**, the major version Railway provisions, because
  `pg_dump`/`pg_restore` and query behaviour must match. PostgreSQL 18 images store data under
  `/var/lib/postgresql/18/`, so the compose volume mounts `/var/lib/postgresql`.
- **Windows consoles** with a non-UTF-8 code page (e.g. Korean cp949) need `PYTHONUTF8=1`;
  otherwise Python cannot decode the Tailwind binary's output.
- **The production image locally:** `docker compose --profile full up --build` builds it, runs
  `predeploy` and serves it at http://localhost:8000 (SSL redirect off, since there is no TLS
  locally).
- **PDF work runs in Docker** (the production image), because WeasyPrint's system libraries
  (Pango) are impractical to install natively on Windows. Everything else runs natively.
- **External services are off by default:** `NullNotifier` replaces Telegram, and Turnstile uses
  its official test keys or is disabled in `dev` settings.

## 3a. Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request. Its three jobs run in parallel:

| Job | What it proves |
|---|---|
| Lint, checks and tests | ruff lint and format, no missing migrations, `check --deploy --fail-level WARNING` under production settings, and the full pytest suite on a PostgreSQL 18 service |
| Production image | the Dockerfile builds; `predeploy` runs against PostgreSQL; the web process becomes healthy. The smoke test checks that plain-HTTP `/healthz/` is not redirected, other plain-HTTP pages are, HTTPS responses carry HSTS, the hashed stylesheet is served, the image's Pillow can encode AVIF and WebP with LittleCMS (D-034), and the process is uid 10001 and cannot write to the app |
| Secrets and dependency audit | gitleaks over the full history, and pip-audit over `uv.lock` |

Dependabot opens weekly update PRs for uv, GitHub Actions and the Docker base image. Python and
PostgreSQL major versions are excluded, because those are decisions.

## 4. Railway

One new project, separate from all other projects.

| Service | Details |
|---|---|
| **web** | Built from the repository `Dockerfile` (multi-stage; the app runs as uid 10001 and cannot modify its own code). gunicorn (`config/gunicorn.conf.py`) bound to `$PORT`. **1 replica.** Healthcheck `/healthz/`, which also checks the database and is exempt from the HTTPS redirect. `preDeployCommand = python manage.py predeploy` (migrate + createcachetable): a failed migration stops the deploy and the previous version keeps serving. All of this is in `railway.toml` |
| **db** | Railway PostgreSQL. **Private networking only; no public TCP proxy.** `DATABASE_URL` is referenced from this service |
| **cron** | Same image. Command `python manage.py maintenance`, schedule `*/10 * * * *`. Exits when done |

`collectstatic` and the Tailwind build run at **image build time**, not at deploy.

**Required web variables on Railway:** `DJANGO_SECRET_KEY` (long, random), `DATABASE_URL`
(referenced from the db service), and `DJANGO_ALLOWED_HOSTS`. The allowed hosts must include the
service's public domain **and `healthcheck.railway.app`**, the host Railway's health checks
send; without it, every health check is answered 400 and the deploy never goes live.

**Deploy flow:**
1. A PR is merged to `main`, with CI green.
2. Railway builds the image.
3. Pre-deploy runs migrations.
4. The healthcheck passes.
5. Traffic switches to the new version.

## 5. Cloudflare

| Setting | Value |
|---|---|
| Zone | `odilbek.me`, with its nameservers at Cloudflare |
| DNS | Apex → Railway custom-domain target (proxied). `media` → the R2 bucket's custom domain |
| SSL/TLS | Full (strict); Always Use HTTPS; minimum TLS 1.2; HSTS once stable |
| Transform Rule | Adds the request header `X-Origin-Verify: <ORIGIN_VERIFY_SECRET>` to all traffic to the origin |
| WAF | Managed free rules on |
| Rate limiting | One rule covering `POST /contact/` and `/accounts/login/` |
| Turnstile | One widget for the contact form (site key public, secret key server-side) |
| Caching | `/static/*` and media cached long (hashed filenames). HTML is not edge-cached. The resume download redirect is `no-store` |

Phase 10 confirms Railway's current guidance for Cloudflare-proxied custom domains before switching DNS.

## 6. Cloudflare R2

| Bucket | Access | Used for |
|---|---|---|
| media | Public, **only** via the custom domain `media.odilbek.me` (the `r2.dev` URL stays disabled) | images, variants, resume PDFs |
| backups | Private | nightly database dumps, deleted after 30 days by a lifecycle rule |

**Least privilege:** separate API tokens. The web service's token can read and write the media
bucket only; the cron service's token can write the backup bucket only.

## 7. Environment variables (planned inventory)

Phase 1 and Phase 2 variables are final and in `.env.example`. Later names are **provisional**,
and each phase adds its own there. Real values live only in Railway variables and a local,
git-ignored `.env`.

| Variable | Secret | Introduced | Purpose |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | | 1 | set by the Docker image to `config.settings.prod`; `manage.py` defaults to dev |
| `DJANGO_SECRET_KEY` | ✔ | 1 | signing; **required** in production, no default |
| `DJANGO_ALLOWED_HOSTS` | | 1 | host allowlist; **required** in production, including `healthcheck.railway.app` (section 4) |
| `DATABASE_URL` | ✔ | 1 | PostgreSQL only; **required** everywhere |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | | 1 | explicit HTTPS origins, e.g. `https://odilbek.me` |
| `DJANGO_DEBUG` | | 1 | development only (default `True` there) |
| `DJANGO_LOG_LEVEL` | | 1 | default `INFO` |
| `DJANGO_CONN_MAX_AGE` | | 1 | persistent DB connections, default 60 s |
| `DJANGO_SECURE_SSL_REDIRECT` | | 1 | default `True`; off only for the local production image |
| `DJANGO_SECURE_HSTS_SECONDS` | | 1 | default 3600; raised to a year once the domain is stable |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` / `DJANGO_SECURE_HSTS_PRELOAD` | | 1 | defaults `True` / `False` |
| `PORT`, `WEB_CONCURRENCY`, `GUNICORN_THREADS` | | 1 | gunicorn; Railway sets `PORT`. Defaults 8000 / 2 / 4 |
| `POSTGRES_PORT` | | 1 | local only: the host port for the compose database |
| `DJANGO_ADMIN_PATH` | | 2 | the admin's URL segment: lowercase, ending in `/`, default `admin/`. Anything else stops startup. A profile slug can never take it |
| `DJANGO_ADMIN_ENABLED` | | 2 | mounts the temporary admin. Default `True` in development and tests, **`False` in production**. Leave it off in production until Phase 5 puts the admin behind allauth with MFA (D-038) |
| `TELEGRAM_BOT_TOKEN` | ✔ | 7 | notifications |
| `TELEGRAM_CHAT_ID` | | 7 | notification target |
| `TURNSTILE_SITE_KEY` | | 7 | public widget key |
| `TURNSTILE_SECRET_KEY` | ✔ | 7 | server-side verification |
| `ANALYTICS_RETENTION_DAYS` | | 9 | default 395 |
| `R2_ENDPOINT_URL` | | 10 | S3 API endpoint |
| `R2_MEDIA_BUCKET` / `R2_BACKUP_BUCKET` | | 10 | bucket names |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | ✔ | 10 | per-service tokens (section 6) |
| `MEDIA_DOMAIN` | | 10 | `media.odilbek.me` |
| `ORIGIN_VERIFY_SECRET` | ✔ | 10 | origin lock |
| `SENTRY_DSN` | ✔ | 10 | optional error reporting |
| `DASHBOARD_ALLOWED_EMAILS` | | 12 | Google login allowlist |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | ✔ | 12 | Google login |
| `REDIS_URL` | ✔ | — | not used in the MVP; a drop-in if needed (D-022) |

## 8. Scheduled work

There is one command, `manage.py maintenance`, run every 10 minutes by the cron service. Each job
records when it last ran:

| Job | Frequency | Phase |
|---|---|---|
| retry unsent contact notifications | every run | 7 |
| delete past analytics salts; delete expired events | daily | 9 |
| `pg_dump` (custom format, compressed) → private R2 | nightly | 10 |

## 9. Backups and restore

- **What:** a nightly logical dump to R2, kept 30 days. Railway's own backups too, if the plan includes them.
- **Targets:** at most 24 hours of data loss; about an hour to restore.
- **Restore rehearsal** (required before launch, and repeated occasionally):
  1. download the latest dump
  2. restore it into a scratch Postgres in Docker
  3. boot the app against it
  4. open the home page and the dashboard
- **Media** in R2 is not versioned in the MVP. Uploads are infrequent and their source files
  remain with Odilbek.

## 10. Prerequisites only Odilbek can do

| Item | Needed by |
|---|---|
| Create the GitHub repository (public) and push `main` | before Phase 1's first PR |
| Approve creation of the new Railway project | Phase 1 |
| Create a Telegram bot (@BotFather) and get the target chat ID | Phase 7 |
| Create a Turnstile widget | Phase 7 |
| Confirm the `odilbek.me` registration; point its nameservers at Cloudflare (it currently does not resolve) | Phase 10 |
| Add a payment method to Cloudflare (required for R2 even on the free tier) | Phase 10 |
| Create a Google OAuth client | Phase 12 |

## 11. Cost expectations

Roughly a Railway Hobby plan: one small web service, a Postgres service, and a cron service that
runs for seconds at a time. Cloudflare is free; R2 stays within its free tier at this volume.
Keep one web replica; there is no other recurring cost.

## 12. Launch check (end of Phase 10)

1. Open `https://odilbek.me/developer/?ref=test-launch`.
2. Open a project, download the CV, click the Telegram link, and submit the contact form.
3. Confirm:
   - the Telegram notification arrives
   - the message appears in the dashboard inbox with campaign `test-launch`
   - the campaign funnel shows every step
   - a request that bypasses Cloudflare gets 403
   - security-header and TLS scanners report good grades
   - the latest backup restores and boots
