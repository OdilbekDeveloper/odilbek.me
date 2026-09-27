"""Database constraint builders shared by every app.

Invariants live in PostgreSQL wherever a single table can express them, so they hold for admin
edits, services, bulk `QuerySet.update()` calls and the shell alike. Rules that need another table
are validated in `clean()` and the services instead; each model says which.
"""

from functools import reduce
from operator import and_

from django.core.validators import URLValidator
from django.db.models import CheckConstraint, F, Q

from apps.core.content import TODO_MARKER, localized

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
HTTP_URL_PATTERN = r"^https?://"

# The form-level twin of http_url(): URLField alone would also accept ftp:// links.
validate_http_url = URLValidator(schemes=("http", "https"))


def all_columns(translated=(), plain=()):
    """Every column holding text for these fields: each translation plus the original column,
    which modeltranslation keeps and fills with the resolved value on save."""
    columns = list(plain)
    for field in translated:
        columns += [field, *localized(field)]
    return columns


def filled(column):
    """Not NULL and not blank. (A CHECK passes on NULL, so NULL must be ruled out explicitly.)"""
    return Q(**{f"{column}__isnull": False}) & Q(**{f"{column}__regex": r"\S"})


def blank(column):
    return Q(**{f"{column}__isnull": True}) | Q(**{column: ""})


def slug_format(name, field="slug"):
    """ASCII, lowercase, words joined by single hyphens. Never translated."""
    return CheckConstraint(
        condition=Q(**{f"{field}__regex": SLUG_PATTERN}),
        name=name,
        violation_error_message="Use lowercase letters, digits and single hyphens only.",
    )


def http_url(name, field):
    """Empty, or an http(s) URL: never javascript:, data: or any other scheme."""
    return CheckConstraint(
        condition=Q(**{field: ""}) | Q(**{f"{field}__regex": HTTP_URL_PATTERN}),
        name=name,
        violation_error_message="Only http:// and https:// links are allowed.",
    )


def one_of(name, field, choices, allow_blank=False):
    values = list(choices.values) + ([""] if allow_blank else [])
    return CheckConstraint(condition=Q(**{f"{field}__in": values}), name=name)


def english_required(name, *fields):
    """The English translation of each field must be filled (D-015: only English is required)."""
    return CheckConstraint(
        condition=reduce(and_, (filled(f"{field}_en") for field in fields)),
        name=name,
        violation_error_message="English is required.",
    )


def required_to_publish(name, condition):
    """A draft may lack it; a published record may not."""
    return CheckConstraint(
        condition=Q(is_published=False) | condition,
        name=name,
        violation_error_message="This must be filled in before the record is published.",
    )


def published_at_set(name):
    return CheckConstraint(
        condition=Q(is_published=False) | Q(published_at__isnull=False),
        name=name,
    )


def todo_free(translated=(), plain=()):
    """No text column of these fields contains a TODO marker."""
    return reduce(
        and_,
        (~Q(**{f"{column}__icontains": TODO_MARKER}) for column in all_columns(translated, plain)),
    )


def no_todo_when_published(name, translated=(), plain=()):
    """A record whose own text still contains a TODO marker cannot be published."""
    return CheckConstraint(
        condition=Q(is_published=False) | todo_free(translated, plain),
        name=name,
        violation_error_message="Resolve every TODO(odilbek) before publishing.",
    )


def dates_in_order(name, start="started_on", end="ended_on"):
    return CheckConstraint(
        condition=(
            Q(**{f"{start}__isnull": True})
            | Q(**{f"{end}__isnull": True})
            | Q(**{f"{end}__gte": F(start)})
        ),
        name=name,
        violation_error_message="The end date cannot be before the start date.",
    )
