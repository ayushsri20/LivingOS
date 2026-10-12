"""
Production safety guard for every destructive test-data operation.

The rule this module enforces is simple and absolute:

    synthetic test data may only ever be written to, or removed from, a
    database that is unambiguously a throwaway test database.

It refuses to guess. There is no ``--force`` escape hatch on purpose: a bypass
flag is exactly how test data eventually reaches production.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class UnsafeEnvironmentError(ImproperlyConfigured):
    """Raised when a test-data operation is attempted outside the test env."""


#: Substrings that mark a database file/URL as a disposable test artefact.
TEST_MARKERS = ("test", "sqlite3")


def _database_name():
    return str(settings.DATABASES.get("default", {}).get("NAME", "") or "")


def _database_engine():
    return str(settings.DATABASES.get("default", {}).get("ENGINE", "") or "")


def assert_safe_to_mutate(operation="This operation"):
    """
    Raise :class:`UnsafeEnvironmentError` unless *operation* is provably safe.

    Checks, in order:

    1. ``settings.ENVIRONMENT`` must be exactly ``"test"``.
    2. The default database must be SQLite. A ``DATABASE_URL``/Postgres
       connection is a deployment database (production or staging) and is
       refused outright.
    3. The database file name must contain ``test`` *and* end in ``.sqlite3``,
       so ``db.sqlite3`` can never qualify.
    4. The resolved path must differ from the development database path.
    5. No non-test ``TEST-DATABASE-URL``-style override may be present.

    Django's own test runner database (``test_db.testrunner.sqlite3``) also
    passes: it satisfies checks 2-4.
    """
    problems = []

    environment = str(getattr(settings, "ENVIRONMENT", "") or "")
    if environment != "test":
        problems.append(
            f'settings.ENVIRONMENT is {environment!r}, expected "test". '
            "Run with DJANGO_SETTINGS_MODULE=hotel_project.settings_test."
        )

    engine = _database_engine()
    if "sqlite3" not in engine:
        problems.append(
            f"default database engine is {engine!r}; the test environment only "
            "uses a local SQLite file (a DATABASE_URL means a deployment DB)."
        )

    name = _database_name()
    lowered = name.lower()
    if "test" not in lowered:
        problems.append(
            f'database name {name!r} does not contain "test" — refusing to treat '
            "it as a disposable test database."
        )
    if not lowered.endswith(".sqlite3"):
        problems.append(
            f'database name {name!r} is not a ".sqlite3" file — refusing to touch it.'
        )

    development_path = getattr(settings, "DEVELOPMENT_DATABASE_PATH", None)
    if development_path is not None:
        from pathlib import Path

        if Path(name).resolve() == Path(development_path).resolve():
            problems.append(
                "the configured test database is the development database "
                f"({development_path}); refusing to continue."
            )

    test_url = str(getattr(settings, "TEST_DATABASE_URL", "") or "")
    if test_url and "test" not in test_url.lower():
        problems.append(
            f"TEST_DATABASE_URL={test_url!r} does not look like a test database."
        )

    if problems:
        detail = "\n  - ".join([""] + problems)
        raise UnsafeEnvironmentError(
            f"REFUSED: {operation} would run outside the isolated test "
            f"environment.{detail}\n"
            "No data was read or written. Synthetic test data can never be "
            "seeded into a production or development database."
        )

    return True


def describe_environment():
    """Short human-readable summary used by the seed command output."""
    return {
        "environment": str(getattr(settings, "ENVIRONMENT", "")),
        "engine": _database_engine(),
        "name": _database_name(),
        "electricity_rate": str(getattr(settings, "ELECTRICITY_RATE_PER_UNIT", "")),
    }
