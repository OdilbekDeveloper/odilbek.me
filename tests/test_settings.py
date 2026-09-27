"""Each settings module loads, and production refuses to start insecurely."""

import json

import pytest
from django.conf import settings
from django.db import connection

REPORT_PROD = """
import json, django
django.setup()
from django.conf import settings as s
print(json.dumps({
    "debug": s.DEBUG,
    "ssl_redirect": s.SECURE_SSL_REDIRECT,
    "redirect_exempt": s.SECURE_REDIRECT_EXEMPT,
    "proxy_header": list(s.SECURE_PROXY_SSL_HEADER),
    "session_secure": s.SESSION_COOKIE_SECURE,
    "csrf_secure": s.CSRF_COOKIE_SECURE,
    "hsts": s.SECURE_HSTS_SECONDS,
    "first_hasher": s.PASSWORD_HASHERS[0],
    "staticfiles": s.STORAGES["staticfiles"]["BACKEND"],
    "session_domain": s.SESSION_COOKIE_DOMAIN,
}))
"""


def test_suite_runs_on_test_settings_and_postgresql():
    assert settings.SETTINGS_MODULE == "config.settings.test"
    assert connection.vendor == "postgresql"


def test_production_settings_are_secure(run_with_settings, prod_env):
    result = run_with_settings("config.settings.prod", REPORT_PROD, prod_env)
    assert result.returncode == 0, result.stderr
    prod = json.loads(result.stdout)

    assert prod["debug"] is False
    assert prod["ssl_redirect"] is True
    assert prod["redirect_exempt"] == [r"^healthz/$"]
    assert prod["proxy_header"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert prod["session_secure"] is True
    assert prod["csrf_secure"] is True
    assert prod["hsts"] > 0
    assert prod["first_hasher"] == "django.contrib.auth.hashers.Argon2PasswordHasher"
    assert prod["staticfiles"] == "whitenoise.storage.CompressedManifestStaticFilesStorage"
    assert prod["session_domain"] is None


@pytest.mark.parametrize("missing", ["DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DATABASE_URL"])
def test_production_refuses_to_start_without_required_variable(
    run_with_settings, prod_env, missing
):
    del prod_env[missing]
    result = run_with_settings("config.settings.prod", "import django; django.setup()", prod_env)
    assert result.returncode != 0
    assert missing in result.stderr


def test_production_passes_deploy_checks(run_with_settings, prod_env):
    code = (
        "import django; django.setup(); from django.core.management import call_command; "
        "call_command('check', deploy=True, fail_level='WARNING')"
    )
    result = run_with_settings("config.settings.prod", code, prod_env)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_database_other_than_postgresql_is_refused(run_with_settings, prod_env):
    prod_env["DATABASE_URL"] = "sqlite:///db.sqlite3"
    result = run_with_settings("config.settings.prod", "import django; django.setup()", prod_env)
    assert result.returncode != 0
    assert "must point at PostgreSQL" in result.stderr


def test_development_settings_load(run_with_settings, prod_env):
    code = (
        "import json, django; django.setup(); from django.conf import settings as s; "
        "print(json.dumps({'debug': s.DEBUG, 'first_app': s.INSTALLED_APPS[0]}))"
    )
    env = {"DATABASE_URL": prod_env["DATABASE_URL"]}
    result = run_with_settings("config.settings.dev", code, env)
    assert result.returncode == 0, result.stderr
    dev = json.loads(result.stdout)
    assert dev["debug"] is True
    # Must precede django.contrib.staticfiles to take over runserver's static handling.
    assert dev["first_app"] == "whitenoise.runserver_nostatic"
