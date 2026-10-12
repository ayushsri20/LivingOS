"""
Category H - Dashboard (6 tests).

``/api/dashboard/metrics/`` feeds the KPI cards. These tests verify the figures
are correct *and* that they reconcile with the per-room snapshots they are built
from — a dashboard that disagrees with the rooms it summarises is worse than one
that shows nothing.
"""
from decimal import Decimal

from django.urls import reverse

from .models import Guest
from .test_support import SeededApiTestCase, SeededMutationTestCase


class DashboardMetricsTests(SeededApiTestCase):
    """H.1 - H.4: the headline figures."""

    def test_h1_total_and_occupied_room_counts_match_the_database(self):
        payload = self.get_json(reverse("dashboard_metrics_api"))
        self.assertTrue(payload["success"])
        meta = payload["meta"]
        self.assertEqual(meta["total_rooms"], 36)
        self.assertEqual(
            meta["occupied_rooms"],
            Guest.objects.filter(room__isnull=False, is_active=True)
            .values("room_id").distinct().count(),
        )
        self.assertEqual(meta["occupied_rooms"], 30)

    def test_h2_vacant_count_is_total_minus_occupied(self):
        meta = self.get_json(reverse("dashboard_metrics_api"))["meta"]
        self.assertEqual(meta["total_rooms"] - meta["occupied_rooms"], 6)

    def test_h3_expected_yield_equals_the_sum_of_every_rooms_current_bill(self):
        metrics = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        snapshots = self.snapshots()
        expected = sum(
            (Decimal(str(snapshot["total_bill"])) for snapshot in snapshots.values()),
            Decimal("0.00"),
        )
        self.assertEqual(Decimal(str(metrics["expected_yield"])), expected)

    def test_h4_collection_and_receivable_reconcile_with_the_room_snapshots(self):
        metrics = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        snapshots = self.snapshots()
        collected = sum(
            (Decimal(str(s["collected_amount"])) for s in snapshots.values()),
            Decimal("0.00"),
        )
        outstanding = sum(
            (Decimal(str(s["outstanding_amount"])) for s in snapshots.values()),
            Decimal("0.00"),
        )
        self.assertEqual(Decimal(str(metrics["realized_revenue"])), collected)
        self.assertEqual(Decimal(str(metrics["accounts_receivable"])), outstanding)
        self.assertGreater(metrics["realized_revenue"], 0)
        self.assertGreaterEqual(metrics["accounts_receivable"], 0)


class DashboardDerivedTests(SeededMutationTestCase):
    """H.5 - H.6: derived rates and reaction to a collection."""

    def test_h5_occupancy_and_collection_efficiency_are_consistent_percentages(self):
        payload = self.get_json(reverse("dashboard_metrics_api"))
        metrics = payload["metrics"]
        meta = payload["meta"]

        occupancy = metrics["occupancy_rate"]
        self.assertAlmostEqual(
            occupancy, meta["occupied_rooms"] / meta["total_rooms"] * 100, places=4
        )
        efficiency = metrics["collection_efficiency"]
        self.assertAlmostEqual(
            efficiency,
            metrics["realized_revenue"] / metrics["expected_yield"] * 100,
            places=4,
        )
        self.assertGreaterEqual(occupancy, 0)
        self.assertLessEqual(occupancy, 100)
        self.assertGreaterEqual(efficiency, 0)

    def test_h6_collecting_a_payment_moves_the_dashboard_immediately(self):
        before = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        number = "A-106"
        room_id = self.room_id(number)
        amount = "1000.00"

        response = self.post_json(reverse("api_collect_payment", args=[room_id]), {"amount": amount})
        self.assertEqual(response.status_code, 200)

        after = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        self.assertEqual(
            Decimal(str(after["realized_revenue"])),
            Decimal(str(before["realized_revenue"])) + Decimal(amount),
        )
        self.assertLess(
            Decimal(str(after["accounts_receivable"])),
            Decimal(str(before["accounts_receivable"])),
        )
        self.assertGreater(after["collection_efficiency"], before["collection_efficiency"])
        # Expected yield is unchanged: collecting does not change what is owed.
        self.assertEqual(after["expected_yield"], before["expected_yield"])
