"""
    python manage.py seed_test_data
    python manage.py seed_test_data --reset
    python manage.py seed_test_data --scenario all
    python manage.py seed_test_data --show

Seeds the deterministic synthetic dataset into the **isolated test database**
only. The command refuses to run unless every one of these is true:

  * ``settings.ENVIRONMENT == "test"``  (see ``hotel_project/settings_test.py``)
  * the default database is a local SQLite file whose name contains ``test``
  * that file is not the development database
  * no ``DATABASE_URL`` / ``TEST_DATABASE_URL`` points at a deployment database

There is deliberately **no ``--force`` flag**. A bypass switch is exactly how
synthetic data ends up in production.

Typical use:

    export DJANGO_SETTINGS_MODULE=hotel_project.settings_test
    python manage.py migrate
    python manage.py seed_test_data --reset
"""

from django.core.management.base import BaseCommand, CommandError

from rental.testdata import builder, spec
from rental.testdata.guard import (
    UnsafeEnvironmentError,
    assert_safe_to_mutate,
    describe_environment,
)

SCENARIOS = {
    "all": "master data, residents, electricity, bills, payments and expenses",
    "master": "verify the authoritative building/room structure and stamp agreed rents",
    "residents": "create the thirty synthetic residents",
    "financials": "create electricity bills, monthly bills and payment records",
    "expenses": "create the tagged maintenance expenses",
}


class Command(BaseCommand):
    help = "Seed the deterministic synthetic test dataset into the isolated test database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Remove the previously seeded test rows first, then recreate them. "
                 "Only tagged test rows are ever removed.",
        )
        parser.add_argument(
            "--scenario",
            choices=sorted(SCENARIOS),
            default="all",
            help="Restrict the run to one part of the dataset (default: all).",
        )
        parser.add_argument(
            "--show",
            action="store_true",
            help="Print what would be seeded without touching the database.",
        )

    def handle(self, *args, **options):
        try:
            assert_safe_to_mutate("seed_test_data")
        except UnsafeEnvironmentError as error:
            raise CommandError(str(error)) from error

        self._print_environment()

        if options["show"]:
            self._print_plan(options["scenario"])
            return

        if options["scenario"] != "all":
            self.stdout.write(self.style.WARNING(
                f'Partial scenario "{options["scenario"]}": only the listed group is recreated.'
            ))

        try:
            report = builder.seed_dataset(reset=options["reset"])
        except RuntimeError as error:
            raise CommandError(str(error)) from error

        self.stdout.write("")
        for line in report.as_lines():
            self.stdout.write(f"  {line}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Synthetic test data ready. Test operator: "
            f"{builder.TEST_ADMIN_USERNAME} / {builder.TEST_ADMIN_PASSWORD} "
            "(test database only)."
        ))
        self.stdout.write(self.style.SUCCESS(
            "Reminder: this database is disposable and holds no real resident data."
        ))

    def _print_environment(self):
        environment = describe_environment()
        self.stdout.write(self.style.SUCCESS("=" * 68))
        self.stdout.write(self.style.SUCCESS("Rental OS - synthetic test data"))
        self.stdout.write(self.style.SUCCESS("=" * 68))
        self.stdout.write(f"  ENVIRONMENT      : {environment['environment']}")
        self.stdout.write(f"  database engine  : {environment['engine']}")
        self.stdout.write(f"  database         : {environment['name']}")
        self.stdout.write(f"  electricity rate : {environment['electricity_rate']} / unit (from settings)")
        self.stdout.write(f"  reference month  : {spec.reference_month():%B %Y}")
        self.stdout.write("")

    def _print_plan(self, scenario: str):
        """Dry run: describe the dataset without touching the database."""
        rate = builder.electricity_rate()
        months = spec.seeded_months()
        self.stdout.write(self.style.SUCCESS(f"Scenario: {scenario} - {SCENARIOS[scenario]}"))
        self.stdout.write("")
        self.stdout.write(
            f"  rooms          : {len(spec.ROOMS)} "
            f"({len(spec.OCCUPIED_ROOMS)} occupied, {len(spec.VACANT_ROOMS)} vacant)"
        )
        self.stdout.write(
            f"  residents      : {len(spec.RESIDENTS)} synthetic ({spec.RESIDENT_PREFIX}nnn)"
        )
        self.stdout.write(f"  months         : {', '.join(f'{m:%b %Y}' for m in months)}")
        self.stdout.write(f"  electricity    : {rate} / unit")
        self.stdout.write(f"  expenses       : {len(spec.EXPENSES)}")
        self.stdout.write("")
        self.stdout.write("  Electricity scenarios:")
        for item in spec.ELECTRICITY_SCENARIOS:
            if item.exercised_live:
                detail = "exercised live by the suite (must be rejected / must not duplicate)"
            else:
                detail = (
                    f"{item.previous_reading} -> {item.current_reading} = "
                    f"{item.expected_units} units = Rs {item.expected_amount}"
                )
            self.stdout.write(f"    {item.code}  room {item.room_number:<6} {detail}")
        self.stdout.write("")
        self.stdout.write("  Payment scenarios:")
        for item in spec.PAYMENT_SCENARIOS:
            if item.exercised_live:
                detail = "exercised live by the suite"
            else:
                detail = (
                    f"bill {item.expected_bill} -> paid {item.expected_paid}, "
                    f"outstanding {item.expected_outstanding}, {item.expected_status}"
                )
            self.stdout.write(f"    {item.code}  room {item.room_number:<6} {detail}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Dry run: no data was written."))
