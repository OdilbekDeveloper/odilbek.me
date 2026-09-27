from modeltranslation.translator import register

from apps.core.translation import EnglishRequired, NoFallback
from apps.profiles.models import Profile, ProfileExperience, ProfileProject, ProfileSection


@register(Profile)
class ProfileTranslation(EnglishRequired):
    fields = (
        "name",
        "switcher_label",
        "headline",
        "subheadline",
        "intro",
        "router_prompt",
        "router_blurb",
        "primary_cta_label",
        "seo_title",
        "seo_description",
    )


@register(ProfileSection)
class ProfileSectionTranslation(EnglishRequired):
    fields = ("heading", "intro", "body")


# Overrides do not fall back across languages: an empty Korean override means "no override in
# Korean", so the item's own Korean text shows (effective_summary), not the English override.
@register(ProfileProject)
class ProfileProjectTranslation(NoFallback):
    fields = ("summary_override",)


@register(ProfileExperience)
class ProfileExperienceTranslation(NoFallback):
    fields = ("summary_override", "highlights_override")
