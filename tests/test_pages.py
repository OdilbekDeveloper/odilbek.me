from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import path


def raise_error(request):
    raise RuntimeError("deliberate failure for the 500 page test")


urlpatterns = [path("boom/", raise_error)]


@pytest.mark.django_db
def test_placeholder_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "placeholder.html" in [t.name for t in response.templates]
    html = response.content.decode()
    assert '<html lang="en">' in html
    assert 'href="/static/css/tailwind.css"' in html


@pytest.mark.django_db
def test_nothing_is_indexed_before_launch(client):
    html = client.get("/").content.decode()
    assert '<meta name="robots" content="noindex, nofollow">' in html


@pytest.mark.django_db
def test_unknown_url_renders_the_404_page(client):
    response = client.get("/this-does-not-exist/")
    assert response.status_code == 404
    assert "404.html" in [t.name for t in response.templates]


@pytest.mark.urls(__name__)
def test_server_error_renders_the_self_contained_500_page():
    response = Client(raise_request_exception=False).get("/boom/")
    assert response.status_code == 500
    assert b"Something went wrong on our side." in response.content


def test_500_template_has_no_template_logic():
    # When the server is failing, this page must depend on nothing that could be the cause.
    source = (Path(settings.BASE_DIR) / "templates" / "500.html").read_text(encoding="utf-8")
    assert "{%" not in source
    assert "{{" not in source
