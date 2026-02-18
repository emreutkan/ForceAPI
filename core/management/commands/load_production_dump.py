"""
Load a production-style dump (flush, reset contenttypes, loaddata, reset sequences).
Replaces scripts/migrator.py — use: manage.py load_production_dump.
Use after copying datadump_clean.json to the server (e.g. from backup_db --json -o datadump_clean.json).
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models.signals import post_save, pre_save
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = "Flush DB, reload ContentTypes, load a JSON dump, reset sequences. For production data load (e.g. from datadump_clean.json)."

    def add_arguments(self, parser):
        parser.add_argument(
            "dump_file",
            nargs="?",
            default="datadump_clean.json",
            help="Fixture file to load (default: datadump_clean.json in project root).",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Run flush and load without prompting.",
        )

    def handle(self, *args, **options):
        dump_file = options["dump_file"]
        no_input = options["no_input"]

        self.stdout.write("--- Starting production dump load ---")

        self.stdout.write("Step 1: Flushing database...")
        call_command("flush", interactive=not no_input)

        self.stdout.write("Step 2: Clearing ContentTypes...")
        ContentType.objects.all().delete()

        self.stdout.write("Step 3: Running migrate (recreate ContentTypes)...")
        call_command("migrate", interactive=False)

        self.stdout.write("Step 4: Disabling post_save/pre_save signals...")
        post_receivers = post_save.receivers
        pre_receivers = pre_save.receivers
        post_save.receivers = []
        pre_save.receivers = []

        try:
            # loaddata expects a fixture label (no .json); strip extension if present
            fixture_label = dump_file.replace(".json", "") if dump_file.endswith(".json") else dump_file
            self.stdout.write(f"Step 5: Loading {dump_file}...")
            call_command("loaddata", fixture_label, ignorenonexistent=True)
            self.stdout.write(self.style.SUCCESS("Data imported."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Load failed: {e}"))
            raise
        finally:
            post_save.receivers = post_receivers
            pre_save.receivers = pre_receivers
            self.stdout.write("Signals restored.")

        self.stdout.write("Step 6: Resetting sequences...")
        apps = ["user", "exercise", "workout", "body_measurements"]
        output = StringIO()
        try:
            call_command("sqlsequencereset", *apps, stdout=output)
            sql = output.getvalue()
            if sql:
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                self.stdout.write(self.style.SUCCESS("Sequences reset."))
            else:
                self.stdout.write("No sequences to reset.")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Sequence reset warning: {e}"))

        self.stdout.write(self.style.SUCCESS("--- Production dump load completed ---"))
