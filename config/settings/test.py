"""The test suite (pytest passes --ds=config.settings.test).

Tests run against real PostgreSQL (D-005): DATABASE_URL comes from the environment, or from .env
locally, and pytest-django creates and destroys its own test database next to it.
"""

from ._dotenv import load_dotenv

load_dotenv()

from .base import *  # noqa: E402, F403

DEBUG = False

SECRET_KEY = "test-only-not-a-secret"

ALLOWED_HOSTS = ["testserver", "localhost"]

# Argon2 is deliberately slow; tests don't need to pay for it on every created user.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Tests never depend on the cache table that `predeploy` creates.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# collectstatic never runs under tests, so there is no STATIC_ROOT to serve from; WhiteNoise finds
# files where they live instead.
STATIC_ROOT = None
WHITENOISE_USE_FINDERS = True
