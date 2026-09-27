"""seed_demo: obviously fictional, repeatable, and never mixed with real content."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.career.models import ContactChannel, Education, Experience, Project, Skill
from apps.core.models import MediaAsset, SiteSettings
from apps.profiles.models import Profile, ProfileProject, ProfileSection
from tests import helpers as h

pytestmark = pytest.mark.django_db

COUNTED = (Skill, Project, Experience, Education, ContactChannel, Profile, ProfileSection)


def counts():
    return {model.__name__: model.objects.count() for model in (*COUNTED, ProfileProject)}


def test_seed_creates_a_complete_fictional_site():
    call_command("seed_demo")
    assert Profile.objects.filter(kind="home").exists()
    assert Profile.objects.filter(kind="about").exists()
    assert Profile.objects.roles().count() == 2
    assert Project.objects.filter(is_listed=False).exists()
    assert MediaAsset.objects.count() == 1
    assert Profile.objects.public().count() == 4


def test_seed_is_idempotent():
    call_command("seed_demo")
    first = counts()
    call_command("seed_demo")
    assert counts() == first


def test_demo_content_is_obviously_fake():
    call_command("seed_demo")
    for model in (Skill, Project, Profile):
        assert all(
            slug.startswith("demo-") for slug in model.objects.values_list("slug", flat=True)
        )
    handles = ContactChannel.objects.values_list("handle", "url")
    assert all("example.com" in handle + url for handle, url in handles)
    assert SiteSettings.load().owner_name_en == "Alex Demo"
    assert SiteSettings.load().public_email.endswith("@example.com")


def test_seed_refuses_a_database_with_real_content():
    h.project(slug="a-real-project")
    with pytest.raises(CommandError, match="real"):
        call_command("seed_demo")
    assert not Profile.objects.exists()


def test_reset_removes_every_demo_record(django_capture_on_commit_callbacks):
    call_command("seed_demo")
    with django_capture_on_commit_callbacks(execute=True):
        call_command("seed_demo", "--reset")
    assert all(count == 0 for count in counts().values())
    assert not MediaAsset.objects.exists()
    assert not SiteSettings.objects.exists()
