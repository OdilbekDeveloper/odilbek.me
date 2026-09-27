from django import forms
from django.contrib import admin
from modeltranslation.admin import TranslationAdmin, TranslationTabularInline

from apps.career.models import (
    ContactChannel,
    Education,
    Experience,
    LanguageMode,
    LanguagePair,
    Project,
    ProjectMedia,
    Service,
    Skill,
    SkillCategory,
)
from apps.core.admin import PublishableAdminMixin


@admin.register(SkillCategory)
class SkillCategoryAdmin(TranslationAdmin):
    list_display = ("name", "slug", "kind", "order")
    list_filter = ("kind",)
    search_fields = ("name_en", "name_ko", "slug")
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(Skill)
class SkillAdmin(PublishableAdminMixin, TranslationAdmin):
    list_display = ("name", "category", "level_label", "is_published", "needs_review", "order")
    list_filter = ("category__kind", "category")
    search_fields = ("name_en", "name_ko", "slug")
    autocomplete_fields = ("category",)
    prepopulated_fields = {"slug": ("name_en",)}


class ProjectMediaInline(TranslationTabularInline):
    model = ProjectMedia
    extra = 0
    autocomplete_fields = ("asset",)


@admin.register(Project)
class ProjectAdmin(PublishableAdminMixin, TranslationAdmin):
    list_display = (
        "title",
        "slug",
        "project_status",
        "is_listed",
        "is_featured",
        "is_published",
        "needs_review",
        "order",
    )
    list_filter = ("project_status", "is_listed", "is_featured")
    search_fields = ("title_en", "title_ko", "slug", "summary_en")
    autocomplete_fields = ("skills", "cover", "og_image")
    prepopulated_fields = {"slug": ("title_en",)}
    inlines = (ProjectMediaInline,)


@admin.register(Experience)
class ExperienceAdmin(PublishableAdminMixin, TranslationAdmin):
    list_display = (
        "role",
        "organization",
        "employment_type",
        "started_on",
        "ended_on",
        "is_published",
        "needs_review",
    )
    list_filter = ("employment_type",)
    search_fields = ("role_en", "role_ko", "organization_en", "organization_ko")
    autocomplete_fields = ("skills", "projects")


@admin.register(Education)
class EducationAdmin(PublishableAdminMixin, TranslationAdmin):
    list_display = ("institution", "credential", "kind", "ended_on", "is_published", "needs_review")
    list_filter = ("kind",)
    search_fields = ("institution_en", "institution_ko", "credential_en")
    autocomplete_fields = ("skills",)


@admin.register(Service)
class ServiceAdmin(PublishableAdminMixin, TranslationAdmin):
    list_display = ("title", "slug", "is_published", "needs_review", "order")
    search_fields = ("title_en", "title_ko", "slug")
    autocomplete_fields = ("skills",)
    prepopulated_fields = {"slug": ("title_en",)}


class LanguagePairForm(forms.ModelForm):
    modes = forms.MultipleChoiceField(
        choices=LanguageMode.choices, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        # The admin passes its own field list; this form only customises `modes`.
        model = LanguagePair
        fields = ("modes",)


@admin.register(LanguagePair)
class LanguagePairAdmin(TranslationAdmin):
    form = LanguagePairForm
    list_display = ("__str__", "modes", "order")
    autocomplete_fields = ("source", "target")


@admin.register(ContactChannel)
class ContactChannelAdmin(PublishableAdminMixin, TranslationAdmin):
    list_display = ("label", "kind", "handle", "url", "is_published", "needs_review", "order")
    list_filter = ("kind",)
    search_fields = ("label_en", "handle", "url")
