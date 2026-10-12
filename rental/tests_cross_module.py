"""
Category M - Cross-module (6 tests).

The end-to-end journey the operating brief specifies:

    Room -> electricity reading -> bill -> payment -> payment history
         -> room status -> building totals -> dashboard -> analytics

A room whose payment lands correctly but shows a stale figure on the payments
page is a failure, even though every individual endpoint is "correct". These
tests walk a room through the whole chain and require every surface to agree,
with no contradictions and no stale data.
"""
from decimal import Decimal

from django.urls import reverse

from .models import ElectricityBill, MonthlyPayment
from .test_support import SeededMutationTestCase
from .testdata import spec


def money(value) -> Decimal:
    """Two-decimal money for comparison, so float noise never fails a test."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


class CrossModuleJourneyTests(SeededMutationTestCase):
    """M.1: the brief's worked example, followed through every surface."""

    def test_m1_room_m103_travels_from_reading_to_analytics_without_contradiction(self):
        """
        The brief's worked example, on the authoritative room for "M-103"
        (building M1, room 103 = ``A-103``):

            rent 6500 + electricity 65 units x 13 = 845  -> total 7345
            collected 4000 -> outstanding 3345 -> PARTIAL
        """
        number = "A-103"
        room_id = self.room_id(number)

        # Step 1: the electricity reading is metered correctly.
        bill = ElectricityBill.objects.get(room_id=room_id, month=self.reference_month)
        self.assertEqual(bill.units_consumed, Decimal(65))
        self.assertEqual(bill.bill_amount, Decimal("845.00"))
        self.assertEqual(bill.rate_per_unit, self.rate)

        # Step 2: the bill is rent + electricity.
        monthly = MonthlyPayment.objects.get(room_id=room_id, month=self.reference_month)
        self.assertEqual(monthly.rent_amount, Decimal("6500"))
        self.assertEqual(monthly.get_total_amount_due(), Decimal("7345.00"))

        # Step 3: the payment.
        self.assertEqual(monthly.paid_amount, Decimal("4000.00"))
        self.assertEqual(monthly.payment_status, "partial")

        # Step 4: payment history contains it.
        history = self.get_json(reverse("api_room_payments", args=[room_id]))["payments"]
        this_month = [
            record for record in history
            if record["date"].startswith(f"{self.reference_month:%Y-%m}")
        ]
        self.assertEqual(len(this_month), 1)
        self.assertEqual(this_month[0]["amount"], 4000.0)

        # Step 5: room status.
        snapshot = self.room_snapshot(number)
        self.assertEqual(snapshot["total_bill"], 7345.0)
        self.assertEqual(snapshot["collected_amount"], 4000.0)
        self.assertEqual(snapshot["outstanding_amount"], 3345.0)
        self.assertEqual(snapshot["payment_status"], "PARTIAL")

        # Step 6: building totals for M1. The report bills rent only where there
        # is a resident, but counts electricity for every room because the meter
        # runs whether or not the room is let — which is exactly right, since
        # the landlord pays for a vacant room's power too.
        occupied_m1 = [r for r in spec.OCCUPIED_ROOMS if r.building == "M1"]
        vacant_m1 = [r for r in spec.VACANT_ROOMS if r.building == "M1"]
        report = self.get_json(reverse("monthly_report_api"))
        m1_line = next(line for line in report["income"] if line["building"] == "M1")

        m1_expected = sum(
            (self.expected_total(r.number) for r in occupied_m1), Decimal("0.00")
        ) + sum(
            (self.expected_electricity(r.number) for r in vacant_m1), Decimal("0.00")
        )
        self.assertEqual(money(m1_line["gross_expected"]), m1_expected)
        self.assertEqual(
            money(m1_line["collected"]),
            sum((self.expected_paid(r.number) for r in occupied_m1), Decimal("0.00")),
        )

        # Step 7: dashboard and analytics agree with the room snapshots.
        snapshots = self.snapshots()
        metrics = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        self.assertEqual(
            money(metrics["expected_yield"]),
            sum((money(s["total_bill"]) for s in snapshots.values()), Decimal("0.00")),
        )
        self.assertEqual(
            money(metrics["realized_revenue"]),
            sum((money(s["collected_amount"]) for s in snapshots.values()), Decimal("0.00")),
        )


class CrossModulePropagationTests(SeededMutationTestCase):
    """M.2 - M.3: propagation and total agreement across surfaces."""

    def test_m2_a_live_collection_propagates_to_every_surface_at_once(self):
        """
        Collect on a DUE room and verify the change is visible everywhere in the
        same request cycle — no stale figure on any page.
        """
        number = "A-106"
        room_id = self.room_id(number)
        amount = Decimal("3000.00")

        before_room = self.room_snapshot(number)
        before_metrics = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        before_report = self.get_json(reverse("monthly_report_api"))
        before_m1 = next(l for l in before_report["income"] if l["building"] == "M1")

        response = self.post_json(
            reverse("api_collect_payment", args=[room_id]), {"amount": str(amount)}
        )
        self.assertEqual(response.status_code, 200)

        # Room card / drawer snapshot.
        after_room = self.room_snapshot(number)
        self.assertEqual(
            money(after_room["collected_amount"]),
            money(before_room["collected_amount"]) + amount,
        )
        self.assertEqual(after_room["payment_status"], "PARTIAL")

        # Payment history.
        history = self.get_json(reverse("api_room_payments", args=[room_id]))["payments"]
        self.assertEqual(history[0]["amount"], float(amount))

        # Building totals.
        after_report = self.get_json(reverse("monthly_report_api"))
        after_m1 = next(l for l in after_report["income"] if l["building"] == "M1")
        self.assertEqual(
            money(after_m1["collected"]), money(before_m1["collected"]) + amount
        )

        # Dashboard, and analytics reading the same ledger.
        after_metrics = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        self.assertEqual(
            money(after_metrics["realized_revenue"]),
            money(before_metrics["realized_revenue"]) + amount,
        )
        self.assertEqual(
            money(after_metrics["realized_revenue"]), money(after_report["gross_collected"])
        )

    def test_m3_every_surface_reports_identical_figures_for_every_room(self):
        """
        Sweep all 36 rooms and require the room list, the room detail endpoint
        and the dashboard to agree. No room counted twice, none omitted.
        """
        listed = self.snapshots()
        for number in spec.ROOMS_BY_NUMBER:
            with self.subTest(room=number):
                self.assertEqual(self.room_snapshot(number), listed[number])

        metrics = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        self.assertEqual(
            money(metrics["expected_yield"]),
            sum((money(s["total_bill"]) for s in listed.values()), Decimal("0.00")),
        )
        self.assertEqual(
            money(metrics["realized_revenue"]),
            sum((money(s["collected_amount"]) for s in listed.values()), Decimal("0.00")),
        )
        self.assertEqual(
            money(metrics["accounts_receivable"]),
            sum((money(s["outstanding_amount"]) for s in listed.values()), Decimal("0.00")),
        )


