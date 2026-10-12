"""
Category E - Billing (10 tests).

The business rule under test is the existing one: **total bill = agreed rent +
metered electricity**. Nothing here invents a new rule; these tests pin the rule
that already exists so a future change cannot alter it silently.
"""
from decimal import Decimal

from django.urls import reverse

from .models import ElectricityBill, MonthlyPayment
from .test_support import SeededApiTestCase, SeededMutationTestCase
from .testdata import spec


class SeededBillingTests(SeededApiTestCase):
    """E.1 - E.5: the arithmetic of the seeded bills."""

    def test_e1_total_bill_is_agreed_rent_plus_metered_electricity_for_every_room(self):
        for room_spec in spec.OCCUPIED_ROOMS:
            with self.subTest(room=room_spec.number):
                room = self.room(room_spec.number)
                monthly = MonthlyPayment.objects.get(room=room, month=self.reference_month)
                electricity = ElectricityBill.objects.get(
                    room=room, month=self.reference_month
                ).bill_amount
                self.assertEqual(monthly.rent_amount, Decimal(room_spec.rent))
                self.assertEqual(
                    monthly.get_total_amount_due(), monthly.rent_amount + electricity
                )
                self.assertEqual(
                    self.expected_total(room_spec.number), monthly.rent_amount + electricity
                )

    def test_e2_rent_only_rooms_bill_exactly_the_agreed_rent(self):
        """EC-002's room consumes nothing, so its bill is rent alone."""
        room_spec = self.room_spec("B-105")
        snapshot = self.room_snapshot("B-105")
        self.assertEqual(snapshot["electricity_amount"], 0.0)
        self.assertEqual(snapshot["total_bill"], float(Decimal(room_spec.rent)))
        self.assertEqual(snapshot["agreed_rent"], float(Decimal(room_spec.rent)))

    def test_e3_bill_totals_differ_across_rooms_and_are_never_a_single_constant(self):
        totals = {
            room_spec.number: spec.room_total_bill(room_spec, self.reference_month, self.rate)
            for room_spec in spec.OCCUPIED_ROOMS
        }
        self.assertGreaterEqual(len(set(totals.values())), 20)
        for number, total in totals.items():
            with self.subTest(room=number):
                self.assertGreater(total, 0)

    def test_e4_existing_bill_retrieval_matches_the_stored_bill(self):
        for number in ("A-104", "C-101", "D-105"):
            with self.subTest(room=number):
                payload = self.get_json(self.api("api_current_bill", self.room_id(number)))
                self.assertTrue(payload["success"])
                stored = ElectricityBill.objects.get(
                    room=self.room(number), month=self.reference_month
                )
                self.assertEqual(payload["electricity_amount"], float(stored.bill_amount))
                self.assertEqual(payload["units_used"], float(stored.units_consumed))
                self.assertEqual(payload["total_bill"], float(self.expected_total(number)))

    def test_e5_every_occupied_room_has_exactly_one_bill_per_seeded_month(self):
        for room_spec in spec.OCCUPIED_ROOMS:
            for month in self.seeded_months:
                with self.subTest(room=room_spec.number, month=month):
                    self.assertEqual(
                        MonthlyPayment.objects.filter(
                            room=self.room(room_spec.number), month=month
                        ).count(),
                        1,
                    )
                    self.assertEqual(
                        ElectricityBill.objects.filter(
                            room=self.room(room_spec.number), month=month
                        ).count(),
                        1,
                    )


