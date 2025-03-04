#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys

from django.utils.autoreload import DJANGO_AUTORELOAD_ENV


def run_migrations():
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(["", "migrate_schemas"])

def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "symfexit.root.settings")
    if (
        len(sys.argv) > 1
        # Explicitly only run migrate for server and worker
        and sys.argv[1] in ["runserver", "develop", "startworker"]
        # and don't run if this is the child process of a dev_server
        and os.environ.get(DJANGO_AUTORELOAD_ENV, None) is None
    ):
        run_migrations()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
