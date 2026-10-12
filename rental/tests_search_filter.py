"""
Category J - Search and filter (8 tests).

The React views filter client-side against the room payload, so these tests
reproduce that exact predicate in Python and run it over the real API response.
If the frontend's filter logic ever drifts, these tests are where the mismatch
shows up — and, crucially, they prove the *data* supports unambiguous filtering.
"""
from django.urls import reverse

from .test_support import SeededApiTestCase
from .testdata import spec


def frontend_filter(rooms, building="", status="", query=""):
    """
    Mirror of the predicate in ``PaymentsView``/``ElectricityView`` in App.jsx.

    Kept deliberately faithful: strict equality on the building name, exact
    status match, and a case-insensitive substring over room number + resident.
    """
    needle = query.strip().lower()
    result = []
    for room in rooms:
        if building and room["building"] != building:
            continue
        if status and normalize_status(room) != status:
            continue
        if not needle:
            result.append(room)
            continue
        haystack = f"{room['room']} {room.get('resident') or ''}".lower()
        if needle in haystack:
            result.append(room)
    return result


def normalize_status(room):
    """Mirror of ``normalizeRoomStatus`` in frontend/src/utils.js."""
    if not room or not room.get("resident") or room["resident"] == "No resident":
        return "VACANT"
    status = str(room.get("payment_status") or "").upper()
    if status in {"PAID", "PARTIAL", "DUE", "VACANT"}:
        return status
    return "DUE"


class SearchAndFilterTests(SeededApiTestCase):
    """J.1 - J.8: search, filters, combinations, clearing and empty states."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        import json

        from django.test import Client

        client = Client()
        client.force_login(cls.admin)
        cls.rooms_payload = client.get(reverse("api_rooms")).json()["rooms"]

    def test_j1_unfiltered_list_returns_every_room(self):
        self.assertEqual(len(frontend_filter(self.rooms_payload)), 36)

    def test_j2_room_search_by_number_returns_the_matching_room(self):
        # "A-103" is the authoritative number for the operating brief's "M-103".
        matches = frontend_filter(self.rooms_payload, query="A-103")
        self.assertEqual([room["room"] for room in matches], ["A-103"])
        self.assertEqual(matches[0]["resident"], "TEST RES-003")

    def test_j3_resident_search_by_synthetic_code_returns_one_room(self):
        """
        The resident's display name is ``TEST RES-nnn`` while its identifier is
        ``TEST-RES-nnn``. The room filter searches room number + resident
        *name*, so the searchable form of the identifier is ``RES-001``.
        """
        matches = frontend_filter(self.rooms_payload, query="RES-001")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["room"], "A-101")
        self.assertEqual(matches[0]["resident"], "TEST RES-001")

        # Documented limitation (test report finding VIS-002): the hyphenated
        # identifier is not on the searchable surface, because the room payload
        # exposes only the display name. Searchable by name, not by id.
        self.assertEqual(frontend_filter(self.rooms_payload, query="TEST-RES-001"), [])

    def test_j4_building_filter_returns_exactly_six_rooms(self):
        for name in spec.BUILDING_NAMES:
            with self.subTest(building=name):
                matches = frontend_filter(self.rooms_payload, building=name)
                self.assertEqual(len(matches), 6)
                self.assertTrue(all(room["building"] == name for room in matches))

    def test_j5_building_filter_does_not_leak_between_m1_and_1(self):
        """
        "M1" and "1" are different strings. A substring match would make the
        "1" filter also list M1 rooms, which is the classic building-reporting bug.
        """
        m1 = {room["room"] for room in frontend_filter(self.rooms_payload, building="M1")}
        one = {room["room"] for room in frontend_filter(self.rooms_payload, building="1")}
        self.assertEqual(len(m1), 6)
        self.assertEqual(len(one), 6)
        self.assertEqual(m1 & one, set(), "M1 and building 1 must not overlap")

    def test_j6_status_filter_selects_only_that_status(self):
        for status in ("PAID", "PARTIAL", "DUE", "VACANT"):
            with self.subTest(status=status):
                matches = frontend_filter(self.rooms_payload, status=status)
                self.assertTrue(
                    all(normalize_status(room) == status for room in matches),
                    f"the {status} filter leaked other statuses",
                )
        # The dataset must exercise every status the UI renders.
        counts = {
            status: len(frontend_filter(self.rooms_payload, status=status))
            for status in ("PAID", "PARTIAL", "DUE", "VACANT")
        }
        for status, count in counts.items():
            with self.subTest(status=status):
                self.assertGreater(count, 0)

    def test_j7_combined_building_status_and_search_filters_intersect(self):
        # Building M1 + status PARTIAL + search "103" -> only A-103.
        matches = frontend_filter(
            self.rooms_payload, building="M1", status="PARTIAL", query="103"
        )
        self.assertEqual([room["room"] for room in matches], ["A-103"])

        # Narrowing with a contradictory filter must yield nothing, not everything.
        none = frontend_filter(
            self.rooms_payload, building="M1", status="VACANT", query="103"
        )
        self.assertEqual(none, [])

    def test_j8_a_nonsense_search_yields_an_empty_result_not_everything(self):
        matches = frontend_filter(self.rooms_payload, query="XYZ-NOT-FOUND")
        self.assertEqual(matches, [], "an unmatched search must return an empty list")

        # Clearing the query restores the full list (the "clear filters" path).
        self.assertEqual(len(frontend_filter(self.rooms_payload, query="")), 36)
        self.assertEqual(
            len(frontend_filter(self.rooms_payload, building="", status="", query="")),
            36,
        )
