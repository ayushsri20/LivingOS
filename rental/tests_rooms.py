"""
Category B - Rooms (8 tests).

The room list is the application's front door: every financial figure on every
page is derived from the per-room snapshot in ``/api/rooms/``. These tests prove
the list loads, each room's detail loads, and each occupancy/payment state is
represented and reported correctly.
"""
from decimal import Decimal

from django.urls import reverse

from .models import Guest, MonthlyPayment, Room
from .test_support import SeededApiTestCase
from .testdata import spec


class RoomListApiTests(SeededApiTestCase):
    """B.1 - B.4: the room list and room detail."""

    def test_b1_room_list_loads_with_all_thirty_six_rooms_and_six_buildings(self):
        payload = self.get_json(reverse("api_rooms"))
        self.assertTrue(payload["success"])
        self.assertEqual(payload["count"], 36)
        self.assertEqual(len(payload["rooms"]), 36)
        self.assertEqual(len(payload["buildings"]), 6)
        self.assertEqual(
            [building["name"] for building in payload["buildings"]],
            list(spec.BUILDING_NAMES),
            "buildings must be returned in the application's canonical order",
        )

    def test_b2_room_list_is_grouped_into_six_rooms_per_building(self):
        payload = self.get_json(reverse("api_rooms"))
        for building in payload["buildings"]:
            with self.subTest(building=building["name"]):
                self.assertEqual(len(building["rooms"]), 6)

    def test_b3_room_detail_loads_for_every_room(self):
        for number in spec.ROOMS_BY_NUMBER:
            with self.subTest(room=number):
                snapshot = self.room_snapshot(number)
                self.assertEqual(snapshot["room"], number)
                self.assertEqual(snapshot["id"], self.room_id(number))
                self.assertEqual(snapshot["building"], self.room_spec(number).building)

    def test_b4_room_detail_agrees_with_room_list_for_every_room(self):
        """The two endpoints must never disagree about the same room."""
        listed = self.snapshots()
        for number, from_list in listed.items():
            with self.subTest(room=number):
                self.assertEqual(self.room_snapshot(number), from_list)


class RoomStateTests(SeededApiTestCase):
    """B.5 - B.8: occupancy and payment states as the UI sees them."""

    def test_b5_occupied_state_names_the_resident_and_vacant_state_does_not(self):
        snapshots = self.snapshots()
        occupied = [r for r in spec.OCCUPIED_ROOMS]
        vacant = [r for r in spec.VACANT_ROOMS]

        self.assertEqual(len(occupied), 30)
        self.assertEqual(len(vacant), 6)

        for room_spec in occupied:
            with self.subTest(room=room_spec.number):
                snapshot = snapshots[room_spec.number]
                self.assertNotEqual(snapshot["resident"], "No resident")
                self.assertEqual(snapshot["resident"], Guest.objects.get(
                    room=self.rooms[room_spec.number], is_active=True
                ).full_name)

        for room_spec in vacant:
            with self.subTest(room=room_spec.number):
                snapshot = snapshots[room_spec.number]
                self.assertEqual(
                    snapshot["resident"], "No resident",
                    "a vacant room must report no resident so the UI shows VACANT",
                )

    def test_b6_all_four_payment_states_plus_vacant_are_representable(self):
        statuses = {snapshot["payment_status"] for snapshot in self.snapshots().values()}
        self.assertTrue(
            {"PAID", "PARTIAL", "DUE"}.issubset(statuses),
            f"the dataset must exercise PAID, PARTIAL and DUE; got {statuses}",
        )
        stored = set(
            MonthlyPayment.objects.filter(month=self.reference_month)
            .values_list("payment_status", flat=True)
        )
        self.assertIn("overdue", stored)
        self.assertIn("paid", stored)
        self.assertIn("partial", stored)
        self.assertIn("pending", stored)

    def test_b7_paid_partial_and_due_statuses_match_the_collected_amounts(self):
        """
        The API derives its status from money, not from a stored label. This is
        the rule the frontend's status badges depend on.
        """
        for snapshot in self.snapshots().values():
            if snapshot["resident"] == "No resident":
                continue
            with self.subTest(room=snapshot["room"]):
                collected = Decimal(str(snapshot["collected_amount"]))
                total = Decimal(str(snapshot["total_bill"]))
                if collected == 0:
                    expected = "DUE"
                elif collected >= total:
                    expected = "PAID"
                else:
                    expected = "PARTIAL"
                self.assertEqual(snapshot["payment_status"], expected)

    def test_b8_outstanding_is_never_negative_and_bills_vary_room_to_room(self):
        snapshots = self.snapshots()
        totals = {snapshot["total_bill"] for snapshot in snapshots.values()}
        # A universal bill total would hide rent/electricity calculation errors.
        self.assertGreaterEqual(len(totals), 10)
        for snapshot in snapshots.values():
            with self.subTest(room=snapshot["room"]):
                self.assertGreaterEqual(snapshot["outstanding_amount"], 0)
                self.assertEqual(
                    snapshot["outstanding_amount"],
                    round(
                        max(0.0, snapshot["total_bill"] - snapshot["collected_amount"]), 2
                    ),
                )
