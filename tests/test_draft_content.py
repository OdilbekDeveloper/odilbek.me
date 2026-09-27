"""draft_content: private sources in, unpublished drafts out, nothing invented.

Everything here is fictional: a made-up source text and a generated image in a temporary folder
outside the repository.
"""

import copy
import io
import json

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from apps.career.models import Experience, Project, Skill
from apps.core.models import ImportedRecord, MediaAsset
from apps.core.services import publish
from apps.profiles.drafting import ManifestError, check_root
from apps.profiles.models import Profile, ProfileProject
from tests import helpers as h

pytestmark = pytest.mark.django_db

MANIFEST = {
    "schema": 1,
    "sources": {"cv": "example-cv.txt", "photo": "portraits/example.jpg"},
    "media": [
        {
            "key": "portrait",
            "file": "portraits/example.jpg",
            "alt_text": {"en": "Example Person"},
            "focal": [0.5, 0.3],
            "sources": ["photo"],
        }
    ],
    "skill_categories": [
        {
            "slug": "example-backend",
            "kind": "technical",
            "name": {"en": "Backend"},
            "sources": ["cv"],
        }
    ],
    "skills": [
        {
            "slug": "example-lang",
            "category": "example-backend",
            "name": {"en": "Examplescript"},
            "sources": ["cv"],
        }
    ],
    "projects": [
        {
            "slug": "example-one",
            "title": {"en": "Example One"},
            "summary": {"en": "A fictional tool."},
            "skills": ["example-lang"],
            "started_on": "2021-03",
            "sources": ["cv"],
        },
        {
            "slug": "example-two",
            "title": {"en": "Example Two"},
            "skills": ["example-lang"],
            "sources": ["cv"],
        },
    ],
    "experience": [
        {
            "key": "fictional-co",
            "role": {"en": "Example Engineer"},
            "organization": {"en": "Fictional Company"},
            "started_on": "2019",
            "skills": ["example-lang"],
            "projects": ["example-one"],
            "sources": ["cv"],
        }
    ],
    "profiles": [
        {
            "slug": "example-developer",
            "kind": "role",
            "name": {"en": "Example Developer"},
            "hero_image": "portrait",
            "languages": ["en", "ko"],
            "sections": [{"type": "about"}, {"type": "projects"}],
            "projects": [{"slug": "example-one", "is_primary": True}, {"slug": "example-two"}],
            "experience": ["fictional-co"],
            "sources": ["cv"],
        },
        {
            "slug": "example-writer",
            "kind": "role",
            "name": {"en": "Example Writer"},
            "headline": {"en": "A fictional headline"},
            "projects": [{"slug": "example-one"}],
            "sources": ["cv"],
        },
    ],
}


@pytest.fixture
def source_root(tmp_path):
    root = tmp_path / "private-source"
    (root / "portraits").mkdir(parents=True)
    (root / "example-cv.txt").write_text("A fictional CV for tests.", encoding="utf-8")
    (root / "portraits" / "example.jpg").write_bytes(h.jpeg_with_gps((1200, 800)))
    return root


def run(root, manifest=None, *args):
    (root / "draft.json").write_text(json.dumps(manifest or MANIFEST), encoding="utf-8")
    call_command("draft_content", "--root", str(root), *args)


def mutated(change):
    manifest = copy.deepcopy(MANIFEST)
    change(manifest)
    return manifest


# ---------------------------------------------------------------------------
# What an import produces
# ---------------------------------------------------------------------------


def test_everything_imported_is_unpublished(source_root):
    run(source_root)
    assert Project.objects.count() == 2
    assert Profile.objects.count() == 2
    assert ImportedRecord.objects.count() >= 8
    for record in ImportedRecord.objects.all():
        obj = apps.get_model(record.model_label).objects.get(pk=record.object_id)
        assert getattr(obj, "is_published", False) is False, record


def test_missing_facts_become_todos_not_guesses(source_root):
    run(source_root)
    role = Experience.objects.get()
    assert role.started_on.year == 2019
    assert "TODO(odilbek): the sources give only the year for started_on" in role.summary_en
    assert "TODO(odilbek): the sources do not give an end date" in role.summary_en
    assert (
        "TODO(odilbek): write a one-line summary"
        in Project.objects.get(slug="example-two").summary_en
    )
    assert (
        "TODO(odilbek): write the headline"
        in Profile.objects.get(slug="example-developer").headline_en
    )


