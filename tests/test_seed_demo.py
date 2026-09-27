"""seed_demo: a complete fictional dataset, loaded through the real importer.

Everything the command creates is invented (apps/profiles/demo_data/brief.md). These tests check
that the dataset exercises the whole Phase 2 model, that it is published exactly where intended,
that every record is identifiable by its provenance, and that it can be repeated and removed
without touching anything else.

Seeding runs thirteen generated images through the media pipeline, which takes seconds, so the
module shares one seeded database. The fixture below holds it in a transaction; each test runs
in a savepoint inside it (pytest-django's usual per-test rollback), and the whole module is rolled
back at the end. A test may change anything: the next test never sees it.
"""

import copy
import io
import re
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import override_settings
from django.utils import translation
from PIL import Image

from apps.career import selectors as career
from apps.career.models import (
    ContactChannel,
    Education,
    EmploymentType,
    Experience,
    LanguagePair,
    Project,
    ProjectMedia,
    Service,
    Skill,
    SkillCategory,
)
from apps.core import media
from apps.core.content import todo_fields
from apps.core.models import ImportedRecord, MediaAsset, SiteSettings
from apps.core.services import publish, unpublish
from apps.core.slugs import RESERVED_SLUGS, validate_not_reserved
from apps.profiles import demo
from apps.profiles import selectors as profiles
from apps.profiles.models import Profile, ProfileExperience, ProfileProject, ProfileSection
from tests import helpers as h

CONTENT_MODELS = (
    MediaAsset,
    SkillCategory,
    Skill,
    Project,
    Experience,
    Education,
    Service,
    LanguagePair,
    ContactChannel,
    Profile,
)
MANIFEST, REVIEW = demo.load_data()
KEPT = REVIEW["keep_unpublished"]


@pytest.fixture(scope="module")
def demo_media(django_db_setup, django_db_blocker, tmp_path_factory):
    """Seed once for the module. Yields the folder the demo's media files were written to."""
    media_root = tmp_path_factory.mktemp("demo-media")
    with django_db_blocker.unblock(), override_settings(MEDIA_ROOT=media_root):
        with transaction.atomic():
            call_command("seed_demo", stdout=io.StringIO())
            yield media_root
            transaction.set_rollback(True)


pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("demo_media")]


def record(model, key):
    obj = demo.demo_record(model, key)
    assert obj is not None, (model, key)
    return obj


def role(slug):
    return Profile.objects.get(slug=slug)


def seed(*args):
    call_command("seed_demo", *args, stdout=io.StringIO())


# ---------------------------------------------------------------------------
# The dataset
# ---------------------------------------------------------------------------


def test_every_manifest_record_is_loaded_and_the_dataset_is_big_enough():
    for section, model in demo.SECTION_MODELS.items():
        assert model.objects.count() == len(MANIFEST[section]), section
    sections = sum(len(p.get("sections", [])) for p in MANIFEST["profiles"])
    assert ProfileSection.objects.count() == sections
    assert Project.objects.public().count() >= 7
    assert 10 <= Skill.objects.public().count() <= 15
    assert 3 <= Experience.objects.public().count() <= 4
    assert 2 <= Education.objects.public().count() <= 3
    assert Profile.objects.public().roles().count() >= 3


def test_role_profiles_use_realistic_slugs_that_no_route_reserves():
    slugs = set(Profile.objects.roles().values_list("slug", flat=True))
    assert {"developer", "translator", "ai-automation"} <= slugs
    for slug in slugs:
        assert slug not in RESERVED_SLUGS
        validate_not_reserved(slug)  # also refuses the admin path configured for this run


def test_one_project_record_serves_several_profiles():
    hanbridge = record(Project, "hanbridge-localization-hub")
    assert Project.objects.filter(title_en=hanbridge.title_en).count() == 1
    shown_on = set(
        hanbridge.profile_links.filter(profile__kind="role").values_list("profile__slug", flat=True)
    )
    assert shown_on == {"developer", "translator", "ai-automation"}
    shared = [
        p
        for p in Project.objects.all()
        if p.profile_links.filter(profile__kind="role").count() >= 2
    ]
    assert len(shared) >= 2


def test_each_role_profile_shows_enough_public_projects():
    shown = {
        slug: [link.project.slug for link in profiles.profile_projects(role(slug))]
        for slug in ("developer", "translator", "ai-automation")
    }
    assert len(shown["developer"]) >= 3
    assert len(shown["translator"]) >= 3
    assert len(shown["ai-automation"]) >= 2


