"""
The declarative synthetic dataset.

Design rules
------------
* **Deterministic.** No ``random``. Every value is either written out here or
  derived by an integer formula, so ``--reset`` reproduces byte-identical
  records and test assertions can pin exact figures.
* **Realistic.** Meter readings form a continuous chain across months (a meter
  keeps running whether or not a room is occupied), monthly consumption sits in
  the 20-100 unit band, and collection behaviour varies room to room the way a
  real rent register does.
* **Internally consistent.** Every rent, unit, bill, payment and status below is
  derived from one source of truth, so the dashboard, the reports and the
  room-first API cannot disagree with each other.
* **Obviously synthetic.** Residents are ``TEST-RES-nnn``; no real names,
  e-mail addresses or phone numbers appear anywhere.
* **The handwritten rent-register images are not a data source.** They informed
  only the *shape* of the operation (room-wise rent + metered electricity,
  collected across a month in instalments). Every number here is new.

Room numbering
--------------
The authoritative structure already in the database is ``A-101..F-106`` mapped
to buildings ``M1, 1, 2, 3, 4, 5`` by migration ``0017_building_room_relationship``.
Those exact room numbers and building relationships are preserved untouched.
:attr:`RoomSpec.logical_number` exposes the familiar ``M-103`` / ``203`` style
alias used in the operating brief, purely as a lookup helper.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.utils import timezone


DATASET_VERSION = "2026.10-r1"

#: Authoritative building names, in the order the application sorts them.
BUILDING_NAMES = ("M1", "1", "2", "3", "4", "5")

#: Room-number prefix -> building name, exactly as migration 0017 defined it.
PREFIX_TO_BUILDING = {"A": "M1", "B": "1", "C": "2", "D": "3", "E": "4", "F": "5"}

#: Number of months of history seeded before the reference month.
HISTORY_MONTH_COUNT = 3

#: Marker written into notes/description so a reset can find test rows only.
TAG = "TEST-DATASET"
RESIDENT_PREFIX = "TEST-RES-"

#: Day-of-month ladder used for collection dates.
PAYMENT_DATE_LADDER = (1, 2, 4, 6, 8, 10, 12, 15, 18, 22, 25, 28)

#: Payment methods cycled deterministically so history shows variety.
PAYMENT_METHODS = ("cash", "upi", "bank_transfer", "card", "check")

#: Collection ratio applied to each room-month in the history, cycled per
#: room/month. A real rent register is not uniform: most rooms settle, some pay
#: in instalments, a few are still short at month end.
COLLECTION_RATIOS = (
    1.00, 1.00, 0.65, 1.00, 0.40, 1.00, 0.85, 1.00,
    0.00, 1.00, 0.55, 1.00, 1.00, 0.75, 1.00, 0.30,
)

#: Every Nth resident declares a shared-room preference.
SHARED_PREFERENCE_EVERY = 3

CENT = Decimal("0.01")


def quantize_money(value) -> Decimal:
    """Every amount in the dataset is exactly two decimals."""
    return Decimal(str(value)).quantize(CENT)


# ---------------------------------------------------------------------------
# Electricity edge-case scenarios (operating brief, section 7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ElectricityScenario:
    code: str
    description: str
    room_number: str
    previous_reading: int
    current_reading: int
    expected_units: int
    expected_amount: str
    #: True when the suite must perform this scenario live (it has to be
    #: rejected, or has to prove that repeating it changes nothing) instead of
    #: seeding it as ordinary data. Live scenarios read their numbers from the
    #: room's own meter chain, so ``previous_reading``/``current_reading`` are
    #: ``None`` and the suite derives them.
    exercised_live: bool = False


ELECTRICITY_SCENARIOS = (
    ElectricityScenario("EC-001", "Normal consumption (35 units)", "A-104", 1240, 1275, 35, "455.00"),
    ElectricityScenario("EC-002", "Zero consumption, meter unchanged", "B-105", 1300, 1300, 0, "0.00"),
    ElectricityScenario("EC-003", "High consumption (500 units)", "D-105", 1000, 1500, 500, "6500.00"),
    # EC-004 to EC-006 are performed live by the suite, so their readings are
    # expressed as an offset from the room's real previous reading rather than
    # as absolute numbers. A hard-coded meter value would silently drift out of
    # step with the room's own chained history and stop testing what it claims.
    ElectricityScenario("EC-004", "Reading below the previous one - must be rejected", "A-102", None, None, None, None, True),
    ElectricityScenario("EC-005", "Missing current reading - must be rejected", "A-102", None, None, None, None, True),
    ElectricityScenario("EC-006", "Duplicate generation - must not double-charge", "A-101", None, None, None, None, True),
)


# ---------------------------------------------------------------------------
# Payment scenarios (operating brief, section 9)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaymentScenario:
    code: str
    description: str
    room_number: str
    expected_bill: str
    #: Each entry is (amount, day-of-month, method).
    instalments: tuple = ()
    expected_paid: str = "0.00"
    expected_outstanding: str = "0.00"
    expected_status: str = "DUE"
    #: True when the suite performs the transaction live instead of seeding it.
    exercised_live: bool = False


PAYMENT_SCENARIOS = (
    PaymentScenario(
        "PAY-001", "Full payment in one transaction",
        "A-104", "6655.00", (("6655.00", 2, "cash"),),
        "6655.00", "0.00", "PAID",
    ),
    PaymentScenario(
        "PAY-002", "Partial payment against a 7345.00 bill",
        "A-103", "7345.00", (("4000.00", 2, "upi"),),
        "4000.00", "3345.00", "PARTIAL",
    ),
    PaymentScenario(
        "PAY-003", "No payment collected yet",
        "A-106", "6455.00", (),
        "0.00", "6455.00", "DUE",
    ),
    PaymentScenario(
        "PAY-004", "Three instalments summing to the exact bill",
        "C-101", "7250.00",
        (("2500.00", 1, "cash"), ("2000.00", 2, "upi"), ("2750.00", 4, "bank_transfer")),
        "7250.00", "0.00", "PAID",
    ),
    PaymentScenario(
        "PAY-005", "Overpayment attempt of 8000.00 against a 7250.00 bill",
        "C-102", "7250.00", (("8000.00", 4, "cash"),),
        "0.00", "7250.00", "DUE", True,
    ),
)


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoomSpec:
    number: str
    building: str
    #: Agreed synthetic rent, always inside the 5500-8000 band.
    rent: str
    #: Units consumed per seeded month: July, August, September, October.
    units: tuple = (0, 0, 0, 0)
    #: Meter reading at the start of the oldest seeded month. ``None`` means
    #: "derive as 1000 + index * 13"; an explicit value is used where readings
    #: must land on an exact scenario figure.
    meter_base: int = None
    #: Reference-month state: paid | partial | pending | overdue | vacant.
    state: str = "paid"
    #: Explicit reference-month collection total; ``None`` derives it from ``state``.
    reference_paid: str = None
    scenario_codes: tuple = ()
    #: Alias in the operating brief's notation, e.g. ``A-103`` -> ``M-103``.
    logical_number: str = field(default="", compare=False)

    @property
    def vacant(self) -> bool:
        return self.state == "vacant"


def _logical_number(number: str) -> str:
    """
    Alias in the operating brief's notation.

    ``A-103`` -> ``M-103`` (building M1), ``B-103`` -> ``103`` (building 1),
    ``C-103`` -> ``203`` (building 2), and so on. Without the leading floor
    digit, ``C-101`` and ``B-101`` would collide, so the alias has to carry it.
    """
    prefix, _, digits = number.partition("-")
    building = PREFIX_TO_BUILDING[prefix]
    floor = "0" if building == "M1" else str(building)
    return f"M-{digits}" if building == "M1" else f"{floor}-{digits}"


# Deliberate mix in the reference month (operating brief, section 5):
#   paid      13 rooms  (>= 12 required)
#   partial    7 rooms  (>=  7 required)
#   pending    5 rooms with nothing collected
#   overdue    5 rooms  (>=  5 required), two of which collected nothing at all,
#                      so 7 rooms are "unpaid" in the sense of no collection
#   vacant     6 rooms, one per building, no resident and no rent bill
#
# Rents deliberately span 5500-7800 so no test may assume a universal rent.
_ROWS = (
    # number  bldg rent    jul  aug  sep  oct  base  state     ref_paid scenarios
    ("A-101", "M1", "7500",  46,  52,  58,  61, None, "paid",    None, ()),
    ("A-102", "M1", "7200",  38,  44,  49,  55, None, "partial", None, ()),
    ("A-103", "M1", "6500",  47,  53,  59,  65, None, "partial", None, ("PAY-002",)),
    ("A-104", "M1", "6200",  70,  65,  66,  35, 1039, "paid",    None, ("PAY-001", "EC-001")),
    ("A-105", "M1", "6500",  29,  63,  58,  60, None, "vacant",  None, ()),
    ("A-106", "M1", "6000",  41,  46,  52,  35, None, "pending", None, ("PAY-003",)),
    ("B-101", "1",  "5800",  29,  45,  50,  55, None, "paid",    None, ()),
    ("B-102", "1",  "5600",  31,  39,  44,  49, None, "vacant",  None, ()),
    ("B-103", "1",  "6200",  72,  35,  40,  45, None, "overdue", "0.00", ()),
    ("B-104", "1",  "5900",  41,  56,  51,  54, None, "paid",    None, ()),
    ("B-105", "1",  "6400",  55,  60,  55,   0, 1130, "pending", None, ("EC-002",)),
    ("B-106", "1",  "5500",  27,  48,  53,  57, None, "paid",    None, ()),
    ("C-101", "2",  "6600",  39,  44,  49,  50, None, "paid",    None, ("PAY-004",)),
    ("C-102", "2",  "6600",  42,  47,  51,  50, None, "pending", None, ("PAY-005",)),
    ("C-103", "2",  "7000",  34,  60,  55,  58, None, "paid",    None, ()),
    ("C-104", "2",  "6400",  36,  41,  46,  44, None, "overdue", None, ()),
    ("C-105", "2",  "5800",  31,  51,  56,  60, None, "paid",    None, ()),
    ("C-106", "2",  "7200",  37,  43,  48,  53, None, "vacant",  None, ()),
    ("D-101", "3",  "5500",  26,  45,  50,  55, None, "paid",    None, ()),
    ("D-102", "3",  "6100",  39,  37,  42,  47, None, "pending", None, ()),
    ("D-103", "3",  "6300",  30,  66,  61,  65, None, "vacant",  None, ()),
    ("D-104", "3",  "6800",  43,  58,  53,  57, None, "partial", None, ()),
    ("D-105", "3",  "5600", 110, 115, 135, 500,  640, "overdue", None, ("EC-003",)),
    ("D-106", "3",  "6900",  37,  40,  45,  50, None, "paid",    None, ()),
    ("E-101", "4",  "6200",  32,  54,  49,  53, None, "paid",    None, ()),
    ("E-102", "4",  "5900",  28,  33,  38,  43, None, "pending", None, ()),
    ("E-103", "4",  "7100",  61,  66,  70,  61, None, "partial", None, ()),
    ("E-104", "4",  "6500",  35,  46,  51,  56, None, "vacant",  None, ()),
    ("E-105", "4",  "5700",  36,  68,  63,  67, None, "partial", None, ()),
    ("E-106", "4",  "6000",  39,  44,  48,  40, None, "overdue", "0.00", ()),
    ("F-101", "5",  "7800",  24,  47,  52,  57, None, "vacant",  None, ()),
    ("F-102", "5",  "6700",  33,  50,  55,  59, None, "partial", None, ()),
    ("F-103", "5",  "5500",  25,  57,  52,  56, None, "paid",    None, ()),
    ("F-104", "5",  "6400",  47,  41,  46,  47, None, "overdue", None, ()),
    ("F-105", "5",  "7000",  30,  64,  59,  63, None, "partial", None, ()),
    ("F-106", "5",  "5800",  42,  35,  40,  45, None, "paid",    None, ()),
)


ROOMS = tuple(
    RoomSpec(
        number=row[0],
        building=row[1],
        rent=row[2],
        units=(row[3], row[4], row[5], row[6]),
        meter_base=row[7],
        state=row[8],
        reference_paid=row[9],
        scenario_codes=row[10],
        logical_number=_logical_number(row[0]),
    )
    for row in _ROWS
)

assert len(ROOMS) == 36, "the authoritative inventory is 36 rooms"
assert len({room.number for room in ROOMS}) == 36, "room numbers must be unique"
assert sum(1 for room in ROOMS if room.vacant) == 6, "exactly six vacant rooms"
assert all(
    sum(1 for room in ROOMS if room.building == name) == 6 for name in BUILDING_NAMES
), "six rooms per building"
assert all(
    PREFIX_TO_BUILDING[room.number.partition("-")[0]] == room.building for room in ROOMS
), "room prefix must match its building"
assert all(
    Decimal("5500") <= Decimal(room.rent) <= Decimal("8000") for room in ROOMS
), "every agreed rent stays inside the agreed 5500-8000 band"

ROOMS_BY_NUMBER = {room.number: room for room in ROOMS}
OCCUPIED_ROOMS = tuple(room for room in ROOMS if not room.vacant)
VACANT_ROOMS = tuple(room for room in ROOMS if room.vacant)

assert len(OCCUPIED_ROOMS) == 30, "thirty occupied rooms"


def room_by_logical_number(logical_number: str) -> RoomSpec:
    """Look a room up by its operating-brief alias (``M-103`` -> ``A-103``)."""
    for room in ROOMS:
        if room.logical_number.lower() == str(logical_number).lower():
            return room
    raise KeyError(logical_number)


def resident_index(room: RoomSpec):
    """1-based resident number for an occupied room, ``None`` when vacant."""
    for position, candidate in enumerate(OCCUPIED_ROOMS, start=1):
        if candidate.number == room.number:
            return position
    return None




# ---------------------------------------------------------------------------
# Residents
# ---------------------------------------------------------------------------

#: Residents who moved in recently; everyone else is a longer-standing tenant.
#: Real 2026 dates, so date rendering and sorting behave normally.
RECENT_CHECK_INS = {
    13: date(2026, 9, 12),
    19: date(2026, 10, 1),
    24: date(2026, 8, 20),
    28: date(2026, 10, 3),
}

#: One long-term resident per month of 2026, so tenure sorting has no ties.
LONG_TERM_CHECK_INS = {
    2: date(2026, 1, 5),
    5: date(2026, 2, 11),
    9: date(2026, 3, 18),
    14: date(2026, 4, 2),
    21: date(2026, 5, 23),
    27: date(2026, 6, 9),
}


def resident_spec(index: int) -> dict:
    """Resident ``index`` is 1-based; returns synthetic field values only."""
    room = OCCUPIED_ROOMS[index - 1]
    code = f"{RESIDENT_PREFIX}{index:03d}"
    if index in RECENT_CHECK_INS:
        check_in = RECENT_CHECK_INS[index]
    elif index in LONG_TERM_CHECK_INS:
        check_in = LONG_TERM_CHECK_INS[index]
    else:
        # Everyone else moved in earlier in 2026 at varied dates.
        check_in = date(2026, 1 + (index % 7), 1 + ((index * 5) % 27))
    return {
        "index": index,
        "code": code,
        "first_name": "TEST",
        "last_name": f"RES-{index:03d}",
        "full_name": f"TEST RES-{index:03d}",
        # `.invalid` is reserved by RFC 2606, so this can never reach a mailbox.
        "email": f"test-res-{index:03d}@example.invalid",
        # Deliberately not a dialable number.
        "phone": f"TESTPHONE{index:04d}",
        "gender": "F" if index % 2 else "M",
        "city": "Testville",
        "state": "Teststate",
        "country": "Testland",
        "zip_code": f"T{index:05d}",
        "id_type": "TEST-ID",
        "id_number": code,
        "college_id": f"TEST-COL-{index:03d}",
        "student_college": f"Test Institute {index:03d}",
        "check_in_date": check_in,
        "occupancy_preference": (
            "double" if index % SHARED_PREFERENCE_EVERY == 0 else "single"
        ),
        "room": room,
        "notes": f"{TAG} {code} synthetic resident of {room.number}",
    }


RESIDENTS = tuple(resident_spec(index) for index in range(1, len(OCCUPIED_ROOMS) + 1))

assert len(RESIDENTS) == 30, "thirty synthetic residents"
assert len({resident["email"] for resident in RESIDENTS}) == 30, "e-mails are unique"
assert len({resident["check_in_date"] for resident in RESIDENTS}) >= 15, (
    "move-in dates must vary enough to exercise date sorting and filtering"
)


def resident_by_code(code: str) -> dict:
    for resident in RESIDENTS:
        if resident["code"] == code:
            return resident
    raise KeyError(code)


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------

def reference_month(today: date = None) -> date:
    """
    First day of the month the application treats as "current".

    Mirrors ``timezone.now().date().replace(day=1)`` in ``rental/views.py``
    exactly, so the seeded dataset always lines up with what the running
    application reports as the current month.
    """
    return (today or timezone.localdate()).replace(day=1)


def shift_month(month: date, offset: int) -> date:
    """Shift a first-of-month date by ``offset`` months, staying on day 1."""
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def seeded_months(reference: date = None) -> tuple:
    """Oldest-first list of every month the dataset creates records for."""
    reference = reference or reference_month()
    return tuple(
        shift_month(reference, -HISTORY_MONTH_COUNT + step)
        for step in range(HISTORY_MONTH_COUNT + 1)
    )


def days_in_month(month: date) -> int:
    if month.month == 12:
        return 31
    return (date(month.year, month.month + 1, 1) - date(month.year, month.month, 1)).days


def payment_dates_for(month: date, as_of: date = None) -> tuple:
    """
    Day-of-month values usable for collection records in ``month``.

    Historical months get the whole ladder. The reference month is clamped to
    ``as_of`` (default: today) because a rent register cannot record a payment
    that has not happened yet — a forward-dated collection would be a data
    integrity defect, not extra coverage.
    """
    as_of = as_of or timezone.localdate()
    days = PAYMENT_DATE_LADDER
    if month == as_of.replace(day=1):
        days = tuple(day for day in days if date(month.year, month.month, day) <= as_of)
    return tuple(day for day in days if day <= days_in_month(month))


def month_offset(month: date, reference: date = None) -> int:
    """0 for the reference month, -1 for the month before, and so on."""
    reference = reference or reference_month()
    return (month.year * 12 + month.month) - (reference.year * 12 + reference.month)


# ---------------------------------------------------------------------------
# Meter readings and bills
# ---------------------------------------------------------------------------

def room_units(room: RoomSpec, month: date) -> int:
    """Units consumed by ``room`` in ``month``."""
    offset = month_offset(month)
    if offset < -HISTORY_MONTH_COUNT or offset > 0:
        raise ValueError(f"{month} is outside the seeded range")
    return room.units[offset + HISTORY_MONTH_COUNT]


def room_meter_start(room: RoomSpec, month: date) -> int:
    """
    Meter reading at the start of ``month``.

    Readings chain month to month: each month's opening reading is the previous
    month's closing reading, so the meter never jumps and no month double-counts
    another's consumption. The chain starts at ``meter_base`` (default
    ``1000 + index * 13``) at the beginning of the oldest seeded month.
    """
    reading = room.meter_base if room.meter_base is not None else 1000 + ROOMS.index(room) * 13
    for earlier in seeded_months():
        if earlier >= month:
            break
        reading += room_units(room, earlier)
    return reading


#: Instalment counts per reference-month state.
_REFERENCE_INSTALLMENTS = {"paid": 1, "partial": 2, "overdue": 2, "pending": 0, "vacant": 0}

#: Fraction of the bill collected, per reference-month state.
_REFERENCE_RATIO = {
    "paid": Decimal("1.00"),
    "partial": Decimal("0.55"),
    "overdue": Decimal("0.30"),
    "pending": Decimal("0.00"),
    "vacant": Decimal("0.00"),
}


def reference_month_target(room: RoomSpec, total) -> Decimal:
    """Exact collection target for the reference month."""
    total = Decimal(str(total))
    if room.reference_paid is not None:
        return quantize_money(room.reference_paid)
    return quantize_money(total * _REFERENCE_RATIO[room.state])


def history_month_target(room: RoomSpec, month: date, total) -> Decimal:
    """Exact collection target for a historical month, from the ratio cycle."""
    total = Decimal(str(total))
    index = (ROOMS.index(room) * 3 + month.year * 12 + month.month) % len(COLLECTION_RATIOS)
    return quantize_money(total * Decimal(str(COLLECTION_RATIOS[index])))


def _seeded_scenario(room: RoomSpec):
    for scenario in PAYMENT_SCENARIOS:
        if scenario.room_number == room.number and not scenario.exercised_live:
            return scenario
    return None


def collection_plan(room: RoomSpec, month: date, total) -> list:
    """
    Return ``[(amount, day, method), ...]`` for one room-month.

    The reference month follows the room's declared state (and the explicit
    PAY-00x scenario where one applies); historical months follow the
    :data:`COLLECTION_RATIOS` cycle. A zero target never produces a record, and
    a fully settled room never carries a stale ``partial`` status.
    """
    total = Decimal(str(total))
    if total <= 0 or room.vacant:
        return []

    is_reference = month == reference_month()
    target = (
        reference_month_target(room, total)
        if is_reference
        else history_month_target(room, month, total)
    )
    target = min(quantize_money(target), total)
    if target <= 0:
        return []

    scenario = _seeded_scenario(room) if is_reference else None
    if scenario:
        return [
            (quantize_money(amount), day, method)
            for amount, day, method in scenario.instalments
        ]

    days = payment_dates_for(month) or (1,)
    instalments = (
        _REFERENCE_INSTALLMENTS[room.state]
        if is_reference
        else (1 if target >= total else 2)
    )
    if instalments == 0:
        return []

    instalments = min(instalments, len(days))
    base = quantize_money(target / instalments)
    amounts = [base] * instalments
    amounts[0] = quantize_money(amounts[0] + target - sum(amounts))

    plan = []
    for position, amount in enumerate(amounts):
        if amount <= 0:
            continue
        plan.append((
            amount,
            days[min(position, len(days) - 1)],
            PAYMENT_METHODS[(ROOMS.index(room) + position) % len(PAYMENT_METHODS)],
        ))
    return plan


def scenario_for_room(room_number: str) -> PaymentScenario:
    for scenario in PAYMENT_SCENARIOS:
        if scenario.room_number == room_number:
            return scenario
    raise KeyError(room_number)


# ---------------------------------------------------------------------------
# Maintenance expenses (a handful, so the reports page is never empty)
# ---------------------------------------------------------------------------

#: (building, category, amount, date, description, paid)
EXPENSES = (
    ("M1", "plumbing", "1850.00", date(2026, 10, 3), "M1 bathroom pipe repair", True),
    ("M1", "cleaning", "1200.00", date(2026, 9, 6), "M1 common-area cleaning", True),
    ("1", "electrical", "2400.00", date(2026, 10, 2), "Building 1 corridor lighting", True),
    ("2", "repairs", "3100.00", date(2026, 9, 19), "Building 2 door closer replacement", True),
    ("3", "painting", "4500.00", date(2026, 8, 22), "Building 3 stairwell repaint", True),
    ("4", "internet", "799.00", date(2026, 10, 1), "Building 4 broadband bill", True),
    ("5", "security", "2600.00", date(2026, 9, 27), "Building 5 CCTV service", False),
    ("3", "plumbing", "980.00", date(2026, 7, 15), "Building 3 water tank repair", True),
)


def expense_description(description: str) -> str:
    return f"{TAG} {description}"


# ---------------------------------------------------------------------------
# Import-time self-checks: the module must fail loudly if the dataset drifts.
# ---------------------------------------------------------------------------

def _validate() -> None:
    for scenario in ELECTRICITY_SCENARIOS:
        if scenario.exercised_live or scenario.current_reading is None:
            continue
        units = scenario.current_reading - scenario.previous_reading
        assert units == scenario.expected_units, f"{scenario.code} unit mismatch"
        assert units >= 0, f"{scenario.code} must not imply a negative reading"

    for scenario in PAYMENT_SCENARIOS:
        if not scenario.instalments:
            continue
        collected = sum(Decimal(amount) for amount, _day, _method in scenario.instalments)
        if scenario.code == "PAY-005":
            # Overpayment: the suite asserts the application's chosen rule.
            continue
        assert collected == Decimal(scenario.expected_paid), (
            f"{scenario.code} instalments sum to {collected}, "
            f"expected {scenario.expected_paid}"
        )
        assert collected <= Decimal(scenario.expected_bill), (
            f"{scenario.code} collects more than the bill it is paying against"
        )

    states = [room.state for room in OCCUPIED_ROOMS]
    assert states.count("paid") >= 12, "at least twelve paid rooms are required"
    assert states.count("partial") >= 7, "at least seven partial rooms are required"
    assert states.count("overdue") >= 5, "at least five overdue rooms are required"
    assert states.count("pending") + states.count("overdue") >= 6, (
        "at least six rooms must have collected nothing"
    )


_validate()



def room_electricity(room: RoomSpec, month: date, rate) -> Decimal:
    """Electricity charge for one room-month at the configured rate."""
    return quantize_money(Decimal(room_units(room, month)) * Decimal(str(rate)))


def room_total_bill(room: RoomSpec, month: date, rate) -> Decimal:
    """The existing business rule: agreed rent + metered electricity."""
    return quantize_money(Decimal(room.rent) + room_electricity(room, month, rate))

