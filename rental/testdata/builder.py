"""
Idempotent creation and targeted reset of the synthetic dataset.

Two entry points:

``seed_dataset()``
    Create every record. Safe to re-run: existing test rows are replaced, not
    duplicated, and the result is identical every time.

``reset_dataset()``
    Remove *only* tagged test rows and re-seed. It never calls ``flush`` and
    never touches a row it did not create, so the authoritative 6-building /
    36-room structure, migrations and any non-test rows survive untouched.

Both refuse to run outside the isolated test environment — see
:mod:`rental.testdata.guard`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from ..models import (
    Building,
    ElectricityBill,
    Guest,
    MaintenanceExpense,
    MonthlyPayment,
    PaymentRecord,
    Room,
)
from . import spec
from .guard import assert_safe_to_mutate

#: Login used by the manual/browser test walkthroughs. Never a real credential:
#: it exists only in the disposable test database.
TEST_ADMIN_USERNAME = "tester"
TEST_ADMIN_PASSWORD = "TesterPass!2026"


@dataclass
class SeedReport:
    version: str
    reference_month: date
    rooms: int = 0
    residents: int = 0
    bills: int = 0
    electricity_bills: int = 0
    payment_records: int = 0
    expenses: int = 0
    removed: int = 0

    def as_lines(self):
        return [
            f"dataset version      : {self.version}",
            f"reference month      : {self.reference_month:%B %Y}",
            f"rooms                : {self.rooms}",
            f"residents            : {self.residents}",
            f"monthly bills        : {self.bills}",
            f"electricity bills    : {self.electricity_bills}",
            f"payment records      : {self.payment_records}",
            f"expenses             : {self.expenses}",
            f"rows removed first   : {self.removed}",
        ]


def electricity_rate() -> Decimal:
    """
    The application's authoritative per-unit rate.

    Read from settings every time — the dataset never hard-codes 13, so
    changing ``ELECTRICITY_RATE_PER_UNIT`` re-bills the whole dataset correctly.
    """
    return Decimal(str(settings.ELECTRICITY_RATE_PER_UNIT)).quantize(spec.CENT)


# ---------------------------------------------------------------------------
# Targeted cleanup
# ---------------------------------------------------------------------------

def remove_test_rows() -> int:
    """
    Delete only rows this seeder created.

    Deletion order respects the foreign keys: PaymentRecord cascades from
    MonthlyPayment, ElectricityBill references Guest, and MaintenanceExpense is
    standalone. Buildings and Rooms are never touched.
    """
    removed = 0

    # Bills and expenses carry the marker in their free-text fields.
    bill_ids = list(
        ElectricityBill.objects.filter(notes__startswith=spec.TAG).values_list("id", flat=True)
    )
    payment_ids = list(MonthlyPayment.objects.filter(notes__startswith=spec.TAG).values_list("id", flat=True))
    expense_ids = list(
        MaintenanceExpense.objects.filter(description__startswith=spec.TAG).values_list("id", flat=True)
    )
    record_ids = list(PaymentRecord.objects.filter(notes__startswith=spec.TAG).values_list("id", flat=True))

    removed += PaymentRecord.objects.filter(id__in=record_ids).delete()[0]
    removed += MonthlyPayment.objects.filter(id__in=payment_ids).delete()[0]
    removed += ElectricityBill.objects.filter(id__in=bill_ids).delete()[0]
    removed += MaintenanceExpense.objects.filter(id__in=expense_ids).delete()[0]

    # Residents are identifiable by their synthetic id_number.
    guests = Guest.objects.filter(id_number__startswith=spec.RESIDENT_PREFIX)
    removed += guests.count()
    # A resident may own an electricity bill that was not tagged, so clear the
    # dangling reference before the guest row disappears.
    ElectricityBill.objects.filter(guest__in=guests).update(guest=None)
    MonthlyPayment.objects.filter(guest__in=guests).update(guest=None)
    guests.delete()

    # Restore the authoritative room inventory flags. Rooms keep their ids,
    # numbers and building relationships — only the availability flag and the
    # agreed rent (which the seeder overwrites) are reset.
    Room.objects.update(is_available=True)
    _restore_agreed_rents()

    return removed


def _restore_agreed_rents():
    """Put ``agreed_rent`` back to the room's list ``price`` after a reset."""
    for room in Room.objects.all().only("id", "price", "agreed_rent"):
        if room.agreed_rent is None or room.agreed_rent != room.price:
            Room.objects.filter(pk=room.pk).update(agreed_rent=room.price)