def test_every_project_has_exactly_one_primary_profile():
    for project in Project.objects.all():
        assert project.profile_links.filter(is_primary=True).count() == 1, project.slug


def test_skills_and_roles_are_reused_not_copied():
    python = record(Skill, "python")
    assert python.projects.count() >= 5
    assert python.experiences.count() >= 2
    assert python.profile_links.count() >= 3
    names = list(Skill.objects.values_list("name_en", flat=True))
    assert len(names) == len(set(names))
    cobaltine = record(Experience, "cobaltine-automation-engineer")
    shown_on = set(cobaltine.profile_links.values_list("profile__slug", flat=True))
    assert shown_on == {"about", "developer", "translator", "ai-automation"}


def test_one_record_is_worded_differently_on_each_profile():
    booking = record(Project, "northgale-booking-platform")
    on_developer = ProfileProject.objects.get(profile=role("developer"), project=booking)
    on_translator = ProfileProject.objects.get(profile=role("translator"), project=booking)
    assert on_developer.effective_summary == booking.summary
    assert on_translator.effective_summary != booking.summary
    cobaltine = record(Experience, "cobaltine-automation-engineer")
    wording = {
        link.profile.slug: (link.effective_summary, link.effective_highlights)
        for link in cobaltine.profile_links.select_related("profile")
    }
    assert len(set(wording.values())) == len(wording) == 4


def test_the_timeline_is_consistent():
    for role_record in Experience.objects.all():
        end = role_record.ended_on or date.today()
        for project in role_record.projects.all():
            assert role_record.started_on <= project.started_on <= end, (role_record, project)
    for item in (*Project.objects.all(), *Experience.objects.all(), *Education.objects.all()):
        if item.started_on and item.ended_on:
            assert item.started_on <= item.ended_on, item


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


def test_exactly_the_intended_drafts_stay_unpublished():
    for section in demo.PUBLISH_ORDER:
        model = demo.SECTION_MODELS[section]
        for entry in MANIFEST[section]:
            key = entry.get("slug") or entry["key"]
            assert record(model, key).is_published is (key not in KEPT.get(section, [])), key


def test_project_and_skill_selectors_hide_drafts_and_list_no_unlisted_project():
    listed = {project.slug for project in career.listed_projects()}
    assert "pulsetrack-clinical-data-prototype" not in listed
    assert "ledgerline-reconciliation-service" not in listed
    # Unlisted: reachable at its own URL only.
    assert career.get_project("ledgerline-reconciliation-service")
    with pytest.raises(Project.DoesNotExist):
        career.get_project("pulsetrack-clinical-data-prototype")
    assert career.get_project("pulsetrack-clinical-data-prototype", include_drafts=True)
    with pytest.raises(Skill.DoesNotExist):
        career.get_skill("rust")


def test_profile_selectors_show_only_public_linked_items():
    developer, translator = role("developer"), role("translator")
    shown = {link.project.slug for link in profiles.profile_projects(developer)}
    assert shown.isdisjoint(
        {"pulsetrack-clinical-data-prototype", "ledgerline-reconciliation-service"}
    )
    previewed = {
        link.project.slug for link in profiles.profile_projects(developer, include_drafts=True)
    }
    assert "pulsetrack-clinical-data-prototype" in previewed
    assert "ledgerline-reconciliation-service" not in previewed  # unlisted, preview or not
    assert "rust" not in {link.skill.slug for link in profiles.profile_skills(developer)}
    organizations = {
        link.experience.organization_en for link in profiles.profile_experience(translator)
    }
    assert "Lantern Street Language Café" not in organizations
    assert "subtitle-localization" not in {
        link.service.slug for link in profiles.profile_services(translator)
    }
    assert "kakaotalk" not in {
        link.channel.kind for link in profiles.profile_contact_channels(translator)
    }


def test_profile_and_section_visibility():
    with pytest.raises(Profile.DoesNotExist):
        profiles.get_role_profile("technical-writer")
    switcher = {profile.slug for profile in profiles.switcher_profiles()}
    router = {profile.slug for profile in profiles.router_profiles()}
    assert "technical-writer" not in switcher
    assert "ai-automation" in switcher and "ai-automation" not in router
    developer_sections = {s.section_type for s in profiles.profile_sections(role("developer"))}
    translator_sections = {s.section_type for s in profiles.profile_sections(role("translator"))}
    assert "resume_cta" not in developer_sections
    assert "custom_markdown" not in translator_sections


