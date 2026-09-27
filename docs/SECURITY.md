# SECURITY

No system is DDoS-proof, and nothing in this project is described as such. Cloudflare absorbs and
filters a great deal; the origin is kept cheap to serve and hard to abuse.

## 1. What we protect, and from whom

| Asset | Threat |
|---|---|
| The dashboard account | credential stuffing, phishing, session theft |
| Contact messages (visitors' names and emails) | data exposure, spam flooding |
| Unpublished content and drafts | leaking before review |
| Personal data in a **public** repository | accidental commits of CVs, phone numbers, tokens |
| Availability and cost | bots, scrapers, expensive endpoints, origin bypass |
| Visitors' privacy | over-collection in analytics (see `ANALYTICS.md`) |

## 2. Controls

**Transport and edge**

| Area | Control |
|---|---|
| Transport | Cloudflare Full (strict) TLS; Always-HTTPS; HSTS rolled out short, then 1 year, then preload; `SECURE_PROXY_SSL_HEADER` |
| Origin lock | A Cloudflare Transform Rule adds `X-Origin-Verify: <secret>`; in production, middleware returns 403 without it (except `/healthz/`). This stops attackers bypassing Cloudflare through Railway's edge |
| Client IP | `CF-Connecting-IP` is trusted **only** when the origin header verifies. The IP is used for rate limits and the analytics hash and is **never stored** |
| Headers | Django built-in CSP with nonces (report-only first, then enforced). Also `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, COOP |

The CSP directives:
- `default-src 'self'`
- Turnstile allowances
- `media.odilbek.me` for images
- `object-src 'none'`
- `frame-ancestors 'none'`
- `form-action` including `accounts.google.com` (required for Google login)

**Identity and access**

| Area | Control |
|---|---|
| Authentication | allauth; Argon2; TOTP MFA required for staff in production; closed signup; Google restricted to an email allowlist; login-failure rate limits; Django admin at a secret path behind the same login |
| Authorization | Every dashboard view requires staff. **A test walks every URL in the `dashboard` namespace** and asserts that anonymous and non-staff users are refused |
| Sessions and CSRF | Secure, HttpOnly, SameSite=Lax, **host-only** cookies (never `.odilbek.me`); CSRF on every form; explicit `CSRF_TRUSTED_ORIGINS` |
| Draft leakage | Public reads only through selectors built on `QuerySet.public()`, tested per entity. `?preview=1` is honoured for staff only and returns `no-store` |

**Input, uploads and abuse**

| Area | Control |
|---|---|
| Input | ModelForm validation, length caps, URL fields restricted to `http(s)://` |
| Markdown | Rendered only through the shared renderer and sanitized by **nh3** (allowlisted tags; `rel="noopener nofollow"` on external links). User-authored content is never marked `\|safe` otherwise |
| Uploads | See below |
| Abuse | Turnstile, honeypot and timing token on the contact form; django-ratelimit on `/contact/` and `/e/`; a Cloudflare rate-limit rule on login and contact; beacon payloads ≤ 2 KB with an Origin check; `DATA_UPLOAD_MAX_MEMORY_SIZE` set |
| Expensive work | PDFs are generated only by staff and stored. **No anonymous request ever triggers PDF rendering** |

Upload rules:
- **Staff-only.**
- An allowlist by extension, **magic bytes** and size: images ≤ 10 MB, PDFs ≤ 5 MB.
- Images are **re-encoded** with Pillow, which strips EXIF/GPS and neutralizes polyglots, with
  `MAX_IMAGE_PIXELS` set. **No SVG.**
- Random filenames, served from a **separate origin** (`media.odilbek.me`).

**Data and operations**

| Area | Control |
|---|---|
| Database | Railway private networking only, with no public TCP proxy. Nightly `pg_dump` to a private R2 bucket with lifecycle retention. **Restore rehearsed** before launch |
| Supply chain | Pinned `uv.lock`; GitHub Actions pinned to full commit SHAs (a tag can be moved, a commit cannot); Dependabot for both; `pip-audit` in CI; vendored JS pinned and self-hosted |
| Operations | `DEBUG=False` in production; custom 404/500 pages (the 500 page has no template logic, so it can't fail with the server); `check --deploy --fail-level WARNING` gates CI; logs to stdout (Railway); optional Sentry via `SENTRY_DSN` |
| Container | Multi-stage image. The process runs as **uid 10001**; application code is root-owned and **not writable** by it; build tools (uv, the Tailwind binary) never reach the runtime image. CI asserts all of this on every push |
| Health check | `/healthz/` answers only `{"status": ...}`; database errors go to the log, never to the caller |

## 3. Secrets

- **All** configuration comes from environment variables (`DEPLOYMENT.md` lists them).
  Production requires its secrets and has **no fallback values**: a missing variable stops the
  process at startup.
- `.env` and every `.env.*` except `.env.example` are git-ignored. `.env.example` contains
  **placeholders only**. Only the dev and test settings read a `.env` file; **production never
  does**, so a stray file can't feed it values. `.dockerignore` keeps `.env*` out of image builds.
- CI runs **gitleaks** on every push.
- The dashboard shows whether an integration is configured, **never** its value.
- Secrets never appear in logs, error messages, Telegram notifications, tests or fixtures.
- **If a secret is ever committed:** rotate it first, then clean history. Rotation is the fix;
  history rewriting is secondary.

## 4. Personal data and the public repository

The repository is public (D-002). Therefore:

- **Real career content lives only in the database and R2.** It never goes in fixtures,
  migrations, tests, docs or seed files.
- **`content-import/` is git-ignored.** CVs and photos placed there are read locally and loaded
  into the database by `draft_content`; they are never committed.
- **Test and demo data is obviously fictional** (e.g. "Example Project", `example.com`).
- **Before every commit, review the diff for:**
  - secrets and tokens
  - phone numbers, home addresses, dates of birth, personal email addresses
  - local machine paths
  - private infrastructure identifiers (project or service IDs, internal hostnames)
- **Project descriptions of other systems** stay at the capability level. Operational details
  (payment flows, credentials, internal endpoints) are left out and flagged for Odilbek's review.
- **Never invent personal career facts** (see `CLAUDE.md`). A fabricated credential or client on a
  public site is a misrepresentation, not a typo.

## 5. Required security tests

These must exist and pass. Structural tests are written before the features they protect.

| Test | Phase |
|---|---|
| Security headers present; CSP strict (no `unsafe-eval`/`unsafe-inline`); `check --deploy` clean under prod settings | 1 ✅ |
| Production refuses to start without its secrets or on a non-PostgreSQL database | 1 ✅ |
| Every top-level route segment is a reserved profile slug | 1 ✅ |
| The production image runs unprivileged and cannot modify its code (CI) | 1 ✅ |
| `public()` hides unpublished/unlisted items for every public model | 2 |
| Upload validation: oversize, wrong magic bytes, SVG, polyglot rejected; EXIF stripped | 2 |
| Drafts never render publicly; preview is staff-only | 4 |
| Every dashboard URL refuses anonymous and non-staff users | 5 |
| MFA enforced for staff in production settings | 5 |
| Contact: honeypot, timing, Turnstile failure, rate limit; HTML escaped in Telegram text | 7 |
| No anonymous path triggers PDF generation | 8 |
| Analytics: no IP or UA persisted; salts unrecoverable once deleted; oversized payloads rejected | 9 |
| Origin lock rejects requests without the header | 10 |

## 6. Review gates

- Run `/code-review` on every PR.
- Run `/security-review` before merging Phases 5 (auth), 7 (public input), 8 (uploads, PDF),
  9 (analytics ingest) and 10 (deployment).
- **After launch:** check external security-header and TLS scanner results, and run a restore
  rehearsal from backup.
