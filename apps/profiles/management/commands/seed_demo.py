"""Fill a development database with obviously fictional content.

Everything here is invented: "Alex Demo", "Example Project", "Fictional Company", addresses at
example.com. It never contains Odilbek's real content. Every demo slug starts with "demo-".

    uv run python manage.py seed_demo          create or refresh the demo content (idempotent)
    uv run python manage.py seed_demo --reset  remove it again

Demo content is published (through the publish service), so later phases can render it. The
command refuses to touch a database that already holds real content: demo and real drafts must
never mix. Use a separate database, e.g. DATABASE_URL=.../portfolio_demo.
"""

import io
from datetime import date

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image

from apps.career.models import (
    ContactChannel,
    Education,
    Experience,
    LanguagePair,
    Project,
    Service,
    Skill,
    SkillCategory,
)
from apps.core import media
from apps.core.models import MediaAsset, SiteSettings
from apps.core.services import publish
from apps.profiles import services
from apps.profiles.models import Profile

PREFIX = "demo-"
OWNER = "Alex Demo"
PORTRAIT_ALT = "Demo portrait: a generated colour gradient, not a photo of anyone"
ORGANIZATIONS = ("Fictional Company", "Example Agency")
INSTITUTIONS = ("Example University", "Example Language Institute")
EMAIL = "alex.demo@example.com"
CODE_URL = "https://example.com/alex-demo"


def real_content_exists():
    """True if the database holds anything that is not this command's demo content."""
    for model in (SkillCategory, Skill, Project, Service, Profile):
        if model.objects.exclude(slug__startswith=PREFIX).exists():
            return True
    if Experience.objects.exclude(organization_en__in=ORGANIZATIONS).exists():
        return True
    if Education.objects.exclude(institution_en__in=INSTITUTIONS).exists():
        return True
    if ContactChannel.objects.exclude(handle=EMAIL).exclude(url=CODE_URL).exists():
        return True
    if MediaAsset.objects.exclude(alt_text_en=PORTRAIT_ALT).exists():
        return True
    site = SiteSettings.objects.filter(pk=1).first()
    return bool(site and site.owner_name_en not in ("", None, OWNER))


