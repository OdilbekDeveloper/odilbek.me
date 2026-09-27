"""The draft-content marker.

A fact that the source material does not establish is never guessed: it is written as
`TODO(odilbek): <what is missing>`. A record containing the marker cannot be published. The
database enforces this for each record's own text (apps/core/constraints.py), and the publish
service checks the related text a record displays (apps/core/services.py).
"""

from django.conf import settings
from django.db import models

TODO_MARKER = "TODO(odilbek"


def language_codes():
    return [code for code, _name in settings.LANGUAGES]


def localized(field):
    """'title' -> ['title_en', 'title_ko', 'title_uz']: the columns modeltranslation adds."""
    return [f"{field}_{code}" for code in language_codes()]


def contains_todo(value):
    return isinstance(value, str) and TODO_MARKER.lower() in value.lower()


def text_field_names(model):
    """Every concrete text column of a model, translation columns included."""
    return [
        field.name
        for field in model._meta.concrete_fields
        if isinstance(field, models.CharField | models.TextField)
    ]


def todo_fields(instance):
    """Names of this record's own text fields that still contain a TODO marker."""
    return [
        name
        for name in text_field_names(type(instance))
        if contains_todo(getattr(instance, name, None))
    ]


def todo_in(instance, *fields):
    """Whether any language of these translated fields contains a TODO marker."""
    return any(
        contains_todo(getattr(instance, column, None))
        for field in fields
        for column in [field, *localized(field)]
    )
