"""Writes that compose profiles: sections, links to master items, the primary profile."""

from django.db import transaction
from django.db.models import Max

from apps.career.models import ContactChannel, Education, Experience, Project, Service, Skill
from apps.profiles.models import (
    ProfileContactChannel,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
    ProfileSection,
    ProfileService,
    ProfileSkill,
)

# Master model -> (link model, the link model's item field).
LINK_MODELS = {
    Project: (ProfileProject, "project"),
    Experience: (ProfileExperience, "experience"),
    Skill: (ProfileSkill, "skill"),
    Education: (ProfileEducation, "education"),
    Service: (ProfileService, "service"),
    ContactChannel: (ProfileContactChannel, "channel"),
}


def _next_order(queryset):
    return (queryset.aggregate(highest=Max("order"))["highest"] or 0) + 1


@transaction.atomic
def add_section(profile, section_type, **fields):
    """Append a section, validated against the profile's kind and the section rules."""
    section = ProfileSection(
        profile=profile,
        section_type=section_type,
        order=_next_order(profile.sections.all()),
        **fields,
    )
    section.full_clean()
    section.save()
    return section


@transaction.atomic
def link(profile, item, **fields):
    """Show a master item on a profile (appended), or update the existing link's fields.
    The item itself is never copied."""
    link_model, item_field = LINK_MODELS[type(item)]
    existing = link_model.objects.filter(profile=profile, **{item_field: item}).first()
    if existing:
        for name, value in fields.items():
            setattr(existing, name, value)
        existing.full_clean()
        existing.save()
        return existing
    siblings = link_model.objects.filter(profile=profile)
    row = link_model(profile=profile, order=_next_order(siblings), **{item_field: item}, **fields)
    row.full_clean()
    row.save()
    return row


@transaction.atomic
def set_primary_profile(project, profile):
    """Make `profile` the project's primary profile. The project must already be linked to it,
    so a primary profile always actually shows the project."""
    row = ProfileProject.objects.select_for_update().get(project=project, profile=profile)
    ProfileProject.objects.filter(project=project, is_primary=True).exclude(pk=row.pk).update(
        is_primary=False
    )
    row.is_primary = True
    row.save(update_fields=["is_primary", "updated_at"])
    return row
