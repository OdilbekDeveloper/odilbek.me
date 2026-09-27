"""Master data: what is true about the career (docs/DATA_MODEL.md, "career").

Each project, job, skill or qualification exists exactly once. Profiles and resumes present it
through link tables with per-view overrides; nothing here is ever copied to show it differently.
Spoken languages are Skills in a category of kind `language`; LanguagePair joins two of them.
"""

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint

from apps.core import constraints as c
from apps.core.content import todo_in
from apps.core.models import (
    MediaAsset,
    MediaKind,
    Ordered,
    Publishable,
    PublishableQuerySet,
    SEOFields,
    TimeStamped,
)

IMAGES_ONLY = {"kind": MediaKind.IMAGE}


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class SkillCategoryKind(models.TextChoices):
    TECHNICAL = "technical", "Technical"
    LANGUAGE = "language", "Spoken language"
    DOMAIN = "domain", "Domain"
    TOOL = "tool", "Tool"


class SkillCategory(TimeStamped, Ordered):
    """An area of the career map (Phase 11): Backend, AI & Automation, Languages, ..."""

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=60, unique=True)
    kind = models.CharField(max_length=10, choices=SkillCategoryKind)

    class Meta(Ordered.Meta):
        verbose_name_plural = "skill categories"
        constraints = [
            c.slug_format("career_skillcategory_slug_format"),
            c.one_of("career_skillcategory_kind_valid", "kind", SkillCategoryKind),
            c.english_required("career_skillcategory_name_en", "name"),
        ]

    def __str__(self):
        return self.name


class SkillQuerySet(PublishableQuerySet):
    def languages(self):
        return self.filter(category__kind=SkillCategoryKind.LANGUAGE)


class Skill(TimeStamped, Publishable, Ordered):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=60, unique=True)
    category = models.ForeignKey(SkillCategory, on_delete=models.PROTECT, related_name="skills")
    description = models.TextField(blank=True)
    level_label = models.CharField(
        max_length=80,
        blank=True,
        help_text="As Odilbek states it, e.g. 'Native' or 'TOPIK Level 6'. Never inferred.",
    )

    objects = SkillQuerySet.as_manager()

    class Meta(Ordered.Meta):
        constraints = [
            c.slug_format("career_skill_slug_format"),
            c.english_required("career_skill_name_en", "name"),
            c.published_at_set("career_skill_published_at_set"),
            c.no_todo_when_published(
                "career_skill_no_todo_when_published",
                translated=("name", "description", "level_label"),
            ),
        ]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectStatus(models.TextChoices):
    LIVE = "live", "Live"
    IN_PROGRESS = "in_progress", "In progress"
    ARCHIVED = "archived", "Archived"
    CONCEPT = "concept", "Concept"


class ProjectQuerySet(PublishableQuerySet):
    def listed(self, include_drafts=False):
        """Projects that may appear in lists. Unlisted ones are reachable only by their own URL."""
        return self.visible(include_drafts).filter(is_listed=True)


class Project(TimeStamped, Publishable, SEOFields, Ordered):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    summary = models.CharField(max_length=300, blank=True, help_text="Required to publish.")
    context = models.TextField(blank=True)
    description = models.TextField(blank=True, help_text="Markdown.")
    highlights = models.TextField(blank=True, help_text="Markdown.")
    role = models.CharField(max_length=120, blank=True)
    # The project's life, not its publication state (that is is_published).
    project_status = models.CharField(max_length=12, choices=ProjectStatus, blank=True)
    started_on = models.DateField(null=True, blank=True)
    ended_on = models.DateField(null=True, blank=True)
    github_url = models.URLField(max_length=300, blank=True, validators=[c.validate_http_url])
    demo_url = models.URLField(max_length=300, blank=True, validators=[c.validate_http_url])
    cover = models.ForeignKey(
        MediaAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        limit_choices_to=IMAGES_ONLY,
    )
    is_featured = models.BooleanField(default=False)
    is_listed = models.BooleanField(
        default=True,
        help_text="Unlisted projects are reachable only at their own URL: never listed, never "
        "indexed, never in the sitemap.",
    )
    skills = models.ManyToManyField(Skill, blank=True, related_name="projects")

    objects = ProjectQuerySet.as_manager()

    class Meta(Ordered.Meta):
        constraints = [
            c.slug_format("career_project_slug_format"),
            c.english_required("career_project_title_en", "title"),
            c.required_to_publish("career_project_summary_to_publish", c.filled("summary_en")),
            c.http_url("career_project_github_url_http", "github_url"),
            c.http_url("career_project_demo_url_http", "demo_url"),
            c.dates_in_order("career_project_dates_in_order"),
            c.one_of(
                "career_project_status_valid", "project_status", ProjectStatus, allow_blank=True
            ),
            c.published_at_set("career_project_published_at_set"),
            c.no_todo_when_published(
                "career_project_no_todo_when_published",
                translated=(
                    "title",
                    "summary",
                    "context",
                    "description",
                    "highlights",
                    "role",
                    "seo_title",
                    "seo_description",
                ),
            ),
        ]

    def __str__(self):
        return self.title

    def publication_blockers(self):
        problems = []
        if self.cover and todo_in(self.cover, "alt_text", "caption"):
            problems.append("The cover image's alt text or caption contains a TODO marker.")
        for item in self.media.select_related("asset"):
            if todo_in(item, "caption") or todo_in(item.asset, "alt_text", "caption"):
                problems.append(f"Media #{item.pk} has a caption or alt text with a TODO marker.")
        return problems