def test_drafts_carrying_todo_notes_cannot_be_published():
    pulsetrack = record(Project, "pulsetrack-clinical-data-prototype")
    writer = record(Profile, "technical-writer")
    assert "TODO(odilbek)" in pulsetrack.description_en
    assert "TODO(odilbek)" in writer.headline_en
    for draft in (pulsetrack, writer):
        with pytest.raises(ValidationError):
            publish(draft)
    for model in (Skill, Project, Experience, Education, Service, ContactChannel, Profile):
        for obj in model.objects.public():
            assert not todo_fields(obj), obj


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------


def test_korean_where_it_was_written_and_english_where_it_was_not():
    with translation.override("ko"):
        assert record(Project, "atlas-workflow-engine").title == "아틀라스 워크플로 엔진"
        assert record(Skill, "python").name == "Python"
        beacon = record(Project, "beacon-operations-console")
        assert beacon.description == beacon.description_en
        assert record(Profile, "ai-automation").name == "AI and Automation"
    assert role("translator").languages == ["en", "ko"]
    assert role("ai-automation").languages == ["en"]


def test_an_override_never_borrows_another_languages_wording():
    cobaltine = record(Experience, "cobaltine-automation-engineer")
    link = ProfileExperience.objects.get(profile=role("translator"), experience=cobaltine)
    assert link.summary_override_en
    with translation.override("en"):
        assert link.effective_summary == link.summary_override_en
    with translation.override("ko"):
        assert link.effective_summary == cobaltine.summary_ko


def test_korean_is_real_text_and_there_is_no_uzbek_yet():
    hangul = re.compile(r"[가-힣]")
    for project in Project.objects.public():
        assert hangul.search(project.title_ko or ""), project.slug
        assert hangul.search(project.summary_ko or ""), project.slug
    for model in (*CONTENT_MODELS, ProfileSection, ProfileProject, ProfileExperience, ProjectMedia):
        uzbek = [f.name for f in model._meta.concrete_fields if f.name.endswith("_uz")]
        for obj in model.objects.all():
            assert not any(getattr(obj, name) for name in uzbek), obj


def test_the_dataset_keeps_its_layout_stress_cases():
    titles = list(Project.objects.values_list("title_en", "title_ko"))
    assert max(len(en) for en, _ko in titles) >= 60
    assert max(len(ko or "") for _en, ko in titles) >= 40
    assert max(len(e.organization_en) for e in Experience.objects.all()) >= 60
    skill_counts = [project.skills.count() for project in Project.objects.public()]
    assert max(skill_counts) >= 9
    assert min(skill_counts) <= 2
    assert max(len(p.description_ko or "") for p in Project.objects.all()) >= 500
    assert set(Experience.objects.values_list("employment_type", flat=True)) == set(
        EmploymentType.values
    )
    assert Experience.objects.public().filter(ended_on=None).exists()  # a current role


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


def test_every_image_went_through_the_pipeline(demo_media):
    for entry in MANIFEST["media"]:
        asset = record(MediaAsset, entry["key"])
        assert asset.kind == "image"
        widths = asset.variant_widths("avif")
        assert widths == asset.variant_widths("webp")
        assert widths and max(widths) <= asset.width
        for name in media.asset_file_names(asset):
            assert (demo_media / name).is_file(), name
    assert record(MediaAsset, "atlas-cover").variant_widths("webp") == [480, 960, 1440, 1920]
    assert record(MediaAsset, "quickform-cover").variant_widths("webp") == [320]


def test_the_portraits_camera_data_is_stripped_and_its_rotation_applied(demo_media):
    with Image.open(io.BytesIO(demo.image_bytes(demo.PORTRAIT))) as source:
        assert source.size == (1500, 1200)  # stored on its side, like a phone photo
        assert source.getexif()[0x0112] == 6
        assert source.getexif().get_ifd(0x8825)  # GPS
    portrait = SiteSettings.objects.get().portrait
    assert (portrait.width, portrait.height) == (1200, 1500)
    for name in media.asset_file_names(portrait):
        with Image.open(demo_media / name) as stored:
            assert len(stored.getexif()) == 0, name


def test_images_are_attached_where_the_data_uses_them():
    site = SiteSettings.objects.get()
    assert site.portrait == record(MediaAsset, "portrait")
    assert site.default_og_image == record(MediaAsset, "og-default")
    assert role("translator").hero_image == record(MediaAsset, "hero-translator")
    assert role("developer").hero_image is None  # falls back to the site portrait
    assert role("developer").og_image == record(MediaAsset, "atlas-cover")
    assert 0 < Project.objects.exclude(cover=None).count() < Project.objects.count()
    gallery = list(record(Project, "atlas-workflow-engine").media.order_by("order"))
    assert [row.asset for row in gallery] == [
        record(MediaAsset, "atlas-queue"),
        record(MediaAsset, "atlas-retries"),
    ]
    assert all(row.caption_en and row.caption_ko for row in gallery)


