"""
Restore the database from a SQL backup file.
Replaces scripts/restore_database.sh — use: manage.py restore_db <backup.sql>.
"""
import gzip
import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Restore the database from a .sql or .sql.gz backup (from backup_db)."

    def add_arguments(self, parser):
        parser.add_argument(
            "backup_file",
            type=str,
            help="Path to backup file (e.g. backups/db_2024-01-01_1200.sql or .sql.gz)",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Do not prompt for confirmation.",
        )

    def handle(self, *args, **options):
        path = Path(options["backup_file"])
        no_input = options["no_input"]

        if not path.exists():
            self.stdout.write(self.style.ERROR(f"Backup file not found: {path}"))
            return

        if not no_input:
            self.stdout.write(self.style.WARNING("This will REPLACE the current database with the backup."))
            if input("Type 'yes' to continue: ") != "yes":
                self.stdout.write("Restore cancelled.")
                return

        engine = settings.DATABASES["default"]["ENGINE"]

        if "sqlite3" in engine:
            self._restore_sqlite(path)
        elif "postgresql" in engine:
            self._restore_postgres(path)
        else:
            self.stdout.write(self.style.ERROR(f"Unsupported engine: {engine}"))

    def _read_sql(self, path):
        if path.suffix == ".gz" or str(path).endswith(".sql.gz"):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return f.read()
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _restore_sqlite(self, path):
        db_path = settings.DATABASES["default"]["NAME"]
        if not os.path.isabs(str(db_path)):
            db_path = os.path.join(settings.BASE_DIR, db_path)
        sql = self._read_sql(path)
        connection.close()
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            conn.executescript(sql)
            conn.close()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"SQLite restore failed: {e}"))
            return
        self.stdout.write(self.style.SUCCESS(f"Restored from {path}"))

    def _restore_postgres(self, path):
        db = settings.DATABASES["default"]
        env = os.environ.copy()
        env["PGPASSWORD"] = db.get("PASSWORD", "")
        host = db.get("HOST", "localhost")
        port = str(db.get("PORT", "5432"))
        user = db.get("USER", "")
        name = db["NAME"]

        # Connect to 'postgres' to drop/recreate target DB
        base_cmd = ["psql", "-h", host, "-p", port, "-U", user]
        try:
            subprocess.run(
                base_cmd + ["-d", "postgres", "-c", f"DROP DATABASE IF EXISTS \"{name}\";"],
                check=True, env=env, capture_output=True
            )
            subprocess.run(
                base_cmd + ["-d", "postgres", "-c", f"CREATE DATABASE \"{name}\";"],
                check=True, env=env, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            self.stdout.write(self.style.ERROR(f"PostgreSQL drop/create failed: {e.stderr.decode() if e.stderr else e}"))
            return
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR("psql not found. Install PostgreSQL client."))
            return

        # Restore: feed backup into psql
        if path.suffix == ".gz" or str(path).endswith(".sql.gz"):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                sql_content = f.read()
        else:
            with open(path, "r", encoding="utf-8") as f:
                sql_content = f.read()
        proc = subprocess.Popen(
            base_cmd + ["-d", name],
            stdin=subprocess.PIPE, env=env, shell=False, text=True
        )
        proc.communicate(input=sql_content)
        if proc.returncode != 0:
            self.stdout.write(self.style.ERROR("psql restore failed."))
            return

        self.stdout.write(self.style.SUCCESS(f"Restored from {path}"))
