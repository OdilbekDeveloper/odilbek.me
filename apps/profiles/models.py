"""Curated website views over the master data (docs/DATA_MODEL.md, "profiles").

A profile holds presentation only: its hero, its sections, and which master items it shows, in
which order, with optional wording overrides for this view. It never copies a project, job or
skill. Profiles are data: no code anywhere branches on a particular profile.
"""

from functools import reduce
from operator import and_, or_

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint

from apps.career.models import ContactChannel, Education, Experience, Project, Service, Skill
from apps.core import constraints as c
from apps.core.content import language_codes, todo_fields, todo_in
from apps.core.models import (
    MediaAsset,
    MediaKind,
    Ordered,
    Publishable,
    PublishableQuerySet,
    SEOFields,
    TimeStamped,
)
from apps.core.selectors import site_settings
from apps.core.slugs import RESERVED_SLUGS, validate_not_reserved

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class ProfileKind(models.TextChoices):
    HOME = "home", "Home (/)"
    ABOUT = "about", "About (/about/)"
    ROLE = "role", "Role (/<slug>/)"


class HeroVariant(models.TextChoices):
    PORTRAIT = "portrait", "Portrait"
    SPLIT = "split", "Split"
    BILINGUAL = "bilingual", "Bilingual"
    STATEMENT = "statement", "Statement (no photo)"


class Accent(models.TextChoices):
    # The named accent tokens arrive with the design system in Phase 3 (colours are not locked
    # yet, docs/DESIGN.md). Until then every profile uses the default.
    DEFAULT = "default", "Default"


class PrimaryCTA(models.TextChoices):
    CONTACT = "contact", "Contact"
    RESUME = "resume", "Download CV"
    PROJECTS = "projects", "Projects"


class ContactFormVariant(models.TextChoices):
    GENERAL = "general", "General"
    PROJECT_INQUIRY = "project_inquiry", "Project inquiry"
    LANGUAGE_REQUEST = "language_request", "Language request"


def default_languages():
    return ["en"]


class ProfileQuerySet(PublishableQuerySet):
    def roles(self):
        return self.filter(kind=ProfileKind.ROLE)


