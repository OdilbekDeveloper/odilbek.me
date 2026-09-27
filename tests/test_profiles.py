"""Profiles are data: curated views over shared master data, never copies of it."""

import re
from contextlib import contextmanager

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.career.models import Project
from apps.core.constraints import SLUG_PATTERN
from apps.core.models import SiteSettings
from apps.core.services import publish
from apps.core.slugs import RESERVED_SLUGS
from apps.profiles import services
from apps.profiles.models import (
    Profile,
    ProfileContactChannel,
    ProfileProject,
    ProfileSection,
    SectionType,
)
from tests import helpers as h

pytestmark = pytest.mark.django_db


@contextmanager
def violates(*constraints):
    """The write fails on (any of) these database constraints."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        yield
    assert any(name in str(excinfo.value) for name in constraints)


# ---------------------------------------------------------------------------
# Slugs and kinds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", sorted(s for s in RESERVED_SLUGS if re.fullmatch(SLUG_PATTERN, s)))
def test_role_profiles_cannot_take_a_reserved_slug(slug):
    # (Reserved names such as 'sitemap.xml' could never be slugs anyway: the format forbids dots.)
    with violates("profiles_profile_slug_not_reserved"):
        h.profile(slug=slug)


def test_reserved_slug_is_also_reported_as_a_form_error():
    profile = Profile(slug="projects", kind="role", name_en="Example")
    with pytest.raises(ValidationError) as excinfo:
        profile.full_clean()
    assert "slug" in excinfo.value.message_dict


def test_the_configured_admin_path_is_reserved_too(settings):
    settings.ADMIN_URL = "back-office/"
    with pytest.raises(ValidationError) as excinfo:
        Profile(slug="back-office", kind="role", name_en="Example").full_clean()
    assert "slug" in excinfo.value.message_dict


def test_home_and_about_have_fixed_routes_so_any_slug_is_fine():
    h.profile(slug="about", kind="about", name_en="About")
    h.profile(slug="home", kind="home", name_en="Home")


def test_at_most_one_home_and_one_about():
    h.profile(slug="home", kind="home")
    with violates("profiles_profile_one_home"):
        h.profile(slug="home-two", kind="home")
    h.profile(slug="about", kind="about")
    with violates("profiles_profile_one_about"):
        h.profile(slug="about-two", kind="about")


def test_many_role_profiles_are_allowed():
    h.profile("example-developer")
    h.profile("example-translator")
    assert Profile.objects.roles().count() == 2


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------


def test_english_is_always_a_profile_language():
    with violates("profiles_profile_languages_valid"):
        h.profile(languages=["ko"])


def test_only_site_languages_are_allowed():
    with violates("profiles_profile_languages_valid"):
        h.profile(languages=["en", "fr"])


def test_languages_are_normalised():
    profile = Profile(slug="example-x", kind="role", name_en="X", languages=["ko", "ko", "uz"])
    profile.full_clean()
    assert profile.languages == ["en", "ko", "uz"]


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def test_sections_are_appended_in_order():
    profile = h.profile()
    for section_type in ("about", "projects", "contact"):
        services.add_section(profile, section_type)
    assert [s.section_type for s in profile.sections.all()] == ["about", "projects", "contact"]
    assert [s.order for s in profile.sections.all()] == [1, 2, 3]


def test_profile_router_is_for_the_home_profile_only():
    with pytest.raises(ValidationError):
        services.add_section(h.profile(), SectionType.PROFILE_ROUTER)
    home = h.profile(slug="home", kind="home")
    services.add_section(home, SectionType.PROFILE_ROUTER)


def test_home_with_a_router_cannot_become_a_role():
    home = h.profile(slug="home", kind="home")
    services.add_section(home, SectionType.PROFILE_ROUTER)
    home.kind = "role"
    with pytest.raises(ValidationError) as excinfo:
        home.full_clean()
    assert "kind" in excinfo.value.message_dict


def test_one_section_per_type_except_custom_text():
    profile = h.profile()
    services.add_section(profile, "about")
    with violates("profiles_profilesection_one_per_type"):
        ProfileSection.objects.create(profile=profile, section_type="about")
    ProfileSection.objects.create(profile=profile, section_type="custom_markdown", body_en="A")
    ProfileSection.objects.create(profile=profile, section_type="custom_markdown", body_en="B")


def test_unknown_section_types_are_refused():
    # Refused twice over (the type list and the layout map); PostgreSQL reports whichever it
    # checks first. career_map only becomes a type in Phase 11.
    with violates("profiles_profilesection_type_valid", "profiles_profilesection_layout_valid"):
        ProfileSection.objects.create(profile=h.profile(), section_type="career_map")


def test_only_custom_text_sections_have_a_body():
    with violates("profiles_profilesection_body_custom_only"):
        ProfileSection.objects.create(profile=h.profile(), section_type="about", body_ko="본문")


@pytest.mark.parametrize(("section_type", "limit"), [("about", 3), ("projects", 0)])
def test_item_limit_only_on_list_sections_and_positive(section_type, limit):
    with violates("profiles_profilesection_item_limit_valid"):
        ProfileSection.objects.create(
            profile=h.profile(), section_type=section_type, item_limit=limit
        )


def test_layout_variant_must_suit_the_section_type():
    with violates("profiles_profilesection_layout_valid"):
        ProfileSection.objects.create(
            profile=h.profile(), section_type="projects", layout_variant="carousel"
        )


def test_anchors_are_slug_like_and_unique_per_profile():
    profile = h.profile()
    with violates("profiles_profilesection_anchor_format"):
        ProfileSection.objects.create(profile=profile, section_type="about", anchor="Bad Anchor")
    ProfileSection.objects.create(profile=profile, section_type="about", anchor="intro")
    with violates("profiles_profilesection_anchor_unique"):
        ProfileSection.objects.create(profile=profile, section_type="skills", anchor="intro")


def test_a_section_with_a_todo_cannot_be_enabled():
    profile = h.profile()
    with violates("profiles_profilesection_no_todo_when_enabled"):
        ProfileSection.objects.create(
            profile=profile, section_type="about", heading_en="TODO(odilbek): heading"
        )
    ProfileSection.objects.create(
        profile=profile,
        section_type="about",
        heading_en="TODO(odilbek): heading",
        is_enabled=False,
    )


# ---------------------------------------------------------------------------
# Links and overrides
# ---------------------------------------------------------------------------


def test_linking_never_copies_the_item():
    project = h.project()
    developer, translator = h.profile("example-developer"), h.profile("example-translator")
    services.link(developer, project, summary_override_en="Worded for developers")
    services.link(translator, project)
    assert Project.objects.count() == 1
    assert ProfileProject.objects.count() == 2


def test_linking_twice_updates_rather_than_duplicates():
    project, profile = h.project(), h.profile()
    services.link(profile, project)
    services.link(profile, project, is_featured=True)
    assert ProfileProject.objects.get().is_featured


def test_each_pair_is_unique():
    project, profile = h.project(), h.profile()
    ProfileProject.objects.create(profile=profile, project=project)
    with violates("profiles_profileproject_pair"):
        ProfileProject.objects.create(profile=profile, project=project)


def test_a_project_has_at_most_one_primary_profile():
    project = h.project()
    developer, translator = h.profile("example-developer"), h.profile("example-translator")
    ProfileProject.objects.create(profile=developer, project=project, is_primary=True)
    with violates("profiles_profileproject_one_primary"):
        ProfileProject.objects.create(profile=translator, project=project, is_primary=True)


def test_set_primary_profile_moves_it():
    project = h.project()
    developer, translator = h.profile("example-developer"), h.profile("example-translator")
    services.link(developer, project)
    services.link(translator, project)
    services.set_primary_profile(project, developer)
    services.set_primary_profile(project, translator)
    assert ProfileProject.objects.get(is_primary=True).profile == translator


def test_the_primary_profile_must_show_the_project():
    with pytest.raises(ProfileProject.DoesNotExist):
        services.set_primary_profile(h.project(), h.profile())


def test_a_profile_has_at_most_one_primary_channel():
    profile = h.profile()
    ProfileContactChannel.objects.create(profile=profile, channel=h.channel(), is_primary=True)
    other = h.channel(kind="telegram", handle="@example", label_en="Telegram")
    with violates("profiles_profilechannel_one_primary"):
        ProfileContactChannel.objects.create(profile=profile, channel=other, is_primary=True)


def test_override_falls_back_to_the_item_not_to_another_language():
    from django.utils import translation

    project = h.project(summary_en="Own summary", summary_ko="자체 요약")
    link = services.link(h.profile(), project, summary_override_en="Developer wording")
    with translation.override("en"):
        assert link.effective_summary == "Developer wording"
    with translation.override("ko"):
        # No Korean override: the project's own Korean text, not the English override.
        assert link.effective_summary == "자체 요약"


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------


def test_profile_needs_a_headline_to_publish():
    profile = h.profile(headline_en="")
    with violates("profiles_profile_headline_to_publish"):
        Profile.objects.filter(pk=profile.pk).update(is_published=True, published_at=timezone.now())


def test_todo_in_a_link_override_blocks_publishing():
    profile = h.profile()
    services.link(profile, h.project(), summary_override_en="TODO(odilbek): wording")
    with pytest.raises(ValidationError, match="override"):
        publish(profile)


def test_todo_in_site_settings_blocks_publishing_any_profile():
    site = SiteSettings.load()
    site.owner_name_en = "TODO(odilbek): name"
    site.save()
    with pytest.raises(ValidationError, match="Site settings"):
        publish(h.profile())


def test_a_clean_profile_publishes():
    profile = publish(h.profile())
    assert profile.is_published and profile.published_at
