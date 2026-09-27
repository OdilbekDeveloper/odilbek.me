import pytest
from django.db import OperationalError

pytestmark = pytest.mark.django_db


def test_healthz_reports_ok_and_is_never_cached(client):
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "no-store" in response["Cache-Control"]


def test_healthz_reports_unavailable_without_leaking_the_error(client, monkeypatch):
    def broken_cursor():
        raise OperationalError("connection to server at 10.0.0.5 failed: password rejected")

    monkeypatch.setattr("apps.core.views.connection.cursor", broken_cursor)

    response = client.get("/healthz/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"10.0.0.5" not in response.content


def test_healthz_accepts_only_safe_methods(client):
    assert client.head("/healthz/").status_code == 200
    assert client.post("/healthz/").status_code == 405