# ---------------------------------------------------------------------------
# Provenance, repetition, removal
# ---------------------------------------------------------------------------


def test_every_demo_record_is_identified_by_its_provenance():
    assert demo.foreign_content() == []
    for model in CONTENT_MODELS:
        tracked = ImportedRecord.objects.filter(origin="demo", model_label=model._meta.label_lower)
        assert set(tracked.values_list("object_id", flat=True)) == set(
            model.objects.values_list("pk", flat=True)
        ), model
    assert ImportedRecord.objects.filter(origin="demo", model_label="core.sitesettings").exists()
    assert not ImportedRecord.objects.exclude(origin="demo").exists()


def test_a_rerun_changes_nothing_and_keeps_edits():
    models = (*CONTENT_MODELS, ProfileSection, ProfileProject, ProjectMedia, ImportedRecord)

    def snapshot():
        return {model.__name__: model.objects.count() for model in models}

    before = snapshot()
    Project.objects.filter(pk=record(Project, "atlas-workflow-engine").pk).update(
        title_en="Edited by hand"
    )
    unpublish(record(Skill, "docker"))
    seed()
    assert snapshot() == before
    assert record(Project, "atlas-workflow-engine").title_en == "Edited by hand"
    assert record(Skill, "docker").is_published is False


def test_reset_removes_exactly_the_demo_records_and_a_new_seed_works(
    django_capture_on_commit_callbacks, isolated_media
):
    hand_made = h.skill(slug="hand-made-skill")  # not demo content
    seed("--reset")
    assert list(Skill.objects.all()) == [hand_made]
    assert list(SkillCategory.objects.all()) == [hand_made.category]
    for model in (*CONTENT_MODELS, SiteSettings, ProfileSection, ProfileProject, ProjectMedia):
        if model not in (Skill, SkillCategory):
            assert not model.objects.exists(), model
    assert not ImportedRecord.objects.exists()

    # With nothing else in the database, the demo loads again from scratch...
    hand_made.delete()
    hand_made.category.delete()
    seed()
    assert Project.objects.count() == len(MANIFEST["projects"])
    assert any(path.is_file() for path in isolated_media.rglob("*"))
    # ...and removing it deletes its files too, once the transaction commits.
    with django_capture_on_commit_callbacks(execute=True):
        seed("--reset")
    assert not any(path.is_file() for path in isolated_media.rglob("*"))


def test_seed_refuses_a_database_holding_other_content():
    h.project(slug="a-real-project")
    with pytest.raises(CommandError, match="not the demo's"):
        seed()


def test_seed_refuses_a_database_holding_real_drafts():
    ImportedRecord.objects.create(
        model_label="career.project", key="a-real-draft", object_id=10**9, origin="draft"
    )
    with pytest.raises(CommandError, match="draft_content"):
        seed()


def test_seed_refuses_settings_that_do_not_allow_demo_content(settings):
    settings.DEMO_CONTENT_ALLOWED = False
    with pytest.raises(CommandError, match="DEMO_CONTENT_ALLOWED"):
        seed()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda r: r["projects"]["atlas-workflow-engine"].update(featured=True), "unknown field"),
        (lambda r: r["keep_unpublished"]["projects"].append("no-such-project"), "not in the"),
        (
            lambda r: r["links"].append(
                {"profile": "developer", "project": "smart-port-terminology-glossary"}
            ),
            "only rewords existing links",
        ),
    ],
)
def test_a_mistake_in_the_review_file_is_an_error_not_a_silent_no_op(monkeypatch, change, message):
    review = copy.deepcopy(REVIEW)
    change(review)
    monkeypatch.setattr(demo, "load_data", lambda: (copy.deepcopy(MANIFEST), review))
    with pytest.raises(CommandError, match=message):
        seed()


def test_demo_data_uses_only_reserved_example_domains():
    text = "\n".join(
        (demo.DATA_DIR / name).read_text(encoding="utf-8")
        for name in ("manifest.json", "review.json", "brief.md")
    )
    hosts = re.findall(r"https?://([^/\s\"]+)", text)
    emails = re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text)
    assert hosts and emails
    for host in hosts + emails:
        assert re.search(r"(^|\.)example\.(com|org|net)$", host), host
