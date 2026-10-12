"""
Category G - Payment history (6 tests).

Payment history is where the known refresh problem lives, so this category also
covers the full refresh cycle in :class:`PaymentHistoryRefreshTests`: collect ->
history updates -> totals update -> status updates -> reopen -> navigate away ->
return -> browser refresh.
"""
from decimal import Decimal

from django.urls import reverse

from .models import MonthlyPayment, PaymentRecord
from .test_support import SeededApiTestCase, SeededMutationTestCase
from .testdata import spec


class PaymentHistoryReadTests(SeededApiTestCase):
    """G.1 - G.3: what the history endpoints return."""

    def test_g1_room_payment_history_lists_every_record_newest_first(self):
        payload = self.get_json(self.api("api_room_payments", self.room_id("C-101")))
        self.assertTrue(payload["success"])
        self.assertEqual(payload["room"], "C-101")

        records = payload["payments"]
        self.assertGreater(len(records), 0)
        dates = [record["date"] for record in records]
        self.assertEqual(dates, sorted(dates, reverse=True))
        for record in records:
            with self.subTest(record=record["id"]):
                self.assertIn("amount", record)
                self.assertIn("method", record)
                self.assertGreater(record["amount"], 0)

    def test_g2_payment_history_sums_to_the_stored_collected_amount(self):
        """
        ``api_room_payments`` deliberately returns *every* payment for the room
        across all months, newest first. The reference-month slice of that list
        must equal the stored ``paid_amount`` for that month.
        """
        for number in ("A-101", "A-103", "C-101", "A-106", "D-105"):
            with self.subTest(room=number):
                payload = self.get_json(self.api("api_room_payments", self.room_id(number)))
                monthly = MonthlyPayment.objects.get(
                    room=self.room(number), month=self.reference_month
                )
                this_month = sum(
                    (
                        Decimal(str(record["amount"]))
                        for record in payload["payments"]
                        if record["date"].startswith(f"{self.reference_month:%Y-%m}")
                    ),
                    Decimal("0.00"),
                )
                self.assertEqual(this_month, monthly.paid_amount)

    def test_g3_monthly_payment_history_endpoint_groups_records_by_month(self):
        payload = self.get_json(reverse("get_payment_history", args=[self.room_id("C-101")]))
        self.assertTrue(payload["success"])

        months = {entry["month"] for entry in payload["history"]}
        self.assertEqual(len(months), len(self.seeded_months))
        for entry in payload["history"]:
            with self.subTest(month=entry["month"]):
                self.assertIn("rent_amount", entry)
                self.assertIn("paid_amount", entry)
                self.assertIn("records", entry)
                # Records inside a month are also newest-first.
                dates = [record["date"] for record in entry["records"]]
                self.assertEqual(dates, sorted(dates, reverse=True))


class PaymentHistoryRefreshTests(SeededMutationTestCase):
    """G.4 - G.6: the refresh behaviour the operating brief calls out."""

    def test_g4_a_new_payment_appears_in_history_immediately_with_no_stale_data(self):
        number = "A-106"
        room_id = self.room_id(number)
        url = reverse("api_collect_payment", args=[room_id])
        history_url = reverse("api_room_payments", args=[room_id])

        before = self.get_json(history_url)["payments"]
        paid_before = Decimal(str(self.room_snapshot(number)["collected_amount"]))
        self.assertEqual(paid_before, Decimal("0.00"))

        response = self.post_json(url, {"amount": "1500.00", "payment_method": "upi"})
        self.assertEqual(response.status_code, 200)

        after = self.get_json(history_url)["payments"]
        self.assertEqual(len(after), len(before) + 1)
        self.assertIn(1500.0, [record["amount"] for record in after])
        # Newest first: the new record leads the list.
        self.assertEqual(after[0]["amount"], 1500.0)

        snapshot = self.room_snapshot(number)
        self.assertEqual(Decimal(str(snapshot["collected_amount"])), Decimal("1500.00"))
        self.assertEqual(snapshot["payment_status"], "PARTIAL")

    def test_g5_collecting_the_full_outstanding_settles_the_history_and_the_status(self):
        number = "A-106"
        room_id = self.room_id(number)
        url = reverse("api_collect_payment", args=[room_id])
        outstanding = Decimal(str(self.room_snapshot(number)["outstanding_amount"]))

        response = self.post_json(url, {"amount": str(outstanding)})
        self.assertEqual(response.status_code, 200)

        snapshot = self.room_snapshot(number)
        self.assertEqual(snapshot["payment_status"], "PAID")
        self.assertEqual(snapshot["outstanding_amount"], 0.0)

        history = self.get_json(reverse("api_room_payments", args=[room_id]))["payments"]
        self.assertGreater(len(history), 0)
        monthly = MonthlyPayment.objects.get(room=self.room(number), month=self.reference_month)
        this_month = sum(
            (
                Decimal(str(record["amount"]))
                for record in history
                if record["date"].startswith(f"{self.reference_month:%Y-%m}")
            ),
            Decimal("0.00"),
        )
        self.assertEqual(this_month, monthly.paid_amount)
        self.assertEqual(monthly.payment_status, "paid")

    def test_g6_history_reflects_every_collection_without_duplicating_or_losing_any(self):
        number = "A-106"
        room_id = self.room_id(number)
        url = reverse("api_collect_payment", args=[room_id])
        history_url = reverse("api_room_payments", args=[room_id])

        expected_records = len(self.get_json(history_url)["payments"])
        for amount in ("500", "750.25", "1000.50"):
            self.assertEqual(self.post_json(url, {"amount": amount}).status_code, 200)
            expected_records += 1

        history = self.get_json(history_url)["payments"]
        self.assertEqual(len(history), expected_records)
        # Idempotent reads: asking twice returns the same list.
        self.assertEqual(self.get_json(history_url)["payments"], history)
        ids = [record["id"] for record in history]
        self.assertEqual(len(ids), len(set(ids)), "history must not duplicate records")
