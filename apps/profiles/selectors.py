"""Public read access to profiles and the master items they show.

The query boundary Phase 4's pages will use. Every function applies the visibility rules in
docs/DATA_MODEL.md: unpublished records are hidden; an item appears on a profile only when a link
row exists and the item itself is public; unlisted projects never appear in lists; disabled
sections are never returned. `include_drafts=True` is for staff previews only, passed after a
view has verified a staff user; it never reveals disabled sections.
"""

from apps.profiles.models import (
    Profile,
    ProfileContactChannel,
    ProfileEducation,
    ProfileExperience,
    ProfileKind,
    ProfileProject,
    ProfileService,
    ProfileSkill,
)


def _published(field, include_drafts):
    return {} if include_drafts else {f"{field}__is_published": True}


def get_home(include_drafts=False):
    """Raises Profile.DoesNotExist if there is no visible home profile."""
    return Profile.objects.visible(include_drafts).get(kind=ProfileKind.HOME)


def get_about(include_drafts=False):
    return Profile.objects.visible(include_drafts).get(kind=ProfileKind.ABOUT)


def get_role_profile(slug, include_drafts=False):
    """The profile at /<slug>/. Raises Profile.DoesNotExist if not visible."""
    return Profile.objects.visible(include_drafts).roles().get(slug=slug)


def switcher_profiles(include_drafts=False):
    return Profile.objects.visible(include_drafts).filter(show_in_switcher=True)


def router_profiles(include_drafts=False):
    """The routes offered by the home page's router: every visible profile except home."""
    return (
        Profile.objects.visible(include_drafts)
        .filter(show_in_router=True)
        .exclude(kind=ProfileKind.HOME)
    )


def profile_sections(profile):
    """Enabled sections, in order. Disabled sections are never returned, preview or not."""
    return profile.sections.filter(is_enabled=True).order_by("order", "id")


def profile_projects(profile, include_drafts=False):
    """Linked projects that are visible and listed, in the profile's order."""
    return (
        ProfileProject.objects.filter(
            profile=profile, project__is_listed=True, **_published("project", include_drafts)
        )
        .select_related("project")
        .order_by("order", "id")
    )


def profile_experience(profile, include_drafts=False):
    return (
        ProfileExperience.objects.filter(
            profile=profile, **_published("experience", include_drafts)
        )
        .select_related("experience")
        .order_by("order", "id")
    )


def profile_skills(profile, include_drafts=False):
    return (
        ProfileSkill.objects.filter(profile=profile, **_published("skill", include_drafts))
        .select_related("skill", "skill__category")
        .order_by("order", "id")
    )


def profile_education(profile, include_drafts=False):
    return (
        ProfileEducation.objects.filter(profile=profile, **_published("education", include_drafts))
        .select_related("education")
        .order_by("order", "id")
    )


def profile_services(profile, include_drafts=False):
    return (
        ProfileService.objects.filter(profile=profile, **_published("service", include_drafts))
        .select_related("service")
        .order_by("order", "id")
    )


def profile_contact_channels(profile, include_drafts=False):
    return (
        ProfileContactChannel.objects.filter(
            profile=profile, **_published("channel", include_drafts)
        )
        .select_related("channel")
        .order_by("order", "id")
    )