class Profile(TimeStamped, Publishable, SEOFields, Ordered):
    kind = models.CharField(max_length=5, choices=ProfileKind, default=ProfileKind.ROLE)
    slug = models.SlugField(
        max_length=60,
        unique=True,
        help_text="Role profiles live at /<slug>/. Never translated.",
    )
    name = models.CharField(max_length=80)
    switcher_label = models.CharField(max_length=40, blank=True)
    headline = models.CharField(max_length=160, blank=True, help_text="Required to publish.")
    subheadline = models.CharField(max_length=240, blank=True)
    intro = models.TextField(blank=True, help_text="Markdown.")
    hero_variant = models.CharField(
        max_length=10, choices=HeroVariant, default=HeroVariant.PORTRAIT
    )
    accent = models.CharField(max_length=20, choices=Accent, default=Accent.DEFAULT)
    hero_image = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        limit_choices_to={"kind": MediaKind.IMAGE},
        help_text="Empty: the portrait in site settings.",
    )
    router_prompt = models.CharField(max_length=120, blank=True)
    router_blurb = models.CharField(max_length=240, blank=True)
    show_in_switcher = models.BooleanField(default=True)
    show_in_router = models.BooleanField(default=True)
    languages = ArrayField(
        models.CharField(max_length=5),
        default=default_languages,
        help_text="Languages this profile is published in. English is always included.",
    )
    primary_cta = models.CharField(max_length=10, choices=PrimaryCTA, default=PrimaryCTA.CONTACT)
    primary_cta_label = models.CharField(max_length=60, blank=True)
    contact_form_variant = models.CharField(
        max_length=20, choices=ContactFormVariant, default=ContactFormVariant.GENERAL
    )
    # default_resume -> Resume arrives with the Resume model in Phase 8.

    objects = ProfileQuerySet.as_manager()

    class Meta(Ordered.Meta):
        constraints = [
            c.slug_format("profiles_profile_slug_format"),
            # A database can guarantee at most one; that a home exists is a content requirement
            # (a migration creating it would put content in code).
            UniqueConstraint(
                fields=["kind"],
                condition=Q(kind=ProfileKind.HOME),
                name="profiles_profile_one_home",
            ),
            UniqueConstraint(
                fields=["kind"],
                condition=Q(kind=ProfileKind.ABOUT),
                name="profiles_profile_one_about",
            ),
            # Role profiles live at the URL root, so their slugs may not shadow a route or
            # language (D-012). Home and About have fixed routes. The configurable admin path is
            # checked in clean(): only the application knows it.
            CheckConstraint(
                condition=(
                    Q(kind__in=[ProfileKind.HOME, ProfileKind.ABOUT])
                    | ~Q(slug__in=sorted(RESERVED_SLUGS))
                ),
                name="profiles_profile_slug_not_reserved",
                violation_error_message="This slug is reserved for a site route or language.",
            ),
            CheckConstraint(
                condition=(
                    Q(languages__contains=["en"]) & Q(languages__contained_by=language_codes())
                ),
                name="profiles_profile_languages_valid",
                violation_error_message="Languages must include English and be site languages.",
            ),
            c.one_of("profiles_profile_kind_valid", "kind", ProfileKind),
            c.one_of("profiles_profile_hero_variant_valid", "hero_variant", HeroVariant),
            c.one_of("profiles_profile_accent_valid", "accent", Accent),
            c.one_of("profiles_profile_primary_cta_valid", "primary_cta", PrimaryCTA),
            c.one_of(
                "profiles_profile_contact_form_valid", "contact_form_variant", ContactFormVariant
            ),
            c.english_required("profiles_profile_name_en", "name"),
            c.required_to_publish("profiles_profile_headline_to_publish", c.filled("headline_en")),
            c.published_at_set("profiles_profile_published_at_set"),
            c.no_todo_when_published(
                "profiles_profile_no_todo_when_published",
                translated=(
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
                ),
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    def clean(self):
        errors = {}
        if self.kind == ProfileKind.ROLE and self.slug:
            try:
                validate_not_reserved(self.slug)
            except ValidationError as exc:
                errors["slug"] = exc.messages
        if self.languages is not None:
            unknown = set(self.languages) - set(language_codes())
            if unknown:
                errors["languages"] = f"Unknown language codes: {', '.join(sorted(unknown))}."
            else:
                # Canonical order, English always included.
                chosen = {*self.languages, "en"}
                self.languages = [code for code in language_codes() if code in chosen]
        if self.pk and self.kind != ProfileKind.HOME:
            if self.sections.filter(section_type=SectionType.PROFILE_ROUTER).exists():
                errors["kind"] = "Only the home profile may have a profile router section."
        if errors:
            raise ValidationError(errors)

    def publication_blockers(self):
        """Related text this profile displays must be free of TODO markers too."""
        problems = []
        for link in self.project_links.all():
            if todo_in(link, "summary_override"):
                problems.append(f"The summary override for project '{link.project}' has a TODO.")
        for link in self.experience_links.all():
            if todo_in(link, "summary_override", "highlights_override"):
                problems.append(f"An override for '{link.experience}' has a TODO.")
        if self.hero_image and todo_in(self.hero_image, "alt_text", "caption"):
            problems.append("The hero image's alt text or caption has a TODO.")
        settings = site_settings()
        if todo_fields(settings):
            problems.append("Site settings (shown on every page) still contain TODO markers.")
        return problems


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


class SectionType(models.TextChoices):
    ABOUT = "about", "About"
    CUSTOM_MARKDOWN = "custom_markdown", "Custom text"
    EVIDENCE_STRIP = "evidence_strip", "Evidence strip"
    SKILLS = "skills", "Skills"
    PROJECTS = "projects", "Projects"
    EXPERIENCE = "experience", "Experience"
    EDUCATION = "education", "Education"
    SERVICES = "services", "Services"
    LANGUAGE_PAIRS = "language_pairs", "Language pairs"
    RESUME_CTA = "resume_cta", "Resume call to action"
    CONTACT = "contact", "Contact"
    PROFILE_ROUTER = "profile_router", "Profile router"
    # career_map (Phase 11) and blog_posts (Phase 13) are added with their phases.


class LayoutVariant(models.TextChoices):
    DEFAULT = "default", "Default"
    # Per-type variants are designed in Phase 4 and added to SECTION_LAYOUTS then.


# Sections that list the profile's linked items; only they may limit how many are shown.
LIST_SECTIONS = frozenset(
    {
        SectionType.SKILLS,
        SectionType.PROJECTS,
        SectionType.EXPERIENCE,
        SectionType.EDUCATION,
        SectionType.SERVICES,
        SectionType.LANGUAGE_PAIRS,
    }
)

# Which profile kinds may use a section type; types not listed suit every kind.
SECTION_PROFILE_KINDS = {SectionType.PROFILE_ROUTER: frozenset({ProfileKind.HOME})}

# Which layout variants each section type supports. The database enforces this map.
SECTION_LAYOUTS = {section_type: (LayoutVariant.DEFAULT,) for section_type in SectionType}


def section_allowed_for(section_type, profile_kind):
    return profile_kind in SECTION_PROFILE_KINDS.get(section_type, frozenset(ProfileKind))


class ProfileSection(TimeStamped, Ordered):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="sections")
    section_type = models.CharField(max_length=20, choices=SectionType)
    heading = models.CharField(max_length=120, blank=True)
    intro = models.TextField(blank=True)
    body = models.TextField(blank=True, help_text="Markdown. Custom text sections only.")
    layout_variant = models.CharField(
        max_length=20, choices=LayoutVariant, default=LayoutVariant.DEFAULT
    )
    item_limit = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="List sections only: show at most this many items."
    )
    anchor = models.SlugField(max_length=60, blank=True, help_text="In-page link target.")
    is_enabled = models.BooleanField(default=True)

    class Meta(Ordered.Meta):
        constraints = [
            c.one_of("profiles_profilesection_type_valid", "section_type", SectionType),
            CheckConstraint(
                condition=reduce(
                    or_,
                    (
                        Q(section_type=section_type, layout_variant__in=list(layouts))
                        for section_type, layouts in SECTION_LAYOUTS.items()
                    ),
                ),
                name="profiles_profilesection_layout_valid",
                violation_error_message="This layout is not available for this section type.",
            ),
            UniqueConstraint(
                fields=["profile", "section_type"],
                condition=~Q(section_type=SectionType.CUSTOM_MARKDOWN),
                name="profiles_profilesection_one_per_type",
                violation_error_message="This profile already has a section of this type.",
            ),
            CheckConstraint(
                condition=(
                    Q(section_type=SectionType.CUSTOM_MARKDOWN)
                    | reduce(and_, (c.blank(col) for col in c.all_columns(("body",))))
                ),
                name="profiles_profilesection_body_custom_only",
                violation_error_message="Only custom text sections have a body.",
            ),
            CheckConstraint(
                condition=(
                    Q(item_limit__isnull=True)
                    | Q(item_limit__gte=1, section_type__in=sorted(LIST_SECTIONS))
                ),
                name="profiles_profilesection_item_limit_valid",
                violation_error_message="Only list sections can limit items, and to at least 1.",
            ),
            CheckConstraint(
                condition=Q(anchor="") | Q(anchor__regex=c.SLUG_PATTERN),
                name="profiles_profilesection_anchor_format",
            ),
            UniqueConstraint(
                fields=["profile", "anchor"],
                condition=~Q(anchor=""),
                name="profiles_profilesection_anchor_unique",
            ),
            CheckConstraint(
                condition=Q(is_enabled=False)
                | c.todo_free(translated=("heading", "intro", "body")),
                name="profiles_profilesection_no_todo_when_enabled",
                violation_error_message="Resolve every TODO(odilbek) before enabling a section.",
            ),
        ]

    def __str__(self):
        return f"{self.profile} · {self.get_section_type_display()}"

    def clean(self):
        # Cross-table rule (a CHECK constraint cannot read the profile's kind).
        try:
            profile = self.profile
        except Profile.DoesNotExist:
            return
        if self.section_type and not section_allowed_for(self.section_type, profile.kind):
            raise ValidationError(
                {"section_type": "This section type is not available for this profile kind."}
            )


