"""Local development. The default for manage.py."""

from ._dotenv import load_dotenv

load_dotenv()

from .base import *  # noqa: E402, F403
from .base import INSTALLED_APPS, env  # noqa: E402

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# Development only; production requires DJANGO_SECRET_KEY and has no fallback.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-local-development-only")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])

# WhiteNoise serves static files under runserver too, so development matches production.
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]
