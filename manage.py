#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import subprocess
import sys
import threading
from dotenv import load_dotenv

POSTGRES_SERVICE_NAME = "db"
_original_thread_excepthook = threading.excepthook


def _run_postgres_help():
    """Print friendly Postgres error, run docker logs for db, and suggest fix commands."""
    sys.stderr.write("CANNOT CONNECT TO POSTGRES. CHECK IF IT'S RUNNING.\n\n")
    project_dir = os.path.dirname(os.path.abspath(__file__))
    check_cmd = ["docker", "compose", "logs", POSTGRES_SERVICE_NAME, "--tail", "30"]
    sys.stderr.write(f"Command run: {' '.join(check_cmd)}\n\n")
    try:
        result = subprocess.run(
            check_cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        if out:
            sys.stderr.write(out + "\n")
        if err:
            sys.stderr.write(err + "\n")
        if not out and not err:
            sys.stderr.write("(No logs — container may not be running.)\n")
    except FileNotFoundError:
        sys.stderr.write("(Docker not found or not in PATH.)\n")
    except subprocess.TimeoutExpired:
        sys.stderr.write("(Command timed out.)\n")
    except Exception as e:
        sys.stderr.write(f"(Could not run docker: {e})\n")
    sys.stderr.write("\nCommands you may want to use:\n")
    sys.stderr.write("  Start Postgres:  docker compose --profile postgres up -d db\n")
    sys.stderr.write("  Check status:   docker compose ps\n")
    sys.stderr.write("  View logs:      docker compose logs db -f\n")


def _postgres_excepthook(args):
    """Replace Postgres connection errors with a short message when raised in a thread."""
    if args.exc_type is None:
        return
    try:
        from django.db.utils import OperationalError
        if issubclass(args.exc_type, OperationalError):
            _run_postgres_help()
            os._exit(1)
    except ImportError:
        pass
    _original_thread_excepthook(args)


def main():
    """Run administrative tasks."""
    load_dotenv()
    os.environ['DJANGO_SETTINGS_MODULE'] = 'force.settings'
    threading.excepthook = _postgres_excepthook
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    try:
        execute_from_command_line(sys.argv)
    except Exception as e:
        from django.db.utils import OperationalError
        if isinstance(e, OperationalError):
            _run_postgres_help()
            sys.exit(1)
        raise


if __name__ == '__main__':
    main()
