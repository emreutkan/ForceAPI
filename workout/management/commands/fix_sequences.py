"""
Reset PostgreSQL sequences for workout app tables.
Run after a DB restore/import so the next INSERT gets a valid id instead of
"duplicate key value violates unique constraint ... Key (id)=(N) already exists."

Usage (in Docker):
  docker compose exec web python manage.py fix_sequences
"""
from django.core.management.base import BaseCommand
from django.db import connection


# Tables that use an id sequence (serial/bigserial)
WORKOUT_TABLES = [
    "workout_workout",
    "workout_workoutexercise",
    "workout_exerciseset",
    "workout_templateworkout",
    "workout_templateworkoutexercise",
    "workout_trainingresearch",
    "workout_musclerecovery",
    "workout_workoutmusclerecovery",
    "workout_cnsrecovery",
]


class Command(BaseCommand):
    help = "Reset id sequences for workout app tables (run after DB restore)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print what would be done.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with connection.cursor() as cursor:
            for table in WORKOUT_TABLES:
                cursor.execute(
                    """
                    SELECT pg_get_serial_sequence(%s, 'id')
                    """,
                    [table],
                )
                row = cursor.fetchone()
                if not row or not row[0]:
                    self.stdout.write(
                        self.style.WARNING(f"No sequence for {table}.id, skipping.")
                    )
                    continue
                seq_name = row[0]
                if dry_run:
                    cursor.execute(
                        "SELECT COALESCE(MAX(id), 0) FROM " + table,
                    )
                    max_id = cursor.fetchone()[0]
                    self.stdout.write(
                        f"Would set {seq_name} to {max_id} (next id = {max_id + 1})"
                    )
                    continue
                sql = f"""
                    SELECT setval(
                        %s,
                        COALESCE((SELECT MAX(id) FROM "{table}"), 0)
                    )
                """
                cursor.execute(sql, [seq_name])
                next_val = cursor.fetchone()[0]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{table}: sequence set, next id = {next_val + 1}"
                    )
                )
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS("Done. Create workout / recovery inserts should work now.")
            )
