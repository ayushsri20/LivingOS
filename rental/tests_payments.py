"""
Category F - Payments (12 tests).

Covers the five named scenarios (PAY-001 full, PAY-002 partial, PAY-003 none,
PAY-004 three instalments, PAY-005 overpayment) plus the validation rules that
protect the ledger from bad input.

PAY-005 needs a stated decision rather than a silent one, so see
:func:`test_f9_pay005_overpayment_behaviour_is_explicit_and_documented` for the
rule this application actually implements.
"""
from decimal import Decimal

from django.urls import reverse

from .models import MonthlyPayment, PaymentRecord
from .test_support import SeededApiTestCase, SeededMutationTestCase
from .testdata import spec


class SeededPaymentScenarioTests(SeededApiTestCase):
    """F.1 - F.4: the scenarios that live in the seeded data."""

    def test_f1_pay001_full_payment_leaves_nothing_outstanding(self):
        scenario = self.scenario("PAY-001")
        number = scenario.room_number
        snapshot = self.room_snapshot(number)
        self.assertEqual(snapshot["total_bill"], float(scenario.expected_bill))
        self.assertEqual(snapshot["collected_amount"], float(scenario.expected_paid))
        self.assertEqual(snapshot["outstanding_amount"], float(scenario.expected_outstanding))
        self.assertEqual(snapshot["payment_status"], scenario.expected_status)

    def test_f2_pay002_partial_payment_reports_the_exact_remainder(self):
        scenario = self.scenario("PAY-002")
        snapshot = self.room_snapshot(scenario.room_number)
        self.assertEqual(snapshot["total_bill"], float(scenario.expected_bill))
        self.assertEqual(snapshot["collected_amount"], float(scenario.expected_paid))
        self.assertEqual(snapshot["outstanding_amount"], float(scenario.expected_outstanding))
        self.assertEqual(snapshot["payment_status"], scenario.expected_status)

    def test_f3_pay003_no_payment_leaves_the_full_bill_outstanding(self):
        scenario = self.scenario("PAY-003")
        number = scenario.room_number
        snapshot = self.room_snapshot(number)
        self.assertEqual(snapshot["total_bill"], float(scenario.expected_bill))
        self.assertEqual(snapshot["collected_amount"], 0.0)
        self.assertEqual(snapshot["outstanding_amount"], float(scenario.expected_bill))
        self.assertEqual(snapshot["payment_status"], "DUE")
        self.assertEqual(
            PaymentRecord.objects.filter(
                monthly_payment__room=self.room(number), monthly_payment__month=self.reference_month
            ).count(),
            0,
        )

    def test_f4_pay004_three_instalments_are_all_recorded_and_sum_to_the_bill(self):
        scenario = self.scenario("PAY-004")
        number = scenario.room_number
        monthly = MonthlyPayment.objects.get(
            room=self.room(number), month=self.reference_month
        )
        records = PaymentRecord.objects.filter(monthly_payment=monthly).order_by("payment_date")

        self.assertEqual(len(scenario.instalments), 3)
        self.assertEqual(records.count(), 3)
        self.assertEqual(sum(records.values_list("payment_amount", flat=True)), Decimal(scenario.expected_bill))
        self.assertEqual(monthly.paid_amount, Decimal(scenario.expected_bill))
        self.assertEqual(monthly.payment_status, "paid")
        # Three distinct methods, so the history view is not uniform.
        self.assertEqual(len({record.payment_method for record in records}), 3)