def test_nothing_is_filled_in_that_the_manifest_does_not_state(source_root):
    run(source_root)
    project = Project.objects.get(slug="example-one")
    assert project.role_en in ("", None)
    assert project.github_url == ""
    assert project.project_status == ""
    assert Experience.objects.get().location_en in ("", None)


def test_drafts_with_todos_cannot_be_published(source_root):
    from django.core.exceptions import ValidationError

    run(source_root)
    with pytest.raises(ValidationError):
        publish(Experience.objects.get())


def test_master_records_are_reused_not_duplicated(source_root):
    run(source_root)
    assert Skill.objects.count() == 1
    assert Skill.objects.get().projects.count() == 2
    assert ProfileProject.objects.filter(project__slug="example-one").count() == 2
    assert ProfileProject.objects.get(is_primary=True).profile.slug == "example-developer"


def test_portraits_go_through_the_media_pipeline(source_root):
    run(source_root)
    asset = MediaAsset.objects.get()
    assert Profile.objects.get(slug="example-developer").hero_image == asset
    with default_storage.open(asset.file.name) as handle:
        assert len(Image.open(io.BytesIO(handle.read())).getexif()) == 0
    assert (asset.focal_x, asset.focal_y) == (0.5, 0.3)


# ---------------------------------------------------------------------------
# Re-runs
# ---------------------------------------------------------------------------


def test_rerunning_creates_nothing_new(source_root):
    run(source_root)
    before = (Project.objects.count(), Experience.objects.count(), MediaAsset.objects.count())
    run(source_root)
    after = (Project.objects.count(), Experience.objects.count(), MediaAsset.objects.count())
    assert before == after


def test_edits_made_in_the_admin_survive_a_rerun(source_root):
    run(source_root)
    Project.objects.filter(slug="example-one").update(title_en="Edited by hand")
    run(source_root)
    assert Project.objects.get(slug="example-one").title_en == "Edited by hand"


def test_update_refreshes_unpublished_drafts_only(source_root):
    run(source_root)
    Project.objects.filter(slug="example-one").update(title_en="Edited one")
    Project.objects.filter(slug="example-two").update(title_en="Edited two")
    publish(Project.objects.get(slug="example-one"))
    run(source_root, None, "--update")
    assert Project.objects.get(slug="example-one").title_en == "Edited one"  # published: untouched
    assert Project.objects.get(slug="example-two").title_en == "Example Two"  # draft: refreshed


def test_a_deleted_draft_is_not_recreated(source_root):
    run(source_root)
    Project.objects.filter(slug="example-two").delete()
    run(source_root)
    assert not Project.objects.filter(slug="example-two").exists()


def test_dry_run_writes_nothing(source_root):
    run(source_root, None, "--dry-run")
    assert not Project.objects.exists()
    assert not MediaAsset.objects.exists()
    assert not ImportedRecord.objects.exists()


# ---------------------------------------------------------------------------
# Rejected manifests write nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda m: m["projects"][0].update(is_published=True), "never set publication"),
        (lambda m: m["projects"][0].update(tagline="x"), "unknown field"),
        (lambda m: m["projects"][0].pop("sources"), "cite at least one source"),
        (lambda m: m["projects"][0].update(sources=["rumour"]), "not a declared source"),
        (lambda m: m["sources"].update(missing="no-such-file.pdf"), "file not found"),
        (lambda m: m["media"][0].update(file="../outside.jpg"), "inside the content-import"),
        (lambda m: m["projects"][0].update(started_on="March 2021"), "YYYY"),
        (lambda m: m["projects"][0].update(slug="Not A Slug"), "slug"),
        (lambda m: m["projects"][0].update(skills=["unknown-skill"]), "unknown skill"),
        (lambda m: m["projects"][0].update(github_url="javascript:x"), "http"),
        (lambda m: m.update(schema=2), "schema"),
    ],
)
def test_invalid_manifests_are_rejected_before_anything_is_written(source_root, change, message):
    with pytest.raises(CommandError, match=message):
        run(source_root, mutated(change))
    assert not Project.objects.exists()
    assert not MediaAsset.objects.exists()


def test_a_hostile_media_file_rejects_the_whole_import(source_root):
    (source_root / "portraits" / "example.jpg").write_bytes(
        h.image_bytes() + b"<script>alert(1)</script>"
    )
    with pytest.raises(CommandError, match="scripting"):
        run(source_root)
    assert not Project.objects.exists()


def test_private_sources_must_not_live_in_the_repository_outside_content_import():
    with pytest.raises(ManifestError, match="not the git-ignored"):
        check_root(settings.BASE_DIR / "docs")