# ---------------------------------------------------------------------------
# Link tables: which master items a profile shows, in what order, in what words
# ---------------------------------------------------------------------------


class ProfileLink(TimeStamped, Ordered):
    """Shared base of the link tables. Each table adds its item, its unique (profile, item)
    pair, and the override fields it needs."""

    class Meta(Ordered.Meta):
        abstract = True


class ProfileProject(ProfileLink):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="project_links")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="profile_links")
    is_featured = models.BooleanField(default=False)
    is_primary = models.BooleanField(
        default=False,
        help_text="The project's primary profile: its back link when the referrer is unknown. "
        "At most one per project.",
    )
    summary_override = models.CharField(max_length=300, blank=True)

    class Meta(ProfileLink.Meta):
        constraints = [
            UniqueConstraint(fields=["profile", "project"], name="profiles_profileproject_pair"),
            UniqueConstraint(
                fields=["project"],
                condition=Q(is_primary=True),
                name="profiles_profileproject_one_primary",
                violation_error_message="This project already has a primary profile.",
            ),
        ]

    def __str__(self):
        return f"{self.profile} · {self.project}"

    @property
    def effective_summary(self):
        """This view's wording in the current language, else the project's own summary."""
        return self.summary_override or self.project.summary


class ProfileExperience(ProfileLink):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="experience_links")
    experience = models.ForeignKey(
        Experience, on_delete=models.CASCADE, related_name="profile_links"
    )
    summary_override = models.TextField(blank=True)
    highlights_override = models.TextField(blank=True, help_text="Markdown.")

    class Meta(ProfileLink.Meta):
        constraints = [
            UniqueConstraint(
                fields=["profile", "experience"], name="profiles_profileexperience_pair"
            ),
        ]

    def __str__(self):
        return f"{self.profile} · {self.experience}"

    @property
    def effective_summary(self):
        return self.summary_override or self.experience.summary

    @property
    def effective_highlights(self):
        return self.highlights_override or self.experience.highlights


