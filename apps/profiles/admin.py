from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from modeltranslation.admin import (
    TranslationAdmin,
    TranslationStackedInline,
    TranslationTabularInline,
)

from apps.core.admin import PublishableAdminMixin
from apps.profiles.models import (
    Profile,
    ProfileContactChannel,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
    ProfileSection,
    ProfileService,
    ProfileSkill,
    SectionType,
)


class ProfileForm(forms.ModelForm):
    languages = forms.TypedMultipleChoiceField(
        choices=settings.LANGUAGES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="English is always included.",
    )

    class Meta:
        # The admin passes its own field list; this form only customises `languages`.
        model = Profile
        fields = ("languages",)


class SectionFormSet(forms.BaseInlineFormSet):
    """Report a repeated section type on the form rather than as a database error."""

    def clean(self):
        super().clean()
        seen = set()
        for form in self.forms:
            if not getattr(form, "cleaned_data", None) or form.cleaned_data.get("DELETE"):
                continue
            section_type = form.cleaned_data.get("section_type")
            if section_type == SectionType.CUSTOM_MARKDOWN:
                continue
            if section_type in seen:
                raise ValidationError(f"Only one '{section_type}' section per profile.")
            seen.add(section_type)


class SectionInline(TranslationStackedInline):
    model = ProfileSection
    formset = SectionFormSet
    extra = 0


class ProjectLinkInline(TranslationTabularInline):
    model = ProfileProject
    extra = 0
    autocomplete_fields = ("project",)


class ExperienceLinkInline(TranslationStackedInline):
    model = ProfileExperience
    extra = 0
    autocomplete_fields = ("experience",)


class SkillLinkInline(admin.TabularInline):
    model = ProfileSkill
    extra = 0
    autocomplete_fields = ("skill",)


class EducationLinkInline(admin.TabularInline):
    model = ProfileEducation
    extra = 0
    autocomplete_fields = ("education",)


class ServiceLinkInline(admin.TabularInline):
    model = ProfileService
    extra = 0
    autocomplete_fields = ("service",)


class ChannelLinkInline(admin.TabularInline):
    model = ProfileContactChannel
    extra = 0
    autocomplete_fields = ("channel",)


@admin.register(Profile)
class ProfileAdmin(PublishableAdminMixin, TranslationAdmin):
    form = ProfileForm
    list_display = ("name", "kind", "slug", "languages", "is_published", "needs_review", "order")
    list_filter = ("kind",)
    search_fields = ("name_en", "name_ko", "slug")
    autocomplete_fields = ("hero_image", "og_image")
    inlines = (
        SectionInline,
        ProjectLinkInline,
        ExperienceLinkInline,
        SkillLinkInline,
        EducationLinkInline,
        ServiceLinkInline,
        ChannelLinkInline,
    )
