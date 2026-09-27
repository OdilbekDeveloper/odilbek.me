"""Publication: the only way a record becomes public.

See docs/DATA_MODEL.md, "Visibility semantics".
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.content import todo_fields


def publication_blockers(obj):
    """Everything that stops this record from being published, as readable sentences."""
    problems = [f"'{name}' still contains a TODO(odilbek) marker." for name in todo_fields(obj)]
    problems.extend(obj.publication_blockers())
    return problems


@transaction.atomic
def publish(obj):
    """Publish a record, or raise ValidationError listing what is still missing.

    The database independently refuses a published record whose own text contains a TODO
    marker; this also checks the related text the record displays (see publication_blockers).
    """
    problems = publication_blockers(obj)
    if problems:
        raise ValidationError(problems)
    obj.is_published = True
    if obj.published_at is None:
        obj.published_at = timezone.now()
    obj.full_clean()
    obj.save()
    return obj


@transaction.atomic
def unpublish(obj):
    obj.is_published = False
    obj.save()
    return obj