class PaymentValidationTests(SeededMutationTestCase):
    """F.5 - F.8: what the collection endpoint refuses."""

    def test_f5_a_missing_amount_is_rejected_without_writing_a_record(self):
        room_id = self.room_id("A-103")
        before = PaymentRecord.objects.filter(
            monthly_payment__room_id=room_id
        ).count()

        response = self.post_json(reverse("api_collect_payment", args=[room_id]), {})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertIn("required", response.json()["message"].lower())
        self.assertEqual(
            PaymentRecord.objects.filter(monthly_payment__room_id=room_id).count(), before
        )

    def test_f6_zero_negative_and_sub_paise_amounts_are_all_rejected(self):
        room_id = self.room_id("A-103")
        before = PaymentRecord.objects.filter(monthly_payment__room_id=room_id).count()
        url = reverse("api_collect_payment", args=[room_id])

        for amount in ("0", "-1", "0.001", "-0.50"):
            with self.subTest(amount=amount):
                response = self.post_json(url, {"amount": amount})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["success"])

        self.assertEqual(
            PaymentRecord.objects.filter(monthly_payment__room_id=room_id).count(), before
        )

    def test_f7_an_invalid_payment_method_is_rejected(self):
        room_id = self.room_id("A-103")
        before = PaymentRecord.objects.filter(monthly_payment__room_id=room_id).count()

        response = self.post_json(
            reverse("api_collect_payment", args=[room_id]),
            {"amount": "100", "payment_method": "cryptocurrency"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("method", response.json()["message"].lower())
        self.assertEqual(
            PaymentRecord.objects.filter(monthly_payment__room_id=room_id).count(), before
        )

    def test_f8_an_unparseable_amount_is_rejected_rather_than_crashing(self):
        room_id = self.room_id("A-103")
        url = reverse("api_collect_payment", args=[room_id])

        for amount in ("abc", "NaN", "Infinity", "1,00,000"):
            with self.subTest(amount=amount):
                response = self.post_json(url, {"amount": amount})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["success"])
                self.assertTrue(response.json()["message"])



class OverpaymentRuleTests(SeededMutationTestCase):
    """
    F.9: PAY-005 — overpayment.

    The operating brief asks for the rule to be *determined and stated*, not
    silently chosen. This application has no credit-balance field and no
    overpayment validation in ``api_collect_payment``: it accepts the amount,
    adds it to ``paid_amount``, and clamps the reported outstanding at zero with
    ``max(0, total - collected)``.

    So the implemented rule is:

        overpayment is accepted, outstanding never goes negative, and the excess
        is retained in ``paid_amount`` as an implicit credit against this
        room-month.

    These tests pin that behaviour explicitly. If the business later wants
    overpayment *rejected*, this is where that change must be made deliberately —
    it will not happen by accident.
    """

    def test_f9_pay005_overpayment_behaviour_is_explicit_and_documented(self):
        scenario = self.scenario("PAY-005")
        number = scenario.room_number
        room_id = self.room_id(number)
        total = Decimal(scenario.expected_bill)
        attempted = Decimal("8000.00")

        self.assertGreater(attempted, total, "PAY-005 must genuinely be an overpayment")

        response = self.post_json(
            reverse("api_collect_payment", args=[room_id]),
            {"amount": str(attempted), "payment_method": "cash"},
        )

        # Rule 1: the request is accepted.
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        body = response.json()
        # Rule 2: outstanding is clamped at zero, never negative.
        self.assertEqual(body["outstanding_amount"], 0.0)
        # Rule 3: the room reads as settled.
        self.assertEqual(body["payment_status"], "PAID")

        # Rule 4: the whole amount is retained as an implicit credit.
        monthly = MonthlyPayment.objects.get(room_id=room_id, month=self.reference_month)
        self.assertEqual(monthly.paid_amount, attempted)
        self.assertEqual(monthly.payment_status, "paid")

        # Rule 5: exactly one record exists, for the amount actually attempted.
        records = PaymentRecord.objects.filter(monthly_payment=monthly)
        self.assertEqual(records.count(), 1)
        self.assertEqual(records.get().payment_amount, attempted)

        # The snapshot agrees, so no page can display a negative balance.
        snapshot = self.room_snapshot(number)
        self.assertEqual(snapshot["collected_amount"], float(attempted))
        self.assertEqual(snapshot["outstanding_amount"], 0.0)


class PaymentStateTransitionTests(SeededMutationTestCase):
    """F.10 - F.12: transitions, outstanding arithmetic and instalment flows."""

    def test_f10_collecting_the_outstanding_amount_moves_a_room_from_due_to_paid(self):
        number = "A-106"  # PAY-003: nothing collected yet
        room_id = self.room_id(number)
        url = reverse("api_collect_payment", args=[room_id])

        before = self.room_snapshot(number)
        self.assertEqual(before["payment_status"], "DUE")
        outstanding = Decimal(str(before["outstanding_amount"]))

        response = self.post_json(url, {"amount": str(outstanding)})
        self.assertEqual(response.status_code, 200)

        after = self.room_snapshot(number)
        self.assertEqual(after["payment_status"], "PAID")
        self.assertEqual(after["outstanding_amount"], 0.0)
        self.assertEqual(after["collected_amount"], float(outstanding))

    def test_f11_sequential_collections_accumulate_and_flip_the_status_once(self):
        number = "A-106"
        room_id = self.room_id(number)
        url = reverse("api_collect_payment", args=[room_id])
        total = Decimal(str(self.room_snapshot(number)["total_bill"]))

        statuses = []
        for portion in (Decimal("2000"), Decimal("2000"), Decimal("2000")):
            response = self.post_json(url, {"amount": str(portion)})
            self.assertEqual(response.status_code, 200)
            statuses.append(response.json()["payment_status"])

        self.assertEqual(
            statuses, ["PARTIAL", "PARTIAL", "PARTIAL"],
            "a part payment must never be reported as settled",
        )

        # Only the final, exact remainder completes the bill.
        remainder = total - Decimal("6000")
        response = self.post_json(url, {"amount": str(remainder)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payment_status"], "PAID")
        self.assertEqual(response.json()["outstanding_amount"], 0.0)

        monthly = MonthlyPayment.objects.get(room=self.room(number), month=self.reference_month)
        self.assertEqual(monthly.paid_amount, total)
        self.assertEqual(PaymentRecord.objects.filter(monthly_payment=monthly).count(), 4)

    def test_f12_outstanding_is_always_bill_minus_collected_and_never_negative(self):
        for number in ("A-103", "A-106", "C-102", "D-105", "F-102"):
            with self.subTest(room=number):
                snapshot = self.room_snapshot(number)
                bill = Decimal(str(snapshot["total_bill"]))
                collected = Decimal(str(snapshot["collected_amount"]))
                self.assertEqual(
                    Decimal(str(snapshot["outstanding_amount"])),
                    max(Decimal("0.00"), bill - collected),
                )
                self.assertGreaterEqual(snapshot["outstanding_amount"], 0)
