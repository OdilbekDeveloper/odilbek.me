"""Production (Railway, behind Cloudflare). The Docker image sets this module.

Every secret is required and has no default: a missing variable stops the process at startup
instead of running with something insecure.
"""

from .base import *  # noqa: F403
from .base import STORAGES, env

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# HTTPS. TLS ends at the proxy in front of the app, which reports the original scheme in
# X-Forwarded-Proto.
# ---------------------------------------------------------------------------

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
# The platform's health check calls the container directly over plain HTTP.
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS is rolled out in steps (docs/SECURITY.md): an hour at first, a year once the domain is
# stable, preload last. The values are environment-driven so each step needs no code change.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)

# The Django admin stays unmounted in production until Phase 5 puts it behind allauth with MFA
# and rate limits. Until then its only login is Django's own, which has neither.
ADMIN_ENABLED = env.bool("DJANGO_ADMIN_ENABLED", default=False)

# security.W021 asks for HSTS preload. Preloading is hard to undo, so it is a deliberate last step
# after launch, not a default.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# ---------------------------------------------------------------------------
# Static files: hashed, compressed and cacheable forever. collectstatic runs at image build time.
# ---------------------------------------------------------------------------

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