def ensure_test_admin():
    """
    Provision the disposable test operator used by manual walkthroughs.

    Idempotent *and* self-healing: the password and staff flags are re-applied on
    every run, then verified through the real ``authenticate()`` path.

    Previously the password was only set when the row was first created. A
    ``tester`` account left behind by an earlier run, an older constant or a
    manual ``createsuperuser`` would therefore keep its old password forever, and
    every sign-in attempt would return ``POST /login/ -> 200`` (the login page
    re-rendered) instead of a 302 — with a perfectly correct-looking username
    and no error anywhere. That is exactly the failure this now prevents.
    """
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username=TEST_ADMIN_USERNAME,
        defaults={
            "email": "tester@example.invalid",
            "is_staff": True,
            "is_superuser": True,
        },
    )

    changed = created
    if not user.has_usable_password() or not user.check_password(TEST_ADMIN_PASSWORD):
        user.set_password(TEST_ADMIN_PASSWORD)
        changed = True
    if not (user.is_staff and user.is_superuser and user.is_active):
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        changed = True
    if changed:
        user.save()

    # Fail loudly at seed time rather than at the login screen.
    from django.contrib.auth import authenticate

    if authenticate(username=TEST_ADMIN_USERNAME, password=TEST_ADMIN_PASSWORD) is None:
        raise RuntimeError(
            f"The test operator {TEST_ADMIN_USERNAME!r} still cannot authenticate "
            "after provisioning. Check AUTHENTICATION_BACKENDS and is_active."
        )
    return user, created


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------

def ensure_master_data() -> dict:
    """
    Verify the authoritative property structure and stamp the synthetic rents.

    The structure itself is created by migration ``0017_building_room_relationship``
    and is never rebuilt here. This function only *checks* it — six buildings,
    six rooms each, correct prefix-to-building mapping, no duplicates — and then
    writes ``agreed_rent`` so the financial layer has realistic per-room values.
    """
    buildings = {building.name: building for building in Building.objects.all()}
    missing = [name for name in spec.BUILDING_NAMES if name not in buildings]
    if missing:
        raise RuntimeError(
            f"The authoritative building structure is incomplete: missing {missing}. "
            "Run `manage.py migrate` before seeding; the seeder never creates buildings."
        )
    unexpected = sorted(set(buildings) - set(spec.BUILDING_NAMES))
    if unexpected:
        raise RuntimeError(f"Unexpected buildings present: {unexpected}")

    rooms = {room.number: room for room in Room.objects.all()}
    if len(rooms) != 36:
        raise RuntimeError(f"Expected exactly 36 rooms, found {len(rooms)}.")

    for name, room_spec in spec.ROOMS_BY_NUMBER.items():
        room = rooms.get(name)
        if room is None:
            raise RuntimeError(f"Authoritative room {name} is missing.")
        if room.building_id != buildings[room_spec.building].id:
            raise RuntimeError(
                f"Room {name} belongs to building {room.building.name}, "
                f"expected {room_spec.building}."
            )
        Room.objects.filter(pk=room.pk).update(
            agreed_rent=Decimal(room_spec.rent), is_available=True
        )

    report = {"buildings": len(buildings), "rooms": len(rooms)}
    return report


# ---------------------------------------------------------------------------
# Residents
# ---------------------------------------------------------------------------

