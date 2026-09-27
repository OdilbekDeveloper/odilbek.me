import pytest

from apps.core.middleware import build_permissions_policy

pytestmark = pytest.mark.django_db


@pytest.fixture
def response(client):
    return client.get("/")


def test_baseline_security_headers(response):
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"


def test_permissions_policy_disables_unused_features(response):
    policy = response["Permissions-Policy"]
    for feature in ("camera", "microphone", "geolocation", "payment"):
        assert f"{feature}=()" in policy


def test_csp_is_report_only_and_strict(response):
    # Enforcement begins in Phase 10; until then violations are reported, not blocked.
    assert "Content-Security-Policy" not in response
    policy = response["Content-Security-Policy-Report-Only"]
    assert "default-src 'self'" in policy
    assert "object-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "base-uri 'self'" in policy
    assert "'unsafe-eval'" not in policy
    assert "'unsafe-inline'" not in policy


def test_build_permissions_policy():
    policy = {"camera": [], "fullscreen": ["self"]}
    assert build_permissions_policy(policy) == "camera=(), fullscreen=(self)"
