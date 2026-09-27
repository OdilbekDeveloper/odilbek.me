"""Field-level translations (D-015).

English is required; Korean and Uzbek are optional and fall back to English.
"""

import pytest
from django.forms import modelform_factory
from django.utils import translation

from apps.career.models import Project
from tests import helpers as h

pytestmark = pytest.mark.django_db


def test_each_translated_field_has_a_column_per_site_language():
    names = {field.name for field in Project._meta.get_fields()}
    assert {"title_en", "title_ko", "title_uz"} <= names


def test_slugs_are_never_translated():
    names = {field.name for field in Project._meta.get_fields()}
    assert "slug" in names
    assert not any(name.startswith("slug_") for name in names)


def test_forms_require_english_only():
    form_class = modelform_factory(Project, fields=["slug", "title_en", "title_ko", "title_uz"])
    form = form_class()
    assert form.fields["title_en"].required
    assert not form.fields["title_ko"].required
    assert not form.fields["title_uz"].required


def test_korean_is_used_when_present():
    project = h.project(title_en="Example Project", title_ko="예시 프로젝트")
    with translation.override("ko"):
        assert Project.objects.get(pk=project.pk).title == "예시 프로젝트"


def test_missing_korean_falls_back_to_english():
    project = h.project(title_en="Example Project")
    with translation.override("ko"):
        assert Project.objects.get(pk=project.pk).title == "Example Project"


def test_uzbek_exists_without_content_and_falls_back():
    project = h.project(title_en="Example Project")
    assert project.title_uz is None
    with translation.override("uz"):
        assert Project.objects.get(pk=project.pk).title == "Example Project"


def test_optional_fields_stay_optional_in_every_language():
    form_class = modelform_factory(Project, fields=["context_en", "context_ko"])
    form = form_class()
    assert not form.fields["context_en"].required