def create_residents(room_map) -> dict:
    """
    Create the thirty synthetic residents, one per occupied room.

    ``Guest.save()`` auto-creates a ``MonthlyPayment`` whenever a guest checks in
    with a room and a check-in date, using ``room.price`` as the rent. That is
    existing behaviour we must not fight, so the seeder creates residents with
    ``check_in_date`` unset and writes the real move-in date afterwards with a
    queryset ``update()``. The rent bill is then created deliberately below, so
    the auto-generated row never exists and ``rent_amount`` is always the agreed
    rent rather than the list price.
    """
    created = {}
    for resident in spec.RESIDENTS:
        room = room_map[resident["room"].number]
        guest = Guest.objects.create(
            first_name=resident["first_name"],
            last_name=resident["last_name"],
            email=resident["email"],
            phone=resident["phone"],
            gender=resident["gender"],
            city=resident["city"],
            state=resident["state"],
            country=resident["country"],
            zip_code=resident["zip_code"],
            id_type=resident["id_type"],
            id_number=resident["id_number"],
            college_id=resident["college_id"],
            student_college=resident["student_college"],
            room=room,
            is_active=True,
            occupancy_preference=resident["occupancy_preference"],
            notes=resident["notes"],
        )
        created[resident["code"]] = guest

    Guest.objects.filter(id_number__startswith=spec.RESIDENT_PREFIX).update(
        check_in_date=None
    )
    for resident in spec.RESIDENTS:
        Guest.objects.filter(pk=created[resident["code"]].pk).update(
            check_in_date=resident["check_in_date"]
        )

    # Occupied rooms are unavailable; the six vacant rooms stay available.
    # A queryset update is used rather than bulk_update so the flag is derived
    # from the database's own current value per room, never from a stale object.
    for room_number in room_map:
        Room.objects.filter(
            number=room_number,
            id__in=Guest.objects.filter(is_active=True).values_list("room_id", flat=True),
        ).update(is_available=False)

    return created


# ---------------------------------------------------------------------------
# Electricity, bills and payments
# ---------------------------------------------------------------------------

def _status_for(collected: Decimal, total: Decimal, room_state: str, is_reference: bool) -> str:
    """
    Map a collection onto ``MonthlyPayment.payment_status``.

    The application derives its room-facing status from the collected amount;
    ``overdue`` is a stored, business-facing label that the room-first API does
    not surface. It is preserved here for the five rooms that declare it, so the
    ledger pages and the database agree with each other.
    """
    if is_reference and room_state == "overdue":
        return "overdue"
    if collected <= 0:
        return "pending"
    if collected >= total:
        return "paid"
    return "partial"


def _electricity_status(paid: Decimal, amount: Decimal, is_reference: bool, room_state: str) -> str:
    if amount <= 0:
        return "paid"
    if paid >= amount:
        return "paid"
    if is_reference and room_state == "overdue":
        return "overdue"
    return "pending"



def create_financials(room_map, guests_by_room, admin) -> SeedReport:
    """Create electricity bills, monthly bills and payment records."""
    rate = electricity_rate()
    reference = spec.reference_month()
    report = SeedReport(version=spec.DATASET_VERSION, reference_month=reference)

    for month in spec.seeded_months():
        is_reference = month == reference
        for room_spec in spec.ROOMS:
            room = room_map[room_spec.number]
            guest = guests_by_room.get(room_spec.number)
            units = spec.room_units(room_spec, month)
            opening = spec.room_meter_start(room_spec, month)
            closing = opening + units
            electricity = spec.room_electricity(room_spec, month, rate)

            bill = ElectricityBill.objects.create(
                room=room,
                guest=guest,
                month=month,
                starting_reading=Decimal(opening),
                ending_reading=Decimal(closing),
                units_consumed=Decimal(units),
                rate_per_unit=rate,
                bill_amount=electricity,
                due_date=_due_date(month),
                notes=_tag_notes(room_spec, month, "electricity"),
            )
            report.electricity_bills += 1

            # A vacant room is not billed rent and has no resident, so it gets
            # no MonthlyPayment. Its meter still runs, which is realistic.
            if room_spec.vacant:
                bill.paid_amount = electricity
                bill.bill_status = "paid" if electricity > 0 else "pending"
                bill.paid_date = month if electricity > 0 else None
                bill.save(update_fields=["paid_amount", "bill_status", "paid_date"])
                continue

            total = spec.quantize_money(Decimal(room_spec.rent) + electricity)
            monthly = MonthlyPayment.objects.create(
                room=room,
                guest=guest,
                month=month,
                rent_amount=Decimal(room_spec.rent),
                paid_amount=Decimal("0.00"),
                payment_status="pending",
                notes=_tag_notes(room_spec, month, "rent"),
            )
            report.bills += 1

            plan = spec.collection_plan(room_spec, month, total)
            collected = Decimal("0.00")
            last_date = None
            for amount, day, method in plan:
                PaymentRecord.objects.create(
                    monthly_payment=monthly,
                    payment_date=date(month.year, month.month, day),
                    payment_amount=amount,
                    payment_method=method,
                    reference_number=f"TEST-REF-{room_spec.number}-{month:%Y%m}-{day}",
                    notes=f"{spec.TAG} {room_spec.number} {month:%Y-%m} collection",
                    created_by=admin,
                )
                collected = spec.quantize_money(collected + amount)
                last_date = date(month.year, month.month, day)
                report.payment_records += 1

            status = _status_for(collected, total, room_spec.state, is_reference)
            monthly.paid_amount = collected
            monthly.payment_status = status
            monthly.paid_date = last_date if status == "paid" else None
            monthly.save(update_fields=["paid_amount", "payment_status", "paid_date"])

            # The electricity component settles in proportion to the rent bill,
            # capped at the electricity charge itself. That keeps
            # `ElectricityBill.remaining_amount()` meaningful without inventing a
            # second, competing notion of "electricity paid".
            bill.paid_amount = min(collected, electricity)
            bill.bill_status = _electricity_status(
                bill.paid_amount, electricity, is_reference, room_spec.state
            )
            bill.paid_date = last_date if bill.bill_status == "paid" else None
            bill.save(update_fields=["paid_amount", "bill_status", "paid_date"])

    return report


