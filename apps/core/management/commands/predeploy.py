from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Prepare the database for a new release: apply migrations, create the cache table."

    # Railway runs this as the pre-deploy command, to completion, before the new container
    # starts. A failure stops the deploy and the previous release keeps serving, so a broken
    # migration never meets traffic. Locally it is the one-step database setup.

    def handle(self, *args, **options):
        call_command("migrate", interactive=False, verbosity=options["verbosity"])
        call_command("createcachetable", verbosity=options["verbosity"])