class BillGenerationTests(SeededMutationTestCase):
    """E.6 - E.10: generating, regenerating and retrieving bills."""

    def test_e6_generating_a_bill_creates_the_agreed_rent_and_the_electricity_charge(self):
        room_id = self.room_id("A-103")
        bill = ElectricityBill.objects.get(room_id=room_id, month=self.reference_month)
        # The generator measures from the *previous* month's closing reading, so
        # the new target is built from `starting_reading`, not `ending_reading`.
        target = bill.starting_reading + Decimal(10)

        response = self.post_json(
            reverse("api_generate_bill", args=[room_id]), {"current_reading": str(target)}
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["units_used"], float(Decimal(10)))
        self.assertEqual(body["electricity_amount"], float(Decimal(10) * self.rate))
        self.assertEqual(body["agreed_rent"], float(self.room_spec("A-103").rent))
        # total = agreed rent + the newly metered electricity, recomputed from the
        # new reading rather than carried over from the old bill.
        self.assertEqual(
            body["total_bill"],
            float(Decimal(self.room_spec("A-103").rent) + Decimal(10) * self.rate),
        )

    def test_e7_bill_generation_uses_the_agreed_rent_not_the_list_price(self):
        """A discounted agreed rent must be the one that gets billed."""
        discounted = [
            room_spec.number
            for room_spec in spec.ROOMS
            if self.room(room_spec.number).agreed_rent != self.room(room_spec.number).price
        ]
        for number in discounted:
            with self.subTest(room=number):
                monthly = MonthlyPayment.objects.filter(
                    room=self.room(number), month=self.reference_month
                ).first()
                if monthly is not None:
                    self.assertEqual(
                        monthly.rent_amount, self.room(number).agreed_rent
                    )
                    self.assertNotEqual(monthly.rent_amount, self.room(number).price)

    def test_e8_repeated_bill_generation_is_idempotent_for_the_same_reading(self):
        room_id = self.room_id("C-102")
        bill = ElectricityBill.objects.get(room_id=room_id, month=self.reference_month)
        reading = str(bill.ending_reading)
        url = reverse("api_generate_bill", args=[room_id])

        first = self.post_json(url, {"current_reading": reading}).json()
        second = self.post_json(url, {"current_reading": reading}).json()

        self.assertEqual(first["total_bill"], second["total_bill"])
        self.assertEqual(first["bill"]["id"], second["bill"]["id"])
        self.assertEqual(
            ElectricityBill.objects.filter(room_id=room_id, month=self.reference_month).count(), 1
        )

    def test_e9_a_new_reading_recalculates_the_bill_and_never_doubles_it(self):
        room_id = self.room_id("C-102")
        bill = ElectricityBill.objects.get(room_id=room_id, month=self.reference_month)
        original_units = bill.units_consumed
        target = bill.ending_reading + Decimal(20)

        response = self.post_json(
            reverse("api_generate_bill", args=[room_id]), {"current_reading": str(target)}
        )

        self.assertEqual(response.status_code, 200)
        bill.refresh_from_db()
        self.assertEqual(bill.units_consumed, original_units + Decimal(20))
        self.assertEqual(bill.bill_amount, bill.units_consumed * self.rate)
        self.assertEqual(
            ElectricityBill.objects.filter(room_id=room_id, month=self.reference_month).count(), 1
        )

    def test_e10_bill_generation_preserves_what_has_already_been_collected(self):
        """
        Re-reading a meter must never move the collected amount. Only a
        collection can do that.
        """
        room_id = self.room_id("A-104")  # a settled room
        paid_before = MonthlyPayment.objects.get(
            room_id=room_id, month=self.reference_month
        ).paid_amount
        bill = ElectricityBill.objects.get(room_id=room_id, month=self.reference_month)

        response = self.post_json(
            reverse("api_generate_bill", args=[room_id]),
            {"current_reading": str(bill.ending_reading + Decimal(5))},
        )

        self.assertEqual(response.status_code, 200)
        monthly = MonthlyPayment.objects.get(room_id=room_id, month=self.reference_month)
        self.assertEqual(monthly.paid_amount, paid_before)

        # `generate-bill` does not return a status, so the status is read from the
        # authoritative snapshot the drawer actually renders. Growing the meter by
        # 5 units raises the bill by 5 * rate above what was already collected, so
        # the room must fall back from PAID to PARTIAL with exactly that shortfall.
        shortfall = float(Decimal(5) * self.rate)
        snapshot = self.room_snapshot("A-104")
        self.assertEqual(snapshot["collected_amount"], float(paid_before))
        self.assertEqual(snapshot["total_bill"], float(paid_before) + shortfall)
        self.assertEqual(snapshot["payment_status"], "PARTIAL")
        self.assertEqual(snapshot["outstanding_amount"], shortfall)
