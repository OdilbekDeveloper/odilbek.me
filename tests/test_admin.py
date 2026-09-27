"""The temporary content editor: practical, and unable to bypass the publication rules."""

import importlib
import io

import pytest
from django.contrib import admin
from django.core.files.storage import default_storage
from django.urls import clear_url_caches, reverse
from PIL import Image

from apps.career.models import Project
from apps.core.models import MediaAsset
from tests import helpers as h

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        username="example-admin", email="admin@example.com", password="an-example-password-1"
    )
    client.force_login(user)
    return client


@pytest.mark.parametrize("model", list(admin.site._registry), ids=lambda m: m._meta.label_lower)
def test_every_admin_page_loads(staff_client, model):
    prefix = f"admin:{model._meta.app_label}_{model._meta.model_name}"
    changelist = staff_client.get(reverse(f"{prefix}_changelist"), follow=True)
    assert changelist.status_code == 200
    add = staff_client.get(reverse(f"{prefix}_add"))
    assert add.status_code in (200, 403)  # 403: the site-settings singleton already exists


def test_publication_is_not_an_editable_field(staff_client):
    project = h.project()
    page = staff_client.get(reverse("admin:career_project_change", args=[project.pk]))
    assert page.status_code == 200
    assert 'name="is_published"' not in page.content.decode()


def _publish_action(client, model, objs):
    return client.post(
        reverse(f"admin:career_{model}_changelist"),
        {"action": "publish_selected", "_selected_action": [o.pk for o in objs]},
        follow=True,
    )


def test_publish_action_publishes_clean_records(staff_client):
    project = h.project()
    _publish_action(staff_client, "project", [project])
    project.refresh_from_db()
    assert project.is_published and project.published_at


def test_publish_action_refuses_records_with_todos(staff_client):
    project = h.project(summary_en="TODO(odilbek): summary")
    response = _publish_action(staff_client, "project", [project])
    project.refresh_from_db()
    assert not project.is_published
    assert "Not published" in response.content.decode()


def test_editing_a_draft_never_publishes_it(staff_client):
    project = h.project()
    form = {
        "title_en": "Edited title",
        "slug": project.slug,
        "summary_en": "Edited",
        "is_published": "on",  # smuggled in: must be ignored
        "is_listed": "on",
        "order": 0,
        "media-TOTAL_FORMS": 0,
        "media-INITIAL_FORMS": 0,
    }
    staff_client.post(reverse("admin:career_project_change", args=[project.pk]), form)
    project.refresh_from_db()
    assert project.title_en == "Edited title"
    assert not project.is_published


def test_admin_upload_goes_through_the_pipeline(staff_client):
    response = staff_client.post(
        reverse("admin:core_mediaasset_add"),
        {
            "upload": h.upload("portrait.jpg", h.jpeg_with_gps((800, 400)), "image/jpeg"),
            "alt_text_en": "A generated test gradient",
            "focal_x": 0.5,
            "focal_y": 0.3,
        },
    )
    assert response.status_code == 302
    asset = MediaAsset.objects.get()
    assert asset.file.name.startswith("images/") and "portrait" not in asset.file.name
    with default_storage.open(asset.file.name) as handle:
        assert len(Image.open(io.BytesIO(handle.read())).getexif()) == 0


def test_admin_rejects_a_hostile_upload_on_the_form(staff_client, isolated_media):
    svg_in_disguise = b'<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>'
    response = staff_client.post(
        reverse("admin:core_mediaasset_add"),
        {"upload": h.upload("logo.png", svg_in_disguise), "alt_text_en": "x", "focal_x": 0.5},
    )
    assert response.status_code == 200  # the form is shown again with the error
    assert "not a supported image" in response.content.decode()
    assert MediaAsset.objects.count() == 0


def test_admin_is_not_mounted_when_disabled(settings):
    settings.ADMIN_ENABLED = False
    import config.urls

    try:
        clear_url_caches()
        importlib.reload(config.urls)
        prefixes = [str(p.pattern) for p in config.urls.urlpatterns]
        assert settings.ADMIN_URL not in prefixes
    finally:
        settings.ADMIN_ENABLED = True
        importlib.reload(config.urls)
        clear_url_caches()


def test_admin_requires_staff(client):
    response = client.get(reverse("admin:career_project_changelist"))
    assert response.status_code == 302
    assert "/login/" in response["Location"]
    assert not Project.objects.exists()
