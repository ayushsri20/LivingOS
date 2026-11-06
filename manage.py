#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks.

    Tests always run against the isolated test environment so that any
    destructive test-data helper refuses rather than touching the working
    database. All other commands keep the legacy defaults.
    """
    if 'test' in sys.argv:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings_test')
    else:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
# restart trigger
# restart 2

# reload trigger
