"""The public query boundary (docs/DATA_MODEL.md, "Visibility semantics").

Every public read goes through a selector built on public(); these tests prove each rule, and
that include_drafts is the only way to see more.
"""

import pytest

from apps.career import selectors as career
from apps.career.models import Project, Skill
from apps.core.services import publish
from apps.profiles import selectors as profiles
from apps.profiles import services
from apps.profiles.models import Profile
from tests import helpers as h

pytestmark = pytest.mark.django_db


def published(obj):
    return publish(obj)


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------


def test_unpublished_records_are_never_public():
    h.project()
    assert list(career.listed_projects()) == []
    with pytest.raises(Project.DoesNotExist):
        career.get_project("example-project")


def test_published_listed_projects_are_listed():
    project = published(h.project())
    assert list(career.listed_projects()) == [project]


def test_unlisted_projects_are_reachable_but_never_listed():
    project = published(h.project(is_listed=False))
    assert list(career.listed_projects()) == []
    assert career.get_project("example-project") == project


def test_drafts_only_with_include_drafts():
    draft = h.project()
    assert list(career.listed_projects(include_drafts=True)) == [draft]
    assert career.get_project("example-project", include_drafts=True) == draft


def test_project_pages_show_only_public_skills():
    project = published(h.project())
    public_skill = published(h.skill("example-public"))
    project.skills.add(public_skill, h.skill("example-draft", h.category("example-other")))
    assert list(career.get_project("example-project").skills.all()) == [public_skill]


def test_unpublished_skill_pages_are_not_found():
    h.skill()
    with pytest.raises(Skill.DoesNotExist):
        career.get_skill("example-skill")


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def test_unpublished_profiles_are_not_found():
    h.profile()
    with pytest.raises(Profile.DoesNotExist):
        profiles.get_role_profile("example-developer")


def test_role_lookup_ignores_home_and_about():
    published(h.profile(slug="home", kind="home"))
    with pytest.raises(Profile.DoesNotExist):
        profiles.get_role_profile("home")
    assert profiles.get_home().slug == "home"


def test_router_offers_everything_but_home():
    published(h.profile(slug="home", kind="home"))
    developer = published(h.profile())
    about = published(h.profile(slug="about", kind="about"))
    assert set(profiles.router_profiles()) == {developer, about}


def test_items_appear_on_a_profile_only_when_linked_and_public():
    profile = published(h.profile())
    linked = published(h.project("example-linked"))
    published(h.project("example-unlinked"))
    draft = h.project("example-draft")
    services.link(profile, linked)
    services.link(profile, draft)
    assert [link.project for link in profiles.profile_projects(profile)] == [linked]


def test_unlisted_projects_never_appear_on_a_profile():
    profile = published(h.profile())
    services.link(profile, published(h.project(is_listed=False)))
    assert list(profiles.profile_projects(profile)) == []


def test_profile_items_follow_the_profile_order():
    profile = published(h.profile())
    first, second = published(h.project("example-first")), published(h.project("example-second"))
    services.link(profile, first)
    services.link(profile, second)
    services.link(profile, first)  # re-linking keeps the original position
    assert [link.project for link in profiles.profile_projects(profile)] == [first, second]


def test_same_item_can_be_public_on_one_profile_and_absent_from_another():
    developer = published(h.profile("example-developer"))
    translator = published(h.profile("example-translator"))
    project = published(h.project())
    services.link(developer, project)
    assert len(profiles.profile_projects(developer)) == 1
    assert len(profiles.profile_projects(translator)) == 0


def test_disabled_sections_never_render_preview_or_not():
    profile = h.profile()
    services.add_section(profile, "about")
    services.add_section(profile, "projects", is_enabled=False)
    assert [s.section_type for s in profiles.profile_sections(profile)] == ["about"]


@pytest.mark.parametrize(
    ("make", "link_selector"),
    [
        (lambda: h.experience(), profiles.profile_experience),
        (lambda: h.education(), profiles.profile_education),
        (lambda: h.service(), profiles.profile_services),
        (lambda: h.channel(), profiles.profile_contact_channels),
        (lambda: h.skill(), profiles.profile_skills),
    ],
)
def test_every_link_selector_hides_drafts(make, link_selector):
    profile = published(h.profile())
    item = make()
    services.link(profile, item)
    assert list(link_selector(profile)) == []
    assert len(link_selector(profile, include_drafts=True)) == 1
    publish(item)
    assert len(link_selector(profile)) == 1
