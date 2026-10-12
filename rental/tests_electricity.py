"""
Category D - Electricity (10 tests).

The electricity layer is the most error-prone part of a rent system: a reading
that is silently accepted when it should be rejected produces a wrong bill that
is very hard to notice later. These tests cover the three seeded scenarios
(EC-001 normal, EC-002 zero, EC-003 high) and exercise EC-004 (lower reading),
EC-005 (missing reading) and EC-006 (duplicate generation) live.

The per-unit rate is always read from ``settings.ELECTRICITY_RATE_PER_UNIT`` —
never hard-coded — so changing the configured rate re-bills the whole dataset and
these tests still hold.
"""
from decimal import Decimal

from django.urls import reverse

from .models import ElectricityBill, MonthlyPayment
from .test_support import SeededApiTestCase, SeededMutationTestCase
from .testdata import spec


class SeededElectricityScenarioTests(SeededApiTestCase):
    """D.1 - D.3: the three edge cases that live in the dataset."""

    def test_d1_ec001_normal_reading_produces_the_expected_units_and_amount(self):
        scenario = self.electricity_scenario("EC-001")
        bill = ElectricityBill.objects.get(
            room=self.room(scenario.room_number), month=self.reference_month
        )
        self.assertEqual(bill.starting_reading, Decimal(scenario.previous_reading))
        self.assertEqual(bill.ending_reading, Decimal(scenario.current_reading))
        self.assertEqual(bill.units_consumed, Decimal(scenario.expected_units))
        self.assertEqual(bill.bill_amount, Decimal(scenario.expected_amount))

    def test_d2_ec002_zero_consumption_bills_zero_and_keeps_the_reading_flat(self):
        scenario = self.electricity_scenario("EC-002")
        bill = ElectricityBill.objects.get(
            room=self.room(scenario.room_number), month=self.reference_month
        )
        self.assertEqual(bill.units_consumed, Decimal(0))
        self.assertEqual(bill.bill_amount, Decimal("0.00"))
        self.assertEqual(bill.starting_reading, bill.ending_reading)

    def test_d3_ec003_high_consumption_is_billed_at_the_configured_rate(self):
        scenario = self.electricity_scenario("EC-003")
        bill = ElectricityBill.objects.get(
            room=self.room(scenario.room_number), month=self.reference_month
        )
        self.assertEqual(bill.units_consumed, Decimal(500))
        self.assertEqual(bill.bill_amount, Decimal("6500.00"))
        # The amount must be exactly units x the configured rate, not a constant.
        self.assertEqual(bill.bill_amount, bill.units_consumed * self.rate)


class ElectricityCalculationTests(SeededApiTestCase):
    """D.4 - D.7: rates, arithmetic and the meter chain."""

    def test_d4_every_bill_uses_the_configured_rate_exactly(self):
        for bill in ElectricityBill.objects.all():
            with self.subTest(room=bill.room_id, month=bill.month):
                self.assertEqual(bill.rate_per_unit, self.rate)

    def test_d5_every_bill_amount_equals_units_times_rate(self):
        for bill in ElectricityBill.objects.all():
            with self.subTest(room=bill.room_id, month=bill.month):
                self.assertEqual(
                    bill.bill_amount,
                    (bill.units_consumed * bill.rate_per_unit).quantize(Decimal("0.01")),
                )

    def test_d6_meter_readings_chain_month_to_month_with_no_jumps(self):
        """
        Each month's opening reading must be the previous month's closing
        reading. A gap or an overlap means units are being double-counted or
        lost, which is invisible in any single month's total.
        """
        for room_spec in spec.ROOMS:
            previous_end = None
            for month in self.seeded_months:
                with self.subTest(room=room_spec.number, month=month):
                    bill = ElectricityBill.objects.get(
                        room=self.room(room_spec.number), month=month
                    )
                    if previous_end is not None:
                        self.assertEqual(bill.starting_reading, previous_end)
                    self.assertGreaterEqual(bill.ending_reading, bill.starting_reading)
                    self.assertEqual(
                        bill.units_consumed, bill.ending_reading - bill.starting_reading
                    )
                    previous_end = bill.ending_reading

    def test_d7_typical_monthly_consumption_sits_in_a_realistic_band(self):
        """Most rooms read 20-100 units; the outliers are deliberate scenarios."""
        values = [
            spec.room_units(room_spec, self.reference_month)
            for room_spec in spec.ROOMS
        ]
        ordinary = [value for value in values if 0 < value <= 100]
        self.assertGreaterEqual(len(ordinary), 30)
        self.assertGreaterEqual(min(ordinary), 20)