class ProfileSkill(ProfileLink):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="skill_links")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="profile_links")
    is_primary = models.BooleanField(default=False, help_text="Emphasised on this profile.")

    class Meta(ProfileLink.Meta):
        constraints = [
            UniqueConstraint(fields=["profile", "skill"], name="profiles_profileskill_pair"),
        ]

    def __str__(self):
        return f"{self.profile} · {self.skill}"


class ProfileEducation(ProfileLink):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="education_links")
    education = models.ForeignKey(Education, on_delete=models.CASCADE, related_name="profile_links")

    class Meta(ProfileLink.Meta):
        verbose_name = "profile education"
        verbose_name_plural = "profile education"
        constraints = [
            UniqueConstraint(
                fields=["profile", "education"], name="profiles_profileeducation_pair"
            ),
        ]

    def __str__(self):
        return f"{self.profile} · {self.education}"


class ProfileService(ProfileLink):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="service_links")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="profile_links")

    class Meta(ProfileLink.Meta):
        constraints = [
            UniqueConstraint(fields=["profile", "service"], name="profiles_profileservice_pair"),
        ]

    def __str__(self):
        return f"{self.profile} · {self.service}"


class ProfileContactChannel(ProfileLink):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="channel_links")
    channel = models.ForeignKey(
        ContactChannel, on_delete=models.CASCADE, related_name="profile_links"
    )
    is_primary = models.BooleanField(
        default=False, help_text="This profile's main channel. At most one per profile."
    )

    class Meta(ProfileLink.Meta):
        constraints = [
            UniqueConstraint(fields=["profile", "channel"], name="profiles_profilechannel_pair"),
            UniqueConstraint(
                fields=["profile"],
                condition=Q(is_primary=True),
                name="profiles_profilechannel_one_primary",
                violation_error_message="This profile already has a primary channel.",
            ),
        ]

    def __str__(self):
        return f"{self.profile} · {self.channel}"
