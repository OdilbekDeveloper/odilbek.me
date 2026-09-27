"""Public read access to master data.

Public views and templates read career data only through these functions, which build on each
model's public(). `include_drafts=True` is for staff previews and must only be passed after a
view has verified a staff user (docs/ARCHITECTURE.md, "Layering rules").
"""

from django.db.models import Prefetch

from apps.career.models import LanguagePair, Project, Skill


def _public_skills(include_drafts):
    return Skill.objects.visible(include_drafts).select_related("category")


def listed_projects(include_drafts=False):
    """Projects for listings (/projects/). Unlisted projects never appear here."""
    return Project.objects.listed(include_drafts).prefetch_related(
        Prefetch("skills", queryset=_public_skills(include_drafts))
    )


def get_project(slug, include_drafts=False):
    """A project page (/projects/<slug>/). Unlisted projects are reachable here, and only here.
    Raises Project.DoesNotExist for anything not visible."""
    return (
        Project.objects.visible(include_drafts)
        .prefetch_related(Prefetch("skills", queryset=_public_skills(include_drafts)))
        .get(slug=slug)
    )


def get_skill(slug, include_drafts=False):
    """A skill evidence page (/skills/<slug>/). Raises Skill.DoesNotExist if not visible."""
    return _public_skills(include_drafts).get(slug=slug)


def language_pairs(include_drafts=False):
    """Pairs whose two languages are both public."""
    return LanguagePair.objects.visible(include_drafts).select_related("source", "target")
