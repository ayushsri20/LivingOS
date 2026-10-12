"""
Shared base classes for the Rental OS test suite.

Every test in this package runs against the isolated ``hotel_project.settings_test``
database and asserts against the deterministic synthetic dataset in
:mod:`rental.testdata`.

Two base classes are provided:

``SeededApiTestCase``
    Seeds the full dataset once per class (via ``setUpTestData``, so the cost is
    paid once rather than per test) and exposes an authenticated admin client.

``SeededMutationTestCase``
    Same, but each test gets a fresh copy because these tests write. Use it for
    payment collection, bill generation and anything else that mutates.

Assertions always compare against values derived from :mod:`rental.testdata.spec`
or computed by Django itself — never against a figure copied out of the database,
which would let a seeding bug validate itself.
"""

import json
from decimal import Decimal

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Guest, Room
from .testdata import builder, spec

# The suite drives the API exactly as the React client does, so the login-only
# middleware is bypassed here in the same way rental/tests.py already does.
# Authentication itself is covered explicitly by the error/recovery tests.
TEST_MIDDLEWARE = [
    middleware
    for middleware in settings.MIDDLEWARE
    if "LoginRequiredMiddleware" not in middleware
]


class SeededTestMixin:
    """Seeds the dataset once per class and exposes lookup helpers."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rate = Decimal(str(settings.ELECTRICITY_RATE_PER_UNIT))
        cls.reference_month = spec.reference_month()
        cls.seeded_months = spec.seeded_months()
        cls.history_months = tuple(m for m in cls.seeded_months if m != cls.reference_month)
        cls.admin = builder.ensure_test_admin()[0]
        cls.report = builder.seed_dataset(reset=True)
        cls.rooms = {room.number: room for room in Room.objects.select_related("building")}

    # -- lookups -----------------------------------------------------------

    def room(self, number: str) -> Room:
        return self.rooms[number]

    def room_id(self, number: str) -> int:
        return self.rooms[number].id

    def room_spec(self, number: str):
        return spec.ROOMS_BY_NUMBER[number]

    def resident(self, code: str) -> Guest:
        return Guest.objects.get(id_number=code)

    def scenario(self, code: str):
        for item in spec.PAYMENT_SCENARIOS:
            if item.code == code:
                return item
        raise KeyError(code)

    def electricity_scenario(self, code: str):
        for item in spec.ELECTRICITY_SCENARIOS:
            if item.code == code:
                return item
        raise KeyError(code)

    # -- expected figures --------------------------------------------------

    def expected_total(self, number: str, month=None) -> Decimal:
        """agreed rent + metered electricity, derived from the spec."""
        return spec.room_total_bill(self.room_spec(number), month or self.reference_month, self.rate)

    def expected_electricity(self, number: str, month=None) -> Decimal:
        return spec.room_electricity(self.room_spec(number), month or self.reference_month, self.rate)

    def expected_paid(self, number: str, month=None) -> Decimal:
        month = month or self.reference_month
        room_spec = self.room_spec(number)
        total = spec.room_total_bill(room_spec, month, self.rate)
        plan = spec.collection_plan(room_spec, month, total)
        return sum((amount for amount, _day, _method in plan), Decimal("0.00"))

    def expected_outstanding(self, number: str, month=None) -> Decimal:
        month = month or self.reference_month
        total = self.expected_total(number, month)
        return max(Decimal("0.00"), total - self.expected_paid(number, month))

    # -- API helpers -------------------------------------------------------

    def api(self, name: str, *args) -> str:
        return reverse(name, args=args)

    def get_json(self, url: str):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()

    def post_json(self, url: str, payload=None):
        return self.client.post(
            url,
            data=json.dumps({} if payload is None else payload),
            content_type="application/json",
        )

    def room_snapshot(self, number: str) -> dict:
        """The authoritative room-first snapshot the React drawer consumes."""
        payload = self.get_json(self.api("api_room_detail", self.room_id(number)))
        self.assertTrue(payload["success"])
        return payload["room"]

    def snapshots(self) -> dict:
        """Every room snapshot keyed by room number."""
        payload = self.get_json(reverse("api_rooms"))
        self.assertTrue(payload["success"])
        return {room["room"]: room for room in payload["rooms"]}


@override_settings(
    MIDDLEWARE=TEST_MIDDLEWARE,
    ENVIRONMENT="test",
    ELECTRICITY_RATE_PER_UNIT="13.00",
)
class SeededApiTestCase(SeededTestMixin, TestCase):
    """Read-mostly tests: the dataset is seeded once per class."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)


@override_settings(
    MIDDLEWARE=TEST_MIDDLEWARE,
    ENVIRONMENT="test",
    ELECTRICITY_RATE_PER_UNIT="13.00",
)
class SeededMutationTestCase(SeededTestMixin, TestCase):
    """
    Tests that mutate financial data.

    ``TestCase`` wraps every test method in a transaction and rolls it back, so
    a collected payment made in one test cannot leak into the next, while
    ``setUpTestData`` still seeds the dataset only once per class. That is both
    correct and far cheaper than re-seeding for every method.
    """

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

