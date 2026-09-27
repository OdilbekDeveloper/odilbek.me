"""Translated fields of the core models, and the options every app's translations share.

modeltranslation adds a column per language (e.g. alt_text_en, alt_text_ko, alt_text_uz). Slugs
are never translated. Each app registers its own models in its translation.py, using these bases.
"""

from modeltranslation.translator import TranslationOptions, register

from apps.core.models import MediaAsset, SiteSettings


class EnglishRequired(TranslationOptions):
    """English is required wherever the original field is required; Korean and Uzbek are always
    optional (D-015). Missing translations fall back to English
    (MODELTRANSLATION_FALLBACK_LANGUAGES). The database enforces the same rule per model
    (apps.core.constraints.english_required), since these options only affect forms."""

    required_languages = ("en",)


class NoFallback(TranslationOptions):
    """For override fields: an empty override in one language means "no override here", so
    the item's own text shows instead of another language's override."""

    fallback_languages = {"default": ()}


@register(SiteSettings)
class SiteSettingsTranslation(EnglishRequired):
    fields = (
        "owner_name",
        "tagline",
        "location",
        "availability_note",
        "response_time_note",
        "seo_title",
        "seo_description",
    )


@register(MediaAsset)
class MediaAssetTranslation(EnglishRequired):
    fields = ("alt_text", "caption")
