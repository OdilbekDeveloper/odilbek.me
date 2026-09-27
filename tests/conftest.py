import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    """Every test writes media to its own temporary folder, never to the project's media/."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def run_with_settings():
    """Run Python code in a fresh interpreter under a chosen settings module and environment.

    Settings are read once per process, so checking how another environment's settings behave
    (production, above all) needs a new process. Every DJANGO_* variable and DATABASE_URL is
    removed first, so each test states exactly the environment it depends on.
    """

    def run(module, code, env=None):
        clean = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("DJANGO_") and k != "DATABASE_URL"
        }
        clean.update(env or {})
        clean["DJANGO_SETTINGS_MODULE"] = module
        clean["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            env=clean,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

    return run


@pytest.fixture
def prod_env():
    """The minimum production environment: every required variable, no optional ones."""
    return {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_ALLOWED_HOSTS": "example.com",
        "DATABASE_URL": "postgres://user:password@localhost:5432/db",
    }
