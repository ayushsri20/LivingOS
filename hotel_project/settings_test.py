"""
Settings for the isolated Rental OS test environment.

    DJANGO_SETTINGS_MODULE=hotel_project.settings_test python manage.py migrate
    DJANGO_SETTINGS_MODULE=hotel_project.settings_test python manage.py seed_test_data --reset
    DJANGO_SETTINGS_MODULE=hotel_project.settings_test python manage.py test rental

This module reuses every application setting from `hotel_project.settings`
(installed apps, middleware, templates, static/media, auth) and changes only
the database target. Nothing else about the running application differs, so a
test failure here is a real application failure rather than a test-harness
artefact.

Safety rules enforced here (and again, defensively, inside
`rental.management.commands.seed_test_data`):

  * `DATABASE_URL` must not be set. A real Postgres connection string is a
    production (or staging) signal, never a test one.
  * The database is always a *separate* SQLite file next to the development
    database. `db.sqlite3` — the working/development database — is never
    opened for writing by the test environment.
  * `manage.py test` still gets Django's own throwaway test database on top of
    this, so the suite can never leave residue in `test_db.sqlite3`.
"""

import os
from pathlib import Path

# Checked *before* importing the base settings: `hotel_project.settings` reads
# DATABASE_URL at import time, so the refusal has to happen first.
if os.environ.get("DATABASE_URL"):
    raise RuntimeError(
        "Refusing to start the Rental OS test environment: DATABASE_URL is set. "
        "The test environment only ever uses its own local SQLite file "
        "(test_db.sqlite3). Unset DATABASE_URL, or point DJANGO_SETTINGS_MODULE "
        "at hotel_project.settings instead."
    )

from .settings import *  # noqa: F401,F403  (deliberate: reuse the whole app config)
from .settings import BASE_DIR  # noqa: F401


# -----------------------------------------------------------------------------
# Environment identity
# -----------------------------------------------------------------------------

# Read by rental.testdata.guard and by the seed command. Anything that is not
# exactly "test" is refused by the destructive test-data helpers.
ENVIRONMENT = "test"

# Deliberately False: the LoginRequiredMiddleware stays in place so the suite
# exercises the real authentication behaviour. Individual test classes that
# need to bypass it override MIDDLEWARE explicitly, exactly like the existing
# rental/tests.py does.
TESTING = False

# Absolute, explicit and deliberately *not* db.sqlite3.
TEST_DATABASE_PATH = Path(BASE_DIR) / "test_db.sqlite3"

DEVELOPMENT_DATABASE_PATH = Path(BASE_DIR) / "db.sqlite3"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Plain strings, deliberately. `login_view` reports the database with
        # `isinstance(settings.DATABASES['default']['NAME'], str)`; a PosixPath
        # here makes that check fail and the login page then reports
        # "Exists = False, Size = 0" for a database that exists and is fully
        # populated. Django's own docs configure NAME as a string.
        "NAME": str(TEST_DATABASE_PATH),
        "TEST": {
            # Django still creates/uses a dedicated runner database so a test
            # run can never leave residue behind in test_db.sqlite3.
            "NAME": str(Path(BASE_DIR) / "test_db.testrunner.sqlite3"),
        },
        "OPTIONS": {"timeout": 20},
    }
}

# Nothing here may point at the development database.
assert Path(DATABASES["default"]["NAME"]).resolve() != Path(
    DEVELOPMENT_DATABASE_PATH
).resolve(), "test_db.sqlite3 must never be the development database"

DEBUG = False

ALLOWED_HOSTS = list(
    dict.fromkeys(
        [
            "127.0.0.1",
            "http://192.168.1.5:5173/",
            "localhost",
            "testserver",
            *[h for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()],
        ]
    )
)

# Keep the CSRF/session posture of development so the browser flows exercised
# during manual testing behave the same way they do locally.
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = False

LOGGING["loggers"]["django.db.backends"]["level"] = os.getenv(
    "DJANGO_LOG_LEVEL", "INFO"
)
