"""Shared model foundations and the site-wide models (docs/DATA_MODEL.md, "core")."""

import zoneinfo

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q

from apps.core import constraints as c

# ---------------------------------------------------------------------------
# Abstract bases
# ---------------------------------------------------------------------------


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Ordered(models.Model):
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        abstract = True
        ordering = ["order", "id"]


class PublishableQuerySet(models.QuerySet):
    def public(self):
        """What the public may see (docs/DATA_MODEL.md, "Visibility semantics")."""
        return self.filter(is_published=True)

    def visible(self, include_drafts=False):
        """public(), or everything when a staff preview asks for drafts."""
        return self.all() if include_drafts else self.public()


class Publishable(models.Model):
    """Invisible to the public until published, and published only through
    apps.core.services.publish(), never by editing the flag directly."""

    is_published = models.BooleanField(default=False, db_index=True, editable=False)
    # When the record was first published; kept if it is later unpublished.
    published_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = PublishableQuerySet.as_manager()

    class Meta:
        abstract = True

    def publication_blockers(self):
        """Reasons, beyond this record's own constraints, that it cannot be published yet.
        Models that display related text (link overrides, image captions) extend this."""
        return []


class SEOFields(models.Model):
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
    og_image = models.ForeignKey(
        "core.MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        limit_choices_to={"kind": "image"},
        verbose_name="Open Graph image",
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


class MediaKind(models.TextChoices):
    IMAGE = "image", "Image"
    PDF = "pdf", "PDF"


class MediaAsset(TimeStamped):
    """An uploaded image or PDF. Created only through apps.core.media, which validates the
    upload, re-encodes images (stripping EXIF/GPS) and writes files under server-chosen names."""

    file = models.FileField(max_length=255, editable=False)
    kind = models.CharField(max_length=5, choices=MediaKind, editable=False)
    alt_text = models.CharField(max_length=250, blank=True)
    caption = models.CharField(max_length=300, blank=True)
    width = models.PositiveIntegerField(null=True, editable=False)
    height = models.PositiveIntegerField(null=True, editable=False)
    bytes = models.PositiveBigIntegerField(editable=False)
    # Of the uploaded bytes: the same file uploaded twice is the same asset.
    sha256 = models.CharField(max_length=64, unique=True, editable=False)
    # 0-1 from the left/top edge. Variants are resized, never cropped, so this stays valid for
    # whatever crop a layout makes later.
    focal_x = models.FloatField(default=0.5)
    focal_y = models.FloatField(default=0.5)
    # {"avif": {"480": "images/<token>/480.avif", ...}, "webp": {...}}
    variants = models.JSONField(default=dict, blank=True, editable=False)

    class Meta:
        verbose_name = "media asset"
        ordering = ["-created_at", "-id"]
        constraints = [
            c.one_of("core_mediaasset_kind_valid", "kind", MediaKind),
            CheckConstraint(
                condition=Q(sha256__regex=r"^[0-9a-f]{64}$"), name="core_mediaasset_sha256_hex"
            ),
            CheckConstraint(condition=Q(bytes__gte=1), name="core_mediaasset_bytes_positive"),
            # NULL >= 1 is unknown, and a CHECK passes on unknown: rule NULL out explicitly.
            CheckConstraint(
                condition=(
                    Q(
                        kind=MediaKind.IMAGE,
                        width__isnull=False,
                        height__isnull=False,
                        width__gte=1,
                        height__gte=1,
                    )
                    | Q(kind=MediaKind.PDF, width__isnull=True, height__isnull=True)
                ),
                name="core_mediaasset_dimensions_match_kind",
            ),
            CheckConstraint(
                condition=Q(kind=MediaKind.PDF) | c.filled("alt_text_en"),
                name="core_mediaasset_image_alt_text_en",
                violation_error_message="Images need English alt text.",
            ),
            CheckConstraint(
                condition=Q(focal_x__gte=0, focal_x__lte=1, focal_y__gte=0, focal_y__lte=1),
                name="core_mediaasset_focal_point_in_range",
                violation_error_message="The focal point must be between 0 and 1.",
            ),
        ]

    def __str__(self):
        label = self.alt_text or self.caption or self.file.name
        return f"{self.get_kind_display()} #{self.pk}: {label}"

    def variant_widths(self, fmt):
        return sorted(int(width) for width in self.variants.get(fmt, {}))


# ---------------------------------------------------------------------------
# Site settings
# ---------------------------------------------------------------------------


class Availability(models.TextChoices):
    AVAILABLE = "available", "Available"
    LIMITED = "limited", "Limited availability"
    UNAVAILABLE = "unavailable", "Not available"


def validate_timezone(value):
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"{value!r} is not an IANA time zone name, e.g. 'Asia/Seoul'.")


class SiteSettings(TimeStamped):
    """Site-wide identity and defaults. Exactly one row, with id 1; use SiteSettings.load()."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    owner_name = models.CharField(max_length=120, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=120, blank=True)
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone])
    public_email = models.EmailField(blank=True)
    # Blank means "not stated": nothing is shown rather than a claim nobody made.
    availability = models.CharField(max_length=12, choices=Availability, blank=True)
    availability_note = models.CharField(max_length=200, blank=True)
    response_time_note = models.CharField(max_length=200, blank=True)
    portrait = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        limit_choices_to={"kind": MediaKind.IMAGE},
        help_text="The default hero and About photo.",
    )
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
    default_og_image = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        limit_choices_to={"kind": MediaKind.IMAGE},
        verbose_name="default Open Graph image",
    )

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"
        constraints = [
            CheckConstraint(condition=Q(id=1), name="core_sitesettings_singleton"),
            c.one_of(
                "core_sitesettings_availability_valid",
                "availability",
                Availability,
                allow_blank=True,
            ),
        ]

    def __str__(self):
        return "Site settings"

    @classmethod
    def load(cls):
        settings, _created = cls.objects.get_or_create(pk=1)
        return settings


# ---------------------------------------------------------------------------
# Draft-import bookkeeping
# ---------------------------------------------------------------------------


class ImportedRecord(models.Model):
    """Which record `manage.py draft_content` created for which manifest key.

    Provenance only, never content. It lets a re-run find its own drafts even after they were
    edited, and leave alone the ones that were deliberately deleted (docs/CONTENT_IMPORT.md).
    """

    model_label = models.CharField(max_length=60)
    key = models.CharField(max_length=120)
    object_id = models.PositiveBigIntegerField()
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["model_label", "key"]
        constraints = [
            models.UniqueConstraint(
                fields=["model_label", "key"], name="core_importedrecord_unique_key"
            ),
        ]

    def __str__(self):
        return f"{self.model_label}:{self.key} → #{self.object_id}"
