"""Master-data invariants, proven at the database level.

Most tests write with the ORM's create()/update() and no model validation, so they show the rule
lives in PostgreSQL itself and holds for admin edits, bulk updates and the shell alike.
"""

from contextlib import contextmanager
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.career.models import LanguagePair, Project, Skill
from apps.core.services import publish, unpublish
from tests import helpers as h

pytestmark = pytest.mark.django_db


@contextmanager
def violates(constraint):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        yield
    assert constraint in str(excinfo.value)


# ---------------------------------------------------------------------------
# Slugs, English, choices, links, dates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ["Bad Slug", "UPPER", "trailing-", "-leading", "double--dash"])
def test_slugs_are_lowercase_ascii_words(slug):
    with violates("career_project_slug_format"):
        h.project(slug=slug)


def test_slugs_are_unique():
    h.project()
    with pytest.raises(IntegrityError), transaction.atomic():
        h.project()


def test_english_is_required_at_the_database_level():
    with violates("career_project_title_en"):
        Project.objects.create(slug="no-title", title_en="   ")
    with violates("career_project_title_en"):
        Project.objects.create(slug="null-title", title_ko="한국어만")


def test_korean_and_uzbek_may_stay_empty():
    project = h.project(title_ko=None, title_uz=None)
    project.full_clean()


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://example.com/x", "data:text/html,x"])
def test_links_must_be_http(url):
    with violates("career_project_github_url_http"):
        h.project(github_url=url)


def test_url_fields_reject_other_schemes_in_forms_too():
    project = h.project()
    project.github_url = "ftp://example.com/x"
    with pytest.raises(ValidationError):
        project.full_clean()


def test_choices_are_enforced():
    with violates("career_project_status_valid"):
        h.project(project_status="finished-ish")
    with violates("career_skillcategory_kind_valid"):
        h.category(kind="hobby")


def test_end_date_cannot_precede_start_date():
    with violates("career_project_dates_in_order"):
        h.project(started_on=date(2024, 5, 1), ended_on=date(2023, 1, 1))
    with violates("career_experience_dates_in_order"):
        h.experience(started_on=date(2024, 5, 1), ended_on=date(2023, 1, 1))


def test_contact_channel_needs_a_url_or_handle():
    with violates("career_contactchannel_has_target"):
        h.channel(handle="", url="")


# ---------------------------------------------------------------------------
# Publication integrity
# ---------------------------------------------------------------------------


def test_publish_sets_published_at_and_unpublish_keeps_it():
    project = h.project()
    publish(project)
    first = project.published_at
    assert project.is_published and first is not None
    unpublish(project)
    project.refresh_from_db()
    assert not project.is_published and project.published_at == first


def test_published_records_must_carry_a_publication_date():
    project = h.project()
    with violates("career_project_published_at_set"):
        Project.objects.filter(pk=project.pk).update(is_published=True)


def test_a_record_with_a_todo_cannot_be_published():
    project = h.project(summary_en="TODO(odilbek): write the summary")
    with pytest.raises(ValidationError, match="TODO"):
        publish(project)
    project.refresh_from_db()
    assert not project.is_published


def test_todo_rule_holds_even_for_bulk_updates():
    """The database itself refuses, whatever path the write takes."""
    project = h.project(description_ko="todo(odilbek): 확인 필요")  # any case, any language
    with violates("career_project_no_todo_when_published"):
        Project.objects.filter(pk=project.pk).update(is_published=True, published_at=timezone.now())


def test_project_needs_a_summary_to_publish():
    project = h.project(summary_en="")
    with violates("career_project_summary_to_publish"):
        Project.objects.filter(pk=project.pk).update(is_published=True, published_at=timezone.now())


def test_experience_needs_a_start_date_to_publish():
    """An empty end date means 'current', so a published role must say when it began."""
    role = h.experience(started_on=None)
    with pytest.raises(ValidationError):
        publish(role)


def test_todo_in_a_project_image_caption_blocks_publishing():
    from apps.career.models import ProjectMedia
    from apps.core import media

    project = h.project()
    asset, _ = media.ingest(
        h.upload("x.png", h.image_bytes("PNG", (300, 200))), alt_text_en="Screenshot"
    )
    ProjectMedia.objects.create(project=project, asset=asset, caption_en="TODO(odilbek): caption")
    with pytest.raises(ValidationError, match="Media"):
        publish(project)


# ---------------------------------------------------------------------------
# Language pairs
# ---------------------------------------------------------------------------


def _languages():
    langs = h.language_category()
    return (
        h.skill("example-language-a", langs, name_en="Example Language A"),
        h.skill("example-language-b", langs, name_en="Example Language B"),
    )


def test_language_pair_needs_two_different_languages():
    a, _b = _languages()
    with violates("career_languagepair_distinct"):
        LanguagePair.objects.create(source=a, target=a, modes=["document"])


def test_language_pair_is_unique():
    a, b = _languages()
    LanguagePair.objects.create(source=a, target=b, modes=["document"])
    with violates("career_languagepair_unique"):
        LanguagePair.objects.create(source=a, target=b, modes=["review"])


@pytest.mark.parametrize("modes", [[], ["telepathy"], ["document", "telepathy"]])
def test_language_pair_modes_are_non_empty_and_known(modes):
    a, b = _languages()
    with violates("career_languagepair_modes_valid"):
        LanguagePair.objects.create(source=a, target=b, modes=modes)


def test_language_pair_skills_must_be_spoken_languages():
    a, _b = _languages()
    tech = h.skill("example-framework")
    pair = LanguagePair(source=a, target=tech, modes=["document"])
    with pytest.raises(ValidationError) as excinfo:
        pair.full_clean()
    assert "target" in excinfo.value.message_dict


def test_language_pair_visibility_follows_both_languages():
    a, b = _languages()
    LanguagePair.objects.create(source=a, target=b, modes=["document"])
    assert not LanguagePair.objects.public().exists()
    publish(a)
    assert not LanguagePair.objects.public().exists()
    publish(b)
    assert LanguagePair.objects.public().count() == 1


# ---------------------------------------------------------------------------
# Master data is reused, never copied
# ---------------------------------------------------------------------------


def test_one_skill_serves_many_projects_and_roles():
    python = h.skill("example-language")
    first, second = h.project("example-one"), h.project("example-two")
    first.skills.add(python)
    second.skills.add(python)
    role = h.experience()
    role.skills.add(python)
    role.projects.add(first)
    assert Skill.objects.count() == 1
    assert set(python.projects.all()) == {first, second}
    assert list(first.experiences.all()) == [role]


def test_ordering_is_by_order_then_id():
    later = h.project("example-b", order=2)
    earlier = h.project("example-a", order=1)
    tie = h.project("example-c", order=1)
    assert list(Project.objects.all()) == [earlier, tie, later]
