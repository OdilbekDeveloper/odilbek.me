# DEPLOYMENT

Hosting, environments, configuration and operations. **Nothing is deployed yet.** Phase 1 deploys
a walking skeleton to a Railway URL; Phase 10 puts it on odilbek.me. Commands and names here are
the plan; Phase 1 and Phase 10 make them real and update this document.

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
| Local | Windows host, Django native via `uv` | Postgres in Docker | local filesystem | `config.settings.dev` |
| Test / CI | GitHub Actions (Ubuntu) | Postgres service container | local temp dir | `config.settings.test` |
| Production | Railway | Railway Postgres | R2 | `config.settings.prod` |

A staging environment (a second Railway environment) is optional and can be added after launch.

## 3. Local development direction

- **Python 3.13 via `uv`**, with a project-local `.venv` (never a shared venv):
  ```
  uv sync
  docker compose up -d db
  uv run python manage.py migrate
  uv run python manage.py runserver      # plus the Tailwind watcher (exact command set in Phase 1)
  ```
- **PostgreSQL runs in Docker.** Its major version matches Railway's, because `pg_dump`/`pg_restore`
  and query behaviour must match.
- **PDF work runs in Docker** (the production image), because WeasyPrint's system libraries
  (Pango) are impractical to install natively on Windows. Everything else runs natively.
- **External services are off by default:** `NullNotifier` replaces Telegram, and Turnstile uses
  its official test keys or is disabled in `dev` settings.

## 4. Railway

One new project, separate from all other projects.

| Service | Details |
|---|---|
| **web** | Built from the repository `Dockerfile` (multi-stage, non-root). `gunicorn config.wsgi` bound to `$PORT`. **1 replica.** Healthcheck `/healthz/`. `preDeployCommand = python manage.py predeploy` (migrate + createcachetable): a failed migration stops the deploy and the previous version keeps serving |
| **db** | Railway PostgreSQL. **Private networking only; no public TCP proxy.** `DATABASE_URL` is referenced from this service |
| **cron** | Same image. Command `python manage.py maintenance`, schedule `*/10 * * * *`. Exits when done |

`collectstatic` and the Tailwind build run at **image build time**, not at deploy.

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

Names are **provisional**. Phase 1 creates `.env.example` with the ones it needs, and each later
phase adds its own. Real values live only in Railway variables and a local, git-ignored `.env`.

| Variable | Secret | Introduced | Purpose |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | | 1 | `config.settings.{dev,test,prod}` |
| `DJANGO_SECRET_KEY` | ✔ | 1 | signing |
| `DJANGO_DEBUG` | | 1 | dev only |
| `DJANGO_ALLOWED_HOSTS` | | 1 | host allowlist |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | | 1 | explicit HTTPS origins |
| `DATABASE_URL` | ✔ | 1 | PostgreSQL |
| `DJANGO_ADMIN_PATH` | | 2 | secret-ish admin URL segment |
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
