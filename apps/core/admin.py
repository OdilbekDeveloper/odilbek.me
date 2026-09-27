"""The temporary content editor (Django admin) until the dashboard arrives in Phase 5.

Publication happens only through the publish/unpublish actions, which run the publish service:
`is_published` is never an editable checkbox. Uploads go through the media pipeline; the model's
file field is never exposed to a form.
"""

from functools import reduce
from operator import or_

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from modeltranslation.admin import TranslationAdmin

from apps.core import media
from apps.core.content import TODO_MARKER, localized, text_field_names, todo_fields
from apps.core.models import ImportedRecord, MediaAsset, MediaKind, SiteSettings
from apps.core.services import publish, unpublish

admin.site.site_header = "odilbek.me content"
admin.site.site_title = "odilbek.me content"
admin.site.index_title = "Temporary editor (the dashboard replaces it in Phase 5)"


class NeedsReviewFilter(admin.SimpleListFilter):
    title = "review status"
    parameter_name = "todo"

    def lookups(self, request, model_admin):
        return (("yes", "Has TODO(odilbek)"), ("no", "No TODO"))

    def queryset(self, request, queryset):
        has_todo = reduce(
            or_,
            (Q(**{f"{name}__icontains": TODO_MARKER}) for name in text_field_names(queryset.model)),
        )
        if self.value() == "yes":
            return queryset.filter(has_todo)
        if self.value() == "no":
            return queryset.exclude(has_todo)
        return queryset


class PublishableAdminMixin:
    """For Publishable models: publish and unpublish only through the publish service."""

    actions = ["publish_selected", "unpublish_selected"]

    def get_readonly_fields(self, request, obj=None):
        return (*super().get_readonly_fields(request, obj), "is_published", "published_at")

    def get_list_filter(self, request):
        return (*super().get_list_filter(request), "is_published", NeedsReviewFilter)

    @admin.display(boolean=True, description="needs review")
    def needs_review(self, obj):
        return bool(todo_fields(obj))

    @admin.action(description="Publish selected (refused while any TODO remains)")
    def publish_selected(self, request, queryset):
        published, refused = 0, []
        for obj in queryset:
            try:
                publish(obj)
                published += 1
            except ValidationError as exc:
                refused.append(f"{obj}: {' '.join(exc.messages)}")
        if published:
            self.message_user(request, f"Published {published} record(s).", messages.SUCCESS)
        for reason in refused:
            self.message_user(request, f"Not published: {reason}", messages.ERROR)

    @admin.action(description="Unpublish selected")
    def unpublish_selected(self, request, queryset):
        for obj in queryset:
            unpublish(obj)
        self.message_user(request, f"Unpublished {queryset.count()} record(s).", messages.SUCCESS)


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


class MediaUploadForm(forms.ModelForm):
    """The add form: the file goes through the media pipeline during validation, so a rejected
    upload is reported on the form and nothing is written until the admin saves."""

    upload = forms.FileField(
        help_text="JPEG, PNG, WebP or AVIF (10 MB max), or PDF (5 MB max). Images are "
        "re-encoded: EXIF and GPS data are removed."
    )

    class Meta:
        model = MediaAsset
        fields = ("focal_x", "focal_y")

    def clean_upload(self):
        upload = self.cleaned_data["upload"]
        prepared = media.prepare(upload, content_type=getattr(upload, "content_type", ""))
        existing = MediaAsset.objects.filter(sha256=prepared.sha256).first()
        if existing:
            raise ValidationError(f"This exact file is already uploaded as {existing}.")
        self.prepared = prepared
        return upload

    def clean(self):
        cleaned = super().clean()
        prepared = getattr(self, "prepared", None)
        if prepared and prepared.kind != "pdf" and not (cleaned.get("alt_text_en") or "").strip():
            self.add_error("alt_text_en", "Images need English alt text.")
        return cleaned


@admin.register(MediaAsset)
class MediaAssetAdmin(TranslationAdmin):
    list_display = ("id", "thumbnail", "kind", "alt_text", "width", "height", "created_at")
    list_filter = ("kind",)
    search_fields = ("alt_text_en", "alt_text_ko", "caption_en", "sha256")
    readonly_fields = ("preview", "kind", "file", "width", "height", "bytes", "sha256", "variants")

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = MediaUploadForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields if obj else ()

    def get_fieldsets(self, request, obj=None):
        text = [column for field in ("alt_text", "caption") for column in localized(field)]
        if obj is None:
            return ((None, {"fields": ("upload", *text, "focal_x", "focal_y")}),)
        file_fields = ("kind", "file", "width", "height", "bytes", "sha256", "variants")
        return (
            (None, {"fields": ("preview", *text, "focal_x", "focal_y")}),
            ("File", {"fields": file_fields}),
        )

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
        else:
            media.store(form.prepared, instance=obj)

    @admin.display(description="preview")
    def thumbnail(self, obj):
        return self._img(obj, 96)

    @admin.display(description="preview")
    def preview(self, obj):
        return self._img(obj, 320)

    @staticmethod
    def _img(obj, width):
        if obj.kind != MediaKind.IMAGE:
            return "PDF"
        name = obj.variants.get("webp", {}).get("480") or obj.file.name
        return format_html('<img src="{}" width="{}" alt="">', default_storage.url(name), width)


# ---------------------------------------------------------------------------
# Site settings (a singleton)
# ---------------------------------------------------------------------------


@admin.register(SiteSettings)
class SiteSettingsAdmin(TranslationAdmin):
    autocomplete_fields = ("portrait", "default_og_image")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if SiteSettings.objects.exists():
            return redirect(reverse("admin:core_sitesettings_change", args=[1]))
        return super().changelist_view(request, extra_context)


@admin.register(ImportedRecord)
class ImportedRecordAdmin(admin.ModelAdmin):
    """What draft_content created. Read-only; deleting a row lets a later import recreate the
    record (by default a deleted draft is never recreated)."""

    list_display = ("model_label", "key", "object_id", "imported_at")
    list_filter = ("model_label",)
    search_fields = ("key",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
