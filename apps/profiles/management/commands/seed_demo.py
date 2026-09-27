"""Load, or with --reset remove, the fictional demo dataset.

    uv run python manage.py seed_demo          load it (a re-run changes nothing)
    uv run python manage.py seed_demo --reset  remove every demo record, and nothing else

Everything it creates is invented (apps/profiles/demo_data/brief.md): it never contains
Odilbek's content. It goes through the same importer as real drafts, then publishes most of what
it loaded, so later phases have a complete site to render. It runs only where the settings allow
it (development and tests, never production) and only on a database holding no other content.
docs/CONTENT_IMPORT.md, "Demo content", has the details.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.profiles import demo
from apps.profiles.drafting import ManifestError


class Command(BaseCommand):
    help = "Load (or with --reset, remove) the fictional demo dataset."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Remove every demo record.")

    def handle(self, *args, **options):
        try:
            if options["reset"]:
                self.report_reset(demo.reset())
            else:
                if not settings.DEMO_CONTENT_ALLOWED:
                    raise CommandError(
                        "These settings do not allow demo content (DEMO_CONTENT_ALLOWED). The "
                        "fictional dataset is for development and tests, never for the real site."
                    )
                self.report_seed(*demo.seed())
        except ManifestError as exc:
            raise CommandError("Nothing was changed.\n  " + "\n  ".join(exc.messages)) from exc

    def report_seed(self, report, review):
        for section, outcomes in report.summary().items():
            counts = ", ".join(f"{count} {outcome}" for outcome, count in outcomes.items())
            self.stdout.write(f"  {section}: {counts}")
        if not review.published and not review.kept:
            self.stdout.write(
                self.style.SUCCESS("\nThe demo dataset was already in place; nothing changed.")
            )
            return
        drafts = ", ".join(f"{section} '{key}'" for section, key in review.kept)
        self.stdout.write(
            f"\nPublished {len(review.published)} records. Kept {len(review.kept)} as "
            f"unpublished drafts, to exercise the visibility rules: {drafts}."
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Demo dataset loaded. Everything in it is fictional; remove it with "
                "`manage.py seed_demo --reset`."
            )
        )

    def report_reset(self, removed):
        if not removed:
            self.stdout.write(self.style.SUCCESS("No demo content to remove."))
            return
        for name, count in removed.items():
            self.stdout.write(f"  {name}: {count} removed")
        self.stdout.write(self.style.SUCCESS("Demo content removed; nothing else was touched."))