class ProjectMedia(TimeStamped, Ordered):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="media")
    asset = models.ForeignKey(
        MediaAsset, on_delete=models.PROTECT, related_name="+", limit_choices_to=IMAGES_ONLY
    )
    caption = models.CharField(max_length=300, blank=True)

    class Meta(Ordered.Meta):
        verbose_name = "project media"
        verbose_name_plural = "project media"
        constraints = [
            UniqueConstraint(fields=["project", "asset"], name="career_projectmedia_unique_pair"),
        ]

    def __str__(self):
        return f"{self.project} · media #{self.asset_id}"


# ---------------------------------------------------------------------------
# Experience and education
# ---------------------------------------------------------------------------


class EmploymentType(models.TextChoices):
    FULL_TIME = "full_time", "Full-time"
    FREELANCE = "freelance", "Freelance"
    CONTRACT = "contract", "Contract"
    INTERNSHIP = "internship", "Internship"
    VOLUNTEER = "volunteer", "Volunteer"


class Experience(TimeStamped, Publishable, Ordered):
    role = models.CharField(max_length=120)
    organization = models.CharField(max_length=160)
    organization_url = models.URLField(max_length=300, blank=True, validators=[c.validate_http_url])
    location = models.CharField(max_length=120, blank=True)
    employment_type = models.CharField(max_length=12, choices=EmploymentType, blank=True)
    started_on = models.DateField(null=True, blank=True, help_text="Required to publish.")
    ended_on = models.DateField(null=True, blank=True, help_text="Empty means the role is current.")
    summary = models.TextField(blank=True)
    highlights = models.TextField(blank=True, help_text="Markdown.")
    skills = models.ManyToManyField(Skill, blank=True, related_name="experiences")
    projects = models.ManyToManyField(Project, blank=True, related_name="experiences")

    class Meta(Ordered.Meta):
        verbose_name_plural = "experience"
        constraints = [
            c.english_required("career_experience_role_org_en", "role", "organization"),
            c.http_url("career_experience_org_url_http", "organization_url"),
            c.dates_in_order("career_experience_dates_in_order"),
            c.one_of(
                "career_experience_type_valid",
                "employment_type",
                EmploymentType,
                allow_blank=True,
            ),
            # "Empty end date" means current, so a published role must say when it began.
            c.required_to_publish(
                "career_experience_start_to_publish", Q(started_on__isnull=False)
            ),
            c.published_at_set("career_experience_published_at_set"),
            c.no_todo_when_published(
                "career_experience_no_todo_when_published",
                translated=("role", "organization", "location", "summary", "highlights"),
            ),
        ]

    def __str__(self):
        return f"{self.role} · {self.organization}"


class EducationKind(models.TextChoices):
    DEGREE = "degree", "Degree"
    COURSE = "course", "Course"
    CERTIFICATION = "certification", "Certification"
    LANGUAGE_TEST = "language_test", "Language test"


class Education(TimeStamped, Publishable, Ordered):
    institution = models.CharField(max_length=160)
    credential = models.CharField(max_length=160, blank=True)
    field = models.CharField(max_length=160, blank=True)
    kind = models.CharField(max_length=15, choices=EducationKind, blank=True)
    started_on = models.DateField(null=True, blank=True)
    ended_on = models.DateField(null=True, blank=True)
    result = models.CharField(
        max_length=80, blank=True, help_text="As stated on the credential, e.g. 'TOPIK Level 6'."
    )
    description = models.TextField(blank=True)
    credential_url = models.URLField(max_length=300, blank=True, validators=[c.validate_http_url])
    skills = models.ManyToManyField(Skill, blank=True, related_name="education")

    class Meta(Ordered.Meta):
        verbose_name_plural = "education"
        constraints = [
            c.english_required("career_education_institution_en", "institution"),
            c.http_url("career_education_credential_url_http", "credential_url"),
            c.dates_in_order("career_education_dates_in_order"),
            c.one_of("career_education_kind_valid", "kind", EducationKind, allow_blank=True),
            c.published_at_set("career_education_published_at_set"),
            c.no_todo_when_published(
                "career_education_no_todo_when_published",
                translated=("institution", "credential", "field", "result", "description"),
            ),
        ]

    def __str__(self):
        return f"{self.credential or self.get_kind_display() or 'Education'} · {self.institution}"


