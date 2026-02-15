"""
Backup the database as SQL (or optionally JSON via dumpdata).
Same idea as manage.py runserver / migrate — one command, no standalone scripts.
"""
import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Backup the database to a .sql file (SQLite or PostgreSQL). Use --json for Django dumpdata instead."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", "-o",
            type=str,
            default=None,
            help="Output file path (default: backups/db_YYYY-MM-DD_HHMM.sql or .json)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Use Django dumpdata (JSON) instead of raw SQL.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Overwrite file without asking (for cron/CI).",
        )

    def handle(self, *args, **options):
        out_path = options["output"]
        use_json = options["json"]
        no_input = options["no_input"]

        if use_json:
            self._backup_json(out_path, no_input)
        else:
            self._backup_sql(out_path, no_input)

    def _default_path(self, ext):
        from django.utils.dateformat import format as date_format
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d_%H%M")
        backup_dir = Path(settings.BASE_DIR) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir / f"db_{ts}.{ext}"

    def _backup_sql(self, out_path, no_input):
        engine = settings.DATABASES["default"]["ENGINE"]
        out_path = Path(out_path or self._default_path("sql"))

        if out_path.exists() and not no_input:
            self.stdout.write(self.style.WARNING(f"File exists: {out_path}"))
            return

        out_path.parent.mkdir(parents=True, exist_ok=True)

        if "sqlite3" in engine:
            import sqlite3
            db_path = settings.DATABASES["default"]["NAME"]
            if not os.path.isabs(str(db_path)):
                db_path = os.path.join(settings.BASE_DIR, db_path)
            try:
                conn = sqlite3.connect(db_path)
                with open(out_path, "w", encoding="utf-8", newline="\n") as f:
                    for line in conn.iterdump():
                        f.write(line + "\n")
                conn.close()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"SQLite backup failed: {e}"))
                return
        elif "postgresql" in engine:
            db = settings.DATABASES["default"]
            env = os.environ.copy()
            env["PGPASSWORD"] = db.get("PASSWORD", "")
            cmd = [
                "pg_dump",
                "-h", db.get("HOST", "localhost"),
                "-p", str(db.get("PORT", "5432")),
                "-U", db.get("USER", ""),
                "-d", db["NAME"],
                "-f", str(out_path),
            ]
            try:
                subprocess.run(cmd, check=True, env=env, shell=False)
            except FileNotFoundError:
                self.stdout.write(
                    self.style.ERROR("pg_dump not found. Install PostgreSQL client or use --json for dumpdata backup.")
                )
                return
        else:
            self.stdout.write(self.style.ERROR(f"Unsupported engine: {engine}. Use --json for dumpdata backup."))
            return

        self.stdout.write(self.style.SUCCESS(f"SQL backup written to: {out_path}"))

    def _backup_json(self, out_path, no_input):
        out_path = Path(out_path or self._default_path("json"))
        if out_path.exists() and not no_input:
            self.stdout.write(self.style.WARNING(f"File exists: {out_path}"))
            return
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from django.core.management import call_command
        with open(out_path, "w", encoding="utf-8") as f:
            call_command(
                "dumpdata",
                "--natural-foreign",
                "--natural-primary",
                "--indent", "2",
                "-e", "contenttypes",
                "-e", "auth.Permission",
                stdout=f,
            )
        self.stdout.write(self.style.SUCCESS(f"JSON backup (dumpdata) written to: {out_path}"))
