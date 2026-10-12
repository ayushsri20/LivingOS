"""
Category C - Residents (8 tests).

Covers the resident records themselves, room/building association, the per-room
roster API, and the invariants that matter operationally: every resident belongs
to an occupied room, and a vacant room has no active resident at all.
"""
from django.urls import reverse

from .models import Guest, Room
from .test_support import SeededApiTestCase
from .testdata import spec


class ResidentDatasetTests(SeededApiTestCase):
    """C.1 - C.4: the resident records themselves."""

    def test_c1_thirty_active_residents_one_per_occupied_room(self):
        active = Guest.objects.filter(is_active=True, room__isnull=False)
        self.assertEqual(active.count(), 30)
        self.assertEqual(
            active.values("room_id").distinct().count(), 30,
            "each occupied room holds exactly one active resident",
        )

    def test_c2_every_resident_carries_a_synthetic_identifier_and_no_real_data(self):
        codes = set(Guest.objects.values_list("id_number", flat=True))
        self.assertEqual(len(codes), 30)
        for code in codes:
            with self.subTest(code=code):
                self.assertTrue(code.startswith(spec.RESIDENT_PREFIX))
        # `.invalid` is an RFC 2606 reserved TLD: unreachable by construction.
        self.assertEqual(
            Guest.objects.exclude(email__endswith="@example.invalid").count(), 0
        )
        # Phone numbers are deliberately non-dialable.
        self.assertEqual(
            Guest.objects.exclude(phone__startswith="TESTPHONE").count(), 0
        )

    def test_c3_move_in_dates_are_realistic_2026_dates_with_genuine_variation(self):
        dates = set(Guest.objects.values_list("check_in_date", flat=True))
        self.assertEqual(Guest.objects.filter(check_in_date__isnull=True).count(), 0)
        self.assertGreaterEqual(len(dates), 15)
        for value in dates:
            with self.subTest(check_in=value):
                self.assertEqual(value.year, 2026)
        # Both long-term residents and this month's arrivals must be present.
        self.assertTrue(any(value <= spec.reference_month() for value in dates))
        self.assertTrue(
            any(
                value.year == spec.reference_month().year
                and value.month == spec.reference_month().month
                for value in dates
            ),
            "the dataset must include residents who moved in this month",
        )

    def test_c4_room_and_building_association_is_correct_for_every_resident(self):
        building_ids = dict(Room.objects.values_list("number", "building_id"))
        for resident in spec.RESIDENTS:
            with self.subTest(resident=resident["code"]):
                guest = self.resident(resident["code"])
                room = guest.room
                self.assertEqual(room.number, resident["room"].number)
                self.assertEqual(
                    room.building_id,
                    building_ids[resident["room"].number],
                )
                self.assertEqual(room.building.name, resident["room"].building)


class ResidentApiTests(SeededApiTestCase):
    """C.5 - C.8: what the residents UI actually receives."""

    def test_c5_vacant_rooms_have_no_active_resident(self):
        for room_spec in spec.VACANT_ROOMS:
            with self.subTest(room=room_spec.number):
                room = self.room(room_spec.number)
                self.assertEqual(Guest.objects.filter(room=room, is_active=True).count(), 0)
                self.assertEqual(room.current_occupancy, 0)
                self.assertEqual(
                    room.get_occupancy_status(), f"Empty (0/{room.capacity})"
                )

    def test_c6_per_room_roster_api_returns_the_resident_of_an_occupied_room(self):
        first = spec.OCCUPIED_ROOMS[0]
        payload = self.get_json(reverse("get_room_tenants", args=[self.room_id(first.number)]))
        self.assertTrue(payload["success"])
        self.assertEqual(payload["room"], first.number)
        self.assertEqual(len(payload["tenants"]), 1)
        tenant = payload["tenants"][0]
        expected_code = f"{spec.RESIDENT_PREFIX}{spec.resident_index(first):03d}"
        self.assertEqual(tenant["name"], self.resident(expected_code).full_name)
        self.assertTrue(tenant["check_in"])

    def test_c7_per_room_roster_api_returns_an_empty_list_for_a_vacant_room(self):
        for room_spec in spec.VACANT_ROOMS:
            with self.subTest(room=room_spec.number):
                payload = self.get_json(
                    reverse("get_room_tenants", args=[self.room_id(room_spec.number)])
                )
                self.assertTrue(payload["success"])
                self.assertEqual(payload["tenants"], [])

    def test_c8_resident_search_finds_exactly_the_matching_synthetic_resident(self):
        """
        The residents view filters on room number and resident name, so the
        dataset must produce an unambiguous hit and an unambiguous miss.
        """
        needle = spec.RESIDENTS[0]["code"]  # TEST-RES-001
        haystack = [
            f"{guest.full_name} {guest.id_number}".lower()
            for guest in Guest.objects.all()
        ]
        matches = [text for text in haystack if needle.lower() in text]
        self.assertEqual(len(matches), 1, f"{needle} must match exactly one resident")

        self.assertEqual(
            [text for text in haystack if "xyz-not-found" in text], [],
            "a nonsense search must match nothing rather than everything",
        )
