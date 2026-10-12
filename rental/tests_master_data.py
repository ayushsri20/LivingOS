"""
Category A - Master data (8 tests).

The authoritative property structure is the one thing in this system that must
never drift: 6 buildings, 36 rooms, 6 rooms per building, correct prefix-to-
building mapping, no duplicates, no unexpected ids. These tests are the tripwire
for the whole application.
"""
from decimal import Decimal

from .models import Building, ElectricityBill, Guest, MonthlyPayment, Room
from .test_support import SeededApiTestCase
from .testdata import spec


class MasterDataStructureTests(SeededApiTestCase):
    """A.1 - A.5: the authoritative inventory itself."""

    def test_a1_exactly_six_buildings_with_the_authoritative_names(self):
        self.assertEqual(Building.objects.count(), 6)
        self.assertEqual(
            sorted(Building.objects.values_list("name", flat=True)),
            sorted(spec.BUILDING_NAMES),
        )

    def test_a2_exactly_six_rooms_in_every_building(self):
        for name in spec.BUILDING_NAMES:
            with self.subTest(building=name):
                self.assertEqual(
                    Room.objects.filter(building__name=name).count(), 6
                )

    def test_a3_exactly_thirty_six_rooms_in_total(self):
        self.assertEqual(Room.objects.count(), 36)

    def test_a4_no_duplicate_room_numbers(self):
        numbers = list(Room.objects.values_list("number", flat=True))
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_a5_room_numbers_and_building_relationships_match_the_specification(self):
        expected = {
            room_spec.number: room_spec.building for room_spec in spec.ROOMS
        }
        actual = {
            room.number: room.building.name
            for room in Room.objects.select_related("building")
        }
        self.assertEqual(actual, expected)
        for number, building in actual.items():
            with self.subTest(room=number):
                prefix = number.split("-", 1)[0]
                self.assertEqual(spec.PREFIX_TO_BUILDING[prefix], building)


class MasterDataIdAndSeedTests(SeededApiTestCase):
    """A.6 - A.8: ids, flags and the shape of what the seeder produced."""

    def test_a6_no_unexpected_room_ids_and_the_inventory_is_one_per_room(self):
        ids = list(Room.objects.order_by("id").values_list("id", flat=True))
        self.assertEqual(len(ids), 36)
        self.assertEqual(len(set(ids)), 36)
        # The migration seeds ids 1..36 and the seeder must never renumber.
        self.assertEqual(ids, list(range(1, 37)))

    def test_a7_every_room_carries_a_building_and_a_capacity_within_the_model_limit(self):
        for room in Room.objects.all():
            with self.subTest(room=room.number):
                self.assertIsNotNone(room.building_id)
                self.assertLessEqual(room.capacity, Room.MAX_CAPACITY)
                self.assertGreaterEqual(room.capacity, 1)
                self.assertIn(room.room_type, dict(Room.ROOM_TYPES))

    def test_a8_agreed_rents_are_realistic_varied_and_inside_the_agreed_band(self):
        rents = [room.agreed_rent for room in Room.objects.all()]
        self.assertTrue(all(rent is not None for rent in rents))
        for rent in rents:
            with self.subTest(rent=rent):
                self.assertGreaterEqual(rent, Decimal("5500"))
                self.assertLessEqual(rent, Decimal("8000"))
        # The application must never be able to assume one universal rent.
        self.assertGreaterEqual(len(set(rents)), 10)

    def test_a9_every_synthetic_row_is_identifiable_so_a_reset_can_find_it(self):
        """
        Reset correctness depends on tagging: an untagged synthetic row would
        survive ``--reset`` and quietly break determinism on the next run.
        """
        self.assertEqual(
            Guest.objects.filter(id_number__startswith=spec.RESIDENT_PREFIX).count(), 30
        )
        # No resident row outside the marker: the seeder never writes
        # real-looking data, and nothing pre-existing was overwritten.
        self.assertEqual(
            Guest.objects.exclude(id_number__startswith=spec.RESIDENT_PREFIX).count(), 0
        )
        # Every financial row the seeder owns is tagged.
        self.assertEqual(
            MonthlyPayment.objects.exclude(notes__startswith=spec.TAG).count(), 0
        )
        self.assertEqual(
            ElectricityBill.objects.exclude(notes__startswith=spec.TAG).count(), 0
        )
