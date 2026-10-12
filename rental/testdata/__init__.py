"""
Synthetic, deterministic test data for the Rental OS application.

Nothing in this package is imported by the running application. It exists only
for the isolated test environment (`hotel_project.settings_test`) and the test
suite.

Layout
------
``guard``    Production-safety checks. Nothing destructive runs without them.
``spec``     The declarative dataset: rooms, residents, meters, bills, payments.
``builder``  Idempotent creation / targeted reset of that dataset.
"""
