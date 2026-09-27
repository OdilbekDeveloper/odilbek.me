from contextlib import contextmanager

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.models import ImportedRecord, MediaAsset, SiteSettings
from apps.core.selectors import site_settings

pytestmark = pytest.mark.django_db


@contextmanager
def violates(*constraints):
    """The write fails on (any of) these database constraints."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        yield
    assert any(name in str(excinfo.value) for name in constraints)


def test_site_settings_is_a_singleton():
    settings = SiteSettings.load()
    assert settings.pk == 1
    assert SiteSettings.load().pk == 1
    with violates("core_sitesettings_singleton"):
        SiteSettings.objects.create(id=2)


def test_reading_site_settings_never_creates_the_row():
    assert site_settings().pk == 1  # an unsaved default
    assert not SiteSettings.objects.exists()


def test_site_settings_timezone_must_be_real():
    settings = SiteSettings.load()
    settings.timezone = "Mars/Olympus_Mons"
    with pytest.raises(ValidationError):
        settings.full_clean()
    settings.timezone = "Asia/Seoul"
    settings.full_clean()


def test_availability_may_be_unstated_but_not_invented():
    settings = SiteSettings.load()
    assert settings.availability == ""
    with violates("core_sitesettings_availability_valid"):
        SiteSettings.objects.filter(pk=1).update(availability="always")


def _asset(**fields):
    defaults = {
        "file": "images/x.jpg",
        "kind": "image",
        "width": 10,
        "height": 10,
        "bytes": 100,
        "sha256": "a" * 64,
        "alt_text_en": "Example",
    }
    return MediaAsset.objects.create(**{**defaults, **fields})


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"alt_text_en": ""}, "core_mediaasset_image_alt_text_en"),
        ({"sha256": "not-a-hash"}, "core_mediaasset_sha256_hex"),
        ({"focal_x": 1.5}, "core_mediaasset_focal_point_in_range"),
        ({"width": None}, "core_mediaasset_dimensions_match_kind"),
        ({"kind": "pdf"}, "core_mediaasset_dimensions_match_kind"),
        # Refused by the kind list and the dimension rule; either may be reported first.
        ({"kind": "video"}, ("core_mediaasset_kind_valid", "core_mediaasset_dimensions")),
    ],
)
def test_media_asset_invariants(fields, constraint):
    names = constraint if isinstance(constraint, tuple) else (constraint,)
    with violates(*names):
        _asset(**fields)


def test_pdfs_need_no_alt_text():
    _asset(kind="pdf", width=None, height=None, alt_text_en="")


def test_imported_record_keys_are_unique_per_model():
    ImportedRecord.objects.create(model_label="career.project", key="x", object_id=1)
    ImportedRecord.objects.create(model_label="career.skill", key="x", object_id=1)
    with violates("core_importedrecord_unique_key"):
        ImportedRecord.objects.create(model_label="career.project", key="x", object_id=2)
