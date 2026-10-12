#!/usr/bin/env python3
"""
Determinism check for the synthetic test dataset.

Hashes every *business* column of the seeded tables (excluding auto-generated
``created_at``/``updated_at`` timestamps and surrogate key ids, which legitimately
change on every re-seed), re-seeds, and compares.

    DJANGO_SETTINGS_MODULE=hotel_project.settings_test python scripts/verify_seed_determinism.py

Exits non-zero when two consecutive seeds disagree.
"""
import hashlib
import os
import subprocess
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hotel_project.settings_test")

DATABASE = ROOT / "test_db.sqlite3"

QUERIES = (
    "select id, name from rental_building order by id",
    "select number, building_id, room_type, price, agreed_rent, capacity, is_available"
    " from rental_room order by number",
    "select first_name, last_name, email, phone, room_id, is_active, check_in_date,"
    " id_number, occupancy_preference from rental_guest order by email",
    "select room_id, month, rent_amount, paid_amount, payment_status, paid_date"
    " from rental_monthlypayment order by room_id, month",
    "select room_id, month, starting_reading, ending_reading, units_consumed,"
    " rate_per_unit, bill_amount, paid_amount, bill_status, due_date"
    " from rental_electricitybill order by room_id, month",
    "select rm.number, p.month, r.payment_date, r.payment_amount, r.payment_method,"
    " r.reference_number from rental_paymentrecord r"
    " join rental_monthlypayment p on p.id = r.monthly_payment_id"
    " join rental_room rm on rm.id = p.room_id"
    " order by rm.number, p.month, r.payment_date, r.reference_number",
    "select building_name, category, amount, date, description, is_paid"
    " from rental_maintenanceexpense order by building_name, date, description",
)


def fingerprint():
    connection = sqlite3.connect(DATABASE)
    digest = hashlib.sha256()
    counts = []
    for query in QUERIES:
        rows = list(connection.execute(query))
        counts.append(len(rows))
        for row in rows:
            digest.update(repr(row).encode())
    connection.close()
    return digest.hexdigest(), counts


def seed():
    result = subprocess.run(
        [sys.executable, "manage.py", "seed_test_data", "--reset"],
        capture_output=True,
        text=True,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "hotel_project.settings_test"},
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit("seed_test_data failed")


def main():
    seed()
    first, counts = fingerprint()
    print(f"  seed #1 fingerprint : {first}")
    print(f"  row counts          : {counts}")

    seed()
    second, _ = fingerprint()
    print(f"  seed #2 fingerprint : {second}")

    if first == second:
        print("  RESULT: DETERMINISTIC — two consecutive --reset runs are identical")
        return 0
    print("  RESULT: NOT DETERMINISTIC", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
