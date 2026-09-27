from modeltranslation.translator import register

from apps.career.models import (
    ContactChannel,
    Education,
    Experience,
    LanguagePair,
    Project,
    ProjectMedia,
    Service,
    Skill,
    SkillCategory,
)
from apps.core.translation import EnglishRequired


@register(SkillCategory)
class SkillCategoryTranslation(EnglishRequired):
    fields = ("name",)


@register(Skill)
class SkillTranslation(EnglishRequired):
    fields = ("name", "description", "level_label")


@register(Project)
class ProjectTranslation(EnglishRequired):
    fields = (
        "title",
        "summary",
        "context",
        "description",
        "highlights",
        "role",
        "seo_title",
        "seo_description",
    )


@register(ProjectMedia)
class ProjectMediaTranslation(EnglishRequired):
    fields = ("caption",)


@register(Experience)
class ExperienceTranslation(EnglishRequired):
    fields = ("role", "organization", "location", "summary", "highlights")


@register(Education)
class EducationTranslation(EnglishRequired):
    fields = ("institution", "credential", "field", "result", "description")


@register(Service)
class ServiceTranslation(EnglishRequired):
    fields = ("title", "summary", "description", "pricing_note")


@register(LanguagePair)
class LanguagePairTranslation(EnglishRequired):
    fields = ("domains", "note")


@register(ContactChannel)
class ContactChannelTranslation(EnglishRequired):
    fields = ("label",)