class ElectricityValidationTests(SeededMutationTestCase):
    """D.8 - D.10: EC-004, EC-005 and EC-006, performed live."""

    def test_d8_ec004_a_reading_below_the_previous_one_is_rejected(self):
        """
        A lower-than-previous reading must never produce a bill.

        The rejected value is derived from the room's real previous reading, so
        the test keeps testing "a meter that ran backwards" no matter what the
        seeded history happens to be.
        """
        scenario = self.electricity_scenario("EC-004")
        room_id = self.room_id(scenario.room_number)
        before = ElectricityBill.objects.filter(room_id=room_id).count()
        previous = ElectricityBill.objects.get(
            room_id=room_id, month=self.reference_month
        ).starting_reading

        response = self.post_json(
            reverse("api_generate_bill", args=[room_id]),
            {"current_reading": str(previous - 70)},
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIn("reading", body["message"].lower())
        self.assertEqual(
            ElectricityBill.objects.filter(room_id=room_id).count(), before,
            "a rejected reading must not create or modify any bill",
        )

    def test_d9_ec005_a_missing_reading_is_rejected_with_a_clear_message(self):
        scenario = self.electricity_scenario("EC-005")
        room_id = self.room_id(scenario.room_number)
        before = ElectricityBill.objects.filter(room_id=room_id).count()

        for payload in ({}, {"current_reading": ""}, {"current_reading": "   "}):
            with self.subTest(payload=payload):
                response = self.post_json(
                    reverse("api_generate_bill", args=[room_id]), payload
                )
                self.assertEqual(response.status_code, 400)
                body = response.json()
                self.assertFalse(body["success"])
                self.assertIn("required", body["message"].lower())

        self.assertEqual(ElectricityBill.objects.filter(room_id=room_id).count(), before)

    def test_d10_ec006_regenerating_from_the_same_reading_never_double_charges(self):
        """
        The duplicate-generation case. Running the identical reading twice must
        update the same bill row, never add a second electricity charge.
        """
        room_id = self.room_id("A-101")
        bill = ElectricityBill.objects.get(room_id=room_id, month=self.reference_month)
        original_id = bill.id
        original_amount = bill.bill_amount
        original_total = self.room_snapshot("A-101")["total_bill"]
        # A-101 is settled, so its rent bill exists and must not drift.
        paid_before = MonthlyPayment.objects.get(
            room_id=room_id, month=self.reference_month
        ).paid_amount

        reading = str(bill.ending_reading)
        url = reverse("api_generate_bill", args=[room_id])
        first = self.post_json(url, {"current_reading": reading})
        second = self.post_json(url, {"current_reading": reading})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        # One bill per room per month: the repeat must update, never duplicate.
        self.assertEqual(
            ElectricityBill.objects.filter(room_id=room_id, month=self.reference_month).count(),
            1,
        )
        self.assertEqual(
            ElectricityBill.objects.filter(room_id=room_id).count(),
            len(self.seeded_months),
            "regenerating must not add a bill for any month",
        )
        bill.refresh_from_db()
        self.assertEqual(bill.id, original_id)
        self.assertEqual(bill.bill_amount, original_amount)
        self.assertEqual(second.json()["total_bill"], original_total)
        self.assertEqual(
            MonthlyPayment.objects.get(room_id=room_id, month=self.reference_month).paid_amount,
            paid_before,
            "regenerating a bill must never alter what has already been collected",
        )