def demo_portrait_png():
    """A deterministic gradient, so re-runs produce the same file (and the same asset)."""
    size = (1600, 1000)
    across = Image.linear_gradient("L").rotate(90).resize(size)
    down = Image.linear_gradient("L").resize(size)
    image = Image.merge("RGB", (across, down, Image.new("L", size, 130)))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Create (or with --reset, remove) obviously fictional demo content."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Remove the demo content.")

    def handle(self, *args, **options):
        if real_content_exists():
            raise CommandError(
                "This database holds real (non-demo) content. Demo and real drafts must never mix: "
                "run seed_demo against a separate database, e.g. DATABASE_URL=.../portfolio_demo."
            )
        with transaction.atomic():
            if options["reset"]:
                self.reset()
                self.stdout.write(self.style.SUCCESS("Demo content removed."))
            else:
                self.seed()
                self.stdout.write(self.style.SUCCESS("Demo content is in place (all fictional)."))

    # -----------------------------------------------------------------------

    def seed(self):
        portrait, _created = media.ingest(
            ContentFile(demo_portrait_png(), name="demo-portrait.png"),
            alt_text_en=PORTRAIT_ALT,
            focal_x=0.5,
            focal_y=0.4,
        )
        site = SiteSettings.load()
        site.owner_name_en = OWNER
        site.tagline_en = "Fictional demo content for development and screenshots"
        site.location_en = "Example City"
        site.timezone = "UTC"
        site.public_email = EMAIL
        site.availability = "available"
        site.availability_note_en = "Demo only: this is not a real person"
        site.portrait = portrait
        site.full_clean()
        site.save()

        cats = {
            slug: SkillCategory.objects.update_or_create(
                slug=PREFIX + slug, defaults={"kind": kind, "name_en": name}
            )[0]
            for slug, kind, name in (
                ("engineering", "technical", "Demo Engineering"),
                ("languages", "language", "Demo Languages"),
                ("tools", "tool", "Demo Tools"),
            )
        }
        skills = {}
        for slug, cat, name, name_ko, level in (
            ("examplescript", "engineering", "Examplescript", "", ""),
            ("sample-framework", "engineering", "Sample Framework", "", ""),
            ("mock-database", "engineering", "Mock Database", "", ""),
            ("language-a", "languages", "Example Language A", "예시 언어 A", "Native (demo)"),
            ("language-b", "languages", "Example Language B", "예시 언어 B", "Advanced (demo)"),
            ("toolkit", "tools", "Demo Toolkit", "", ""),
        ):
            skills[slug] = Skill.objects.update_or_create(
                slug=PREFIX + slug,
                defaults={
                    "category": cats[cat],
                    "name_en": name,
                    "name_ko": name_ko,
                    "level_label_en": level,
                },
            )[0]

        one = self._project(
            "example-project-one",
            "Example Project One",
            "예시 프로젝트 1",
            "A fictional project used to preview the site.",
            status="live",
            started=date(2023, 2, 1),
            ended=date(2023, 9, 1),
            featured=True,
            skills=[skills["examplescript"], skills["sample-framework"], skills["mock-database"]],
        )
        two = self._project(
            "example-project-two",
            "Example Project Two",
            "",
            "A second fictional project, still in progress.",
            status="in_progress",
            started=date(2024, 5, 1),
            skills=[skills["examplescript"], skills["toolkit"]],
        )
        self._project(
            "example-unlisted-project",
            "Example Unlisted Project",
            "",
            "A fictional project reachable only by its own URL.",
            status="archived",
            listed=False,
            skills=[skills["mock-database"]],
        )

        engineer, _ = Experience.objects.update_or_create(
            organization_en=ORGANIZATIONS[0],
            role_en="Demo Backend Engineer",
            defaults={
                "employment_type": "full_time",
                "started_on": date(2020, 1, 1),
                "ended_on": date(2022, 6, 1),
                "summary_en": "Fictional role at a fictional company.",
            },
        )
        engineer.skills.set([skills["examplescript"], skills["sample-framework"]])
        engineer.projects.set([one])
        interpreter, _ = Experience.objects.update_or_create(
            organization_en=ORGANIZATIONS[1],
            role_en="Demo Interpreter",
            defaults={
                "employment_type": "freelance",
                "started_on": date(2022, 7, 1),
                "ended_on": None,
                "summary_en": "Fictional interpreting work.",
            },
        )
        interpreter.skills.set([skills["language-a"], skills["language-b"]])

        degree, _ = Education.objects.update_or_create(
            institution_en=INSTITUTIONS[0],
            defaults={
                "credential_en": "BSc (demo)",
                "field_en": "Example Studies",
                "kind": "degree",
                "started_on": date(2015, 9, 1),
                "ended_on": date(2019, 6, 1),
            },
        )
        language_test, _ = Education.objects.update_or_create(
            institution_en=INSTITUTIONS[1],
            defaults={
                "credential_en": "Example Language Test",
                "kind": "language_test",
                "ended_on": date(2021, 5, 1),
                "result_en": "Level Demo",
            },
        )
        service, _ = Service.objects.update_or_create(
            slug=PREFIX + "example-service",
            defaults={"title_en": "Example Service", "summary_en": "A fictional service."},
        )
        LanguagePair.objects.update_or_create(
            source=skills["language-a"],
            target=skills["language-b"],
            defaults={"modes": ["document", "consecutive"], "domains_en": "Demo domains"},
        )
        email, _ = ContactChannel.objects.update_or_create(
            kind="email", handle=EMAIL, defaults={"label_en": "Email"}
        )
        code, _ = ContactChannel.objects.update_or_create(
            kind="github", url=CODE_URL, defaults={"label_en": "Code (demo)"}
        )

        for record in (
            *skills.values(),
            engineer,
            interpreter,
            degree,
            language_test,
            service,
            email,
            code,
        ):
            publish(record)

        home = self._profile("home", "home", "Demo Home", "Alex Demo: a fictional placeholder")
        about = self._profile("about", "about", "Demo About", "About the fictional Alex Demo")
        developer = self._profile(
            "developer",
            "role",
            "Demo Developer",
            "A fictional developer profile",
            router_prompt="I need something built (demo)",
            languages=["en", "ko"],
        )
        translator = self._profile(
            "translator",
            "role",
            "Demo Translator",
            "A fictional translator profile",
            router_prompt="I need a language expert (demo)",
            languages=["en", "ko"],
            hero_variant="bilingual",
            contact_form_variant="language_request",
        )

        self._sections(home, ["profile_router", "evidence_strip", "projects"])
        self._sections(about, ["about", "experience", "education"])
        self._sections(
            developer, ["about", "skills", "projects", "experience", "education", "contact"]
        )
        self._sections(
            translator,
            ["about", "language_pairs", "services", "experience", "education", "contact"],
        )

        for project, featured in ((one, True), (two, False)):
            services.link(developer, project, is_featured=featured)
            services.link(home, project)
        services.set_primary_profile(one, developer)
        services.set_primary_profile(two, developer)
        for slug in ("examplescript", "sample-framework", "mock-database", "toolkit"):
            services.link(developer, skills[slug], is_primary=slug == "examplescript")
        for slug in ("language-a", "language-b"):
            services.link(translator, skills[slug], is_primary=True)
        services.link(developer, engineer)
        services.link(
            translator,
            interpreter,
            summary_override_en="Fictional interpreting, worded for the translator profile.",
        )
        services.link(about, engineer)
        services.link(about, interpreter)
        for profile in (developer, about):
            services.link(profile, degree)
        services.link(translator, language_test)
        services.link(translator, service)
        services.link(developer, email, is_primary=True)
        services.link(developer, code)
        services.link(translator, email, is_primary=True)

        for profile in (home, about, developer, translator):
            publish(profile)

    def _project(self, slug, title, title_ko, summary, *, skills, listed=True, **kwargs):
        project, _ = Project.objects.update_or_create(
            slug=PREFIX + slug,
            defaults={
                "title_en": title,
                "title_ko": title_ko,
                "summary_en": summary,
                "project_status": kwargs.get("status", ""),
                "started_on": kwargs.get("started"),
                "ended_on": kwargs.get("ended"),
                "is_featured": kwargs.get("featured", False),
                "is_listed": listed,
            },
        )
        project.skills.set(skills)
        publish(project)
        return project

    def _profile(self, slug, kind, name, headline, **fields):
        profile, _ = Profile.objects.update_or_create(
            slug=PREFIX + slug,
            defaults={"kind": kind, "name_en": name, "headline_en": headline, **fields},
        )
        return profile

    def _sections(self, profile, section_types):
        existing = set(profile.sections.values_list("section_type", flat=True))
        for section_type in section_types:
            if section_type not in existing:
                services.add_section(profile, section_type)

    # -----------------------------------------------------------------------

    def reset(self):
        Profile.objects.filter(slug__startswith=PREFIX).delete()
        LanguagePair.objects.filter(source__slug__startswith=PREFIX).delete()
        Project.objects.filter(slug__startswith=PREFIX).delete()
        Experience.objects.filter(organization_en__in=ORGANIZATIONS).delete()
        Education.objects.filter(institution_en__in=INSTITUTIONS).delete()
        Service.objects.filter(slug__startswith=PREFIX).delete()
        ContactChannel.objects.filter(handle=EMAIL).delete()
        ContactChannel.objects.filter(url=CODE_URL).delete()
        Skill.objects.filter(slug__startswith=PREFIX).delete()
        SkillCategory.objects.filter(slug__startswith=PREFIX).delete()
        SiteSettings.objects.filter(pk=1, owner_name_en=OWNER).delete()
        MediaAsset.objects.filter(alt_text_en=PORTRAIT_ALT).delete()