class CrossModuleLoopTests(SeededMutationTestCase):
    """M.4 - M.6: the operational loop, the vacant path and per-month history."""

    def test_m4_bill_generation_then_payment_then_analytics_stay_consistent(self):
        """The full operational loop on one room: re-read, collect, reconcile."""
        number = "C-102"
        room_id = self.room_id(number)

        # Re-read the meter, adding 40 units on top of the existing consumption.
        bill = ElectricityBill.objects.get(room_id=room_id, month=self.reference_month)
        target = bill.starting_reading + bill.units_consumed + Decimal(40)
        generated = self.post_json(
            reverse("api_generate_bill", args=[room_id]), {"current_reading": str(target)}
        )
        self.assertEqual(generated.status_code, 200)

        expected_total = self.room_snapshot(number)["total_bill"]
        self.assertGreater(expected_total, 0)

        collected = self.post_json(
            reverse("api_collect_payment", args=[room_id]),
            {"amount": f"{expected_total:.2f}"},
        )
        self.assertEqual(collected.status_code, 200)
        self.assertEqual(collected.json()["payment_status"], "PAID")

        settled = self.room_snapshot(number)
        self.assertEqual(settled["outstanding_amount"], 0.0)
        self.assertEqual(settled["payment_status"], "PAID")

        report = self.get_json(reverse("monthly_report_api"))
        building_2 = next(l for l in report["income"] if l["building"] == "2")
        # Same rule as M.1: rent is billed only where a resident exists, but the
        # meter runs in every room, so vacant-room electricity is still a cost.
        vacant_2 = [r for r in spec.VACANT_ROOMS if r.building == "2"]
        expected_2 = sum(
            (
                money(s["total_bill"])
                for s in self.snapshots().values()
                if s["building"] == "2" and s["resident"] != "No resident"
            ),
            Decimal("0.00"),
        ) + sum((self.expected_electricity(r.number) for r in vacant_2), Decimal("0.00"))
        self.assertEqual(money(building_2["gross_expected"]), expected_2)

        metrics = self.get_json(reverse("dashboard_metrics_api"))["metrics"]
        self.assertEqual(
            money(metrics["realized_revenue"]), money(report["gross_collected"])
        )

    def test_m5_a_vacant_room_appears_consistently_on_every_surface(self):
        """
        The vacant path: no resident anywhere, and no rent owed anywhere. A
        vacant room that reports rent receivable is a visible, expensive bug.
        """
        for room_spec in spec.VACANT_ROOMS:
            with self.subTest(room=room_spec.number):
                snapshot = self.room_snapshot(room_spec.number)
                self.assertEqual(snapshot["resident"], "No resident")
                self.assertEqual(snapshot["collected_amount"], 0.0)
                self.assertEqual(snapshot["outstanding_amount"], 0.0)

                history = self.get_json(
                    reverse("api_room_payments", args=[self.room_id(room_spec.number)])
                )["payments"]
                this_month = [
                    r for r in history
                    if r["date"].startswith(f"{self.reference_month:%Y-%m}")
                ]
                self.assertEqual(this_month, [], "a vacant room collects nothing")

                report = self.get_json(reverse("monthly_report_api"))
                line = next(
                    l for l in report["income"] if l["building"] == room_spec.building
                )
                self.assertGreater(line["electricity"], 0, "the meter still runs")

    def test_m6_history_totals_agree_with_the_ledger_across_every_seeded_month(self):
        """
        For every room and every month, the payment history must sum to the
        collected amount on the corresponding monthly bill.
        """
        from .models import PaymentRecord

        for room_spec in spec.OCCUPIED_ROOMS:
            history = self.get_json(
                reverse("api_room_payments", args=[self.room_id(room_spec.number)])
            )["payments"]
            for month in self.seeded_months:
                prefix = f"{month:%Y-%m}"
                with self.subTest(room=room_spec.number, month=month):
                    monthly = MonthlyPayment.objects.get(
                        room=self.room(room_spec.number), month=month
                    )
                    from_history = sum(
                        (
                            money(record["amount"])
                            for record in history
                            if record["date"].startswith(prefix)
                        ),
                        Decimal("0.00"),
                    )
                    from_records = sum(
                        (
                            money(record.payment_amount)
                            for record in PaymentRecord.objects.filter(
                                monthly_payment=monthly
                            )
                        ),
                        Decimal("0.00"),
                    )
                    self.assertEqual(from_history, monthly.paid_amount)
                    self.assertEqual(from_records, monthly.paid_amount)
