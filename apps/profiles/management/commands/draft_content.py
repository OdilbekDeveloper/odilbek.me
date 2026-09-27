"""Create unpublished draft records from the private draft manifest.

    uv run python manage.py draft_content --dry-run   validate and show what would happen
    uv run python manage.py draft_content             create the drafts
    uv run python manage.py draft_content --update    also refresh drafts a previous run created

The manifest is content-import/draft.json (git-ignored). docs/CONTENT_IMPORT.md describes it.
Nothing is ever published; review and publish in the admin.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.profiles.drafting import DEFAULT_ROOT, Loader, ManifestError, check_root, load_manifest


class Command(BaseCommand):
    help = "Create unpublished draft records from content-import/draft.json."

    def add_arguments(self, parser):
        parser.add_argument("--root", default=str(DEFAULT_ROOT), help="The private source folder.")
        parser.add_argument("--manifest", default="draft.json", help="Manifest file in --root.")
        parser.add_argument("--dry-run", action="store_true", help="Validate; write nothing.")
        parser.add_argument(
            "--update",
            action="store_true",
            help="Also update records a previous import created, if they are still unpublished.",
        )

    def handle(self, *args, **options):
        try:
            root = check_root(options["root"])
            manifest = load_manifest(root, options["manifest"])
            loader = Loader(root, manifest, update=options["update"])
            report = loader.plan() if options["dry_run"] else loader.apply()
        except ManifestError as exc:
            raise CommandError(
                "The manifest was not loaded; nothing was written.\n  " + "\n  ".join(exc.messages)
            ) from exc

        for section, outcomes in report.summary().items():
            counts = ", ".join(f"{count} {outcome}" for outcome, count in outcomes.items())
            self.stdout.write(f"  {section}: {counts}")
        if report.todo_records:
            total = len(report.todo_records)
            self.stdout.write(f"\nRecords still containing TODO(odilbek) ({total}):")
            for label, key, count in report.todo_records:
                self.stdout.write(f"  {label} '{key}': {count} field(s)")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run: nothing was written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nDone. Every imported record is unpublished: review it in the admin, resolve "
                    "each TODO(odilbek), then publish."
                )
            )