# ---------------------------------------------------------------------------
# Services, languages, contact channels
# ---------------------------------------------------------------------------


class Service(TimeStamped, Publishable, Ordered):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    summary = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True, help_text="Markdown.")
    pricing_note = models.CharField(max_length=200, blank=True)
    skills = models.ManyToManyField(Skill, blank=True, related_name="services")

    class Meta(Ordered.Meta):
        constraints = [
            c.slug_format("career_service_slug_format"),
            c.english_required("career_service_title_en", "title"),
            c.published_at_set("career_service_published_at_set"),
            c.no_todo_when_published(
                "career_service_no_todo_when_published",
                translated=("title", "summary", "description", "pricing_note"),
            ),
        ]

    def __str__(self):
        return self.title


class LanguageMode(models.TextChoices):
    DOCUMENT = "document", "Document translation"
    CONSECUTIVE = "consecutive", "Consecutive interpreting"
    SIMULTANEOUS = "simultaneous", "Simultaneous interpreting"
    LOCALIZATION = "localization", "Localization"
    REVIEW = "review", "Review and proofreading"


class LanguagePairQuerySet(models.QuerySet):
    def public(self):
        """Not publishable itself: a pair is public when both of its languages are."""
        return self.filter(source__is_published=True, target__is_published=True)

    def visible(self, include_drafts=False):
        return self.all() if include_drafts else self.public()


class LanguagePair(TimeStamped, Ordered):
    source = models.ForeignKey(
        Skill,
        on_delete=models.PROTECT,
        related_name="pairs_from",
        limit_choices_to={"category__kind": SkillCategoryKind.LANGUAGE},
    )
    target = models.ForeignKey(
        Skill,
        on_delete=models.PROTECT,
        related_name="pairs_to",
        limit_choices_to={"category__kind": SkillCategoryKind.LANGUAGE},
    )
    modes = ArrayField(models.CharField(max_length=12, choices=LanguageMode))
    domains = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=300, blank=True)

    objects = LanguagePairQuerySet.as_manager()

    class Meta(Ordered.Meta):
        constraints = [
            CheckConstraint(
                condition=~Q(source=F("target")),
                name="career_languagepair_distinct",
                violation_error_message="A language pair needs two different languages.",
            ),
            UniqueConstraint(fields=["source", "target"], name="career_languagepair_unique"),
            CheckConstraint(
                condition=Q(modes__len__gte=1) & Q(modes__contained_by=LanguageMode.values),
                name="career_languagepair_modes_valid",
                violation_error_message="Choose at least one valid mode.",
            ),
        ]

    def __str__(self):
        return f"{self.source} → {self.target}"

    def clean(self):
        # Cross-table rule (PostgreSQL CHECK cannot read the category): enforced here and in
        # the admin's choices.
        for side in ("source", "target"):
            skill = getattr(self, side, None) if getattr(self, f"{side}_id", None) else None
            if skill and skill.category.kind != SkillCategoryKind.LANGUAGE:
                raise ValidationError({side: "Choose a skill from a spoken-language category."})
        if self.modes:
            self.modes = list(dict.fromkeys(self.modes))


class ChannelKind(models.TextChoices):
    EMAIL = "email", "Email"
    TELEGRAM = "telegram", "Telegram"
    WHATSAPP = "whatsapp", "WhatsApp"
    LINKEDIN = "linkedin", "LinkedIn"
    UPWORK = "upwork", "Upwork"
    GITHUB = "github", "GitHub"
    KAKAOTALK = "kakaotalk", "KakaoTalk"
    OTHER = "other", "Other"


class ContactChannel(TimeStamped, Publishable, Ordered):
    kind = models.CharField(max_length=12, choices=ChannelKind)
    label = models.CharField(max_length=80)
    url = models.URLField(max_length=300, blank=True, validators=[c.validate_http_url])
    handle = models.CharField(
        max_length=120,
        blank=True,
        help_text="E.g. an email address or @username. Email links are built from this.",
    )

    class Meta(Ordered.Meta):
        constraints = [
            c.one_of("career_contactchannel_kind_valid", "kind", ChannelKind),
            c.english_required("career_contactchannel_label_en", "label"),
            c.http_url("career_contactchannel_url_http", "url"),
            CheckConstraint(
                condition=~Q(url="") | ~Q(handle=""),
                name="career_contactchannel_has_target",
                violation_error_message="Give a URL or a handle.",
            ),
            c.published_at_set("career_contactchannel_published_at_set"),
            c.no_todo_when_published(
                "career_contactchannel_no_todo_when_published",
                translated=("label",),
                plain=("handle",),
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.label}"