def create_expenses() -> int:
    """Create the tagged maintenance expenses used by the reports pages."""
    count = 0
    for building, category, amount, when, description, paid in spec.EXPENSES:
        MaintenanceExpense.objects.create(
            building_name=building,
            category=category,
            amount=Decimal(amount),
            date=when,
            description=spec.expense_description(description),
            is_paid=paid,
        )
        count += 1
    return count


def _due_date(month: date) -> date:
    return date(month.year, month.month, spec.days_in_month(month))


def _tag_notes(room_spec, month: date, kind: str) -> str:
    codes = ", ".join(room_spec.scenario_codes) or "-"
    return (
        f"{spec.TAG} {kind} {room_spec.number} {month:%Y-%m} "
        f"[logical {room_spec.logical_number}] [scenarios {codes}]"
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def seed_dataset(reset: bool = False, operation: str = "Seeding test data") -> SeedReport:
    """
    Create the whole synthetic dataset, idempotently.

    ``reset=True`` and ``reset=False`` converge on the same final state, because
    every create is preceded by the same targeted removal. The flag only changes
    how the run is reported, so forgetting it can never leave a half-seeded
    database behind.
    """
    assert_safe_to_mutate(operation)

    with transaction.atomic():
        removed = remove_test_rows()
        master = ensure_master_data()
        admin, _ = ensure_test_admin()
        room_map = {room.number: room for room in Room.objects.all()}

        guests = create_residents(room_map)
        guests_by_room = {guest.room.number: guest for guest in guests.values()}

        report = create_financials(room_map, guests_by_room, admin)
        report.removed = removed
        report.rooms = master["rooms"]
        report.residents = len(guests)
        report.expenses = create_expenses()

    return report


def reset_dataset() -> SeedReport:
    """Remove only tagged test rows and recreate them. Never touches anything else."""
    return seed_dataset(reset=True, operation="Resetting test data")


def dataset_present() -> bool:
    """True when the synthetic dataset is already present."""
    return Guest.objects.filter(id_number__startswith=spec.RESIDENT_PREFIX).exists()


def expected_totals() -> dict:
    """
    Figures the suite asserts against.

    Derived from the spec rather than read back from the database, so a seeding
    bug cannot make a test pass by simply agreeing with itself.
    """
    rate = electricity_rate()
    reference = spec.reference_month()
    totals = {}
    for month in spec.seeded_months():
        expected = collected = outstanding = electricity_total = Decimal("0.00")
        for room_spec in spec.OCCUPIED_ROOMS:
            total = spec.room_total_bill(room_spec, month, rate)
            electricity_total += spec.room_electricity(room_spec, month, rate)
            expected += total
            plan = spec.collection_plan(room_spec, month, total)
            paid = sum((amount for amount, _day, _method in plan), Decimal("0.00"))
            collected += paid
            outstanding += max(Decimal("0.00"), total - paid)
        totals[month] = {
            "is_reference": month == reference,
            "expected": expected,
            "collected": collected,
            "outstanding": outstanding,
            "electricity": electricity_total,
        }
    return totals

