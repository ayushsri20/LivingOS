"""
Category I - Analytics (6 tests).

``/api/reports/monthly/`` and ``/api/reports/yearly/`` are what the Analytics
charts render. The critical property is that every month in the history carries
real, non-degenerate data — an empty or constant series produces a chart that
looks fine and says nothing.

Expected totals are derived from :func:`rental.testdata.builder.expected_totals`,
not read back from the database, so a seeding error cannot validate itself.
"""
from decimal import Decimal

from django.urls import reverse

from .models import ElectricityBill, MonthlyPayment
from .test_support import SeededApiTestCase
from .testdata import builder, spec


class MonthlyReportTests(SeededApiTestCase):
    """I.1 - I.3: monthly totals, trends and building comparison."""

    def test_i1_every_seeded_month_has_real_collection_and_outstanding_data(self):
        for month in self.seeded_months:
            with self.subTest(month=month):
                report = self.get_json(
                    f"{reverse('monthly_report_api')}?month={month:%Y-%m-%d}"
                )
                self.assertTrue(report["success"])
                self.assertGreater(report["gross_expected"], 0)
                self.assertGreater(report["gross_collected"], 0)
                self.assertGreater(report["electricity"], 0)
                self.assertEqual(report["period"]["month"], f"{month:%Y-%m-%d}")

    def test_i2_monthly_report_totals_reconcile_with_the_stored_ledger(self):
        for month in self.seeded_months:
            with self.subTest(month=month):
                report = self.get_json(
                    f"{reverse('monthly_report_api')}?month={month:%Y-%m-%d}"
                )
                rent = sum(
                    MonthlyPayment.objects.filter(month=month).values_list("rent_amount", flat=True),
                    Decimal("0.00"),
                )
                collected = sum(
                    MonthlyPayment.objects.filter(month=month).values_list("paid_amount", flat=True),
                    Decimal("0.00"),
                )
                electricity = sum(
                    ElectricityBill.objects.filter(month=month).values_list("bill_amount", flat=True),
                    Decimal("0.00"),
                )
                self.assertEqual(Decimal(str(report["expected_rent"])), rent)
                self.assertEqual(Decimal(str(report["gross_collected"])), collected)
                self.assertEqual(Decimal(str(report["electricity"])), electricity)

    def test_i3_building_comparison_covers_all_six_buildings_with_varying_figures(self):
        report = self.get_json(reverse("monthly_report_api"))
        lines = {line["building"]: line for line in report["income"]}
        self.assertEqual(set(lines), set(spec.BUILDING_NAMES))

        collected_values = {line["collected"] for line in lines.values()}
        self.assertGreaterEqual(len(collected_values), 4, "building figures must vary")

        for name, line in lines.items():
            with self.subTest(building=name):
                self.assertGreaterEqual(line["expected_rent"], 0)
                self.assertGreaterEqual(line["electricity"], 0)
                self.assertEqual(
                    line["gross_expected"],
                    round(line["expected_rent"] + line["electricity"], 2),
                )
                self.assertIn(name, spec.BUILDING_NAMES)


class YearlyReportTests(SeededApiTestCase):
    """I.4 - I.6: the yearly series and building filters."""

    def test_i4_yearly_report_returns_twelve_months_with_the_seeded_ones_populated(self):
        year = self.reference_month.year
        report = self.get_json(f"{reverse('yearly_report_api')}?year={year}")
        self.assertTrue(report["success"])
        months = report["months"]
        self.assertEqual(len(months), 12)

        populated = {
            entry["month"] for entry in months
            if entry["has_data"] and entry["gross_collection"] > 0
        }
        for month in self.seeded_months:
            with self.subTest(month=month):
                self.assertIn(f"{month:%Y-%m-%d}", populated)
        # Months outside the seeded window are reported as empty, not fabricated.
        for entry in months:
            if entry["month"] not in {f"{m:%Y-%m-%d}" for m in self.seeded_months}:
                with self.subTest(unseeded=entry["month"]):
                    self.assertFalse(entry["has_data"])
                    self.assertEqual(entry["gross_collection"], 0)

    def test_i5_yearly_totals_equal_the_sum_of_the_monthly_reports(self):
        year = self.reference_month.year
        yearly = self.get_json(f"{reverse('yearly_report_api')}?year={year}")
        for month in self.seeded_months:
            with self.subTest(month=month):
                monthly = self.get_json(
                    f"{reverse('monthly_report_api')}?month={month:%Y-%m-%d}"
                )
                entry = next(
                    item for item in yearly["months"]
                    if item["month"] == f"{month:%Y-%m-%d}"
                )
                self.assertEqual(entry["gross_collection"], monthly["gross_collected"])
                self.assertEqual(entry["gross_expected"], monthly["gross_expected"])

        # The yearly roll-up is the sum of its own months, not a separate query.
        self.assertEqual(
            round(
                sum(entry["gross_collection"] for entry in yearly["months"]),
                2,
            ),
            yearly["totals"]["gross_collection"],
        )

    def test_i6_building_filter_is_exact_and_does_not_merge_m1_with_1(self):
        """
        "M1" and "1" are different buildings stored as distinct strings, and the
        report compares names exactly. A substring or loose match would silently
        merge two buildings and corrupt every building-wise total.
        """
        month = f"{self.reference_month:%Y-%m-%d}"

        m1 = self.get_json(f"{reverse('monthly_report_api')}?month={month}&building=M1")
        self.assertEqual(m1["building_filter"], "M1")
        self.assertEqual(
            [line["building"] for line in m1["income"]],
            list(spec.BUILDING_NAMES),
            "the income lines stay complete; the filter scopes deductions, not income",
        )

        other = self.get_json(f"{reverse('monthly_report_api')}?month={month}&building=1")
        self.assertEqual(other["building_filter"], "1")

        # Both buildings genuinely exist and differ, so an exact filter is meaningful.
        m1_rooms = [r for r in spec.ROOMS if r.building == "M1"]
        building_1 = [r for r in spec.ROOMS if r.building == "1"]
        self.assertEqual(len(m1_rooms), 6)
        self.assertEqual(len(building_1), 6)

        rent_m1 = sum(
            MonthlyPayment.objects.filter(
                month=self.reference_month, room__building__name="M1"
            ).values_list("rent_amount", flat=True),
            Decimal("0.00"),
        )
        rent_one = sum(
            MonthlyPayment.objects.filter(
                month=self.reference_month, room__building__name="1"
            ).values_list("rent_amount", flat=True),
            Decimal("0.00"),
        )
        self.assertNotEqual(rent_m1, rent_one)

        # Expenses are filtered by exact building name, so an M1 expense must not
        # appear under the "1" filter.
        for name in ("M1", "1"):
            with self.subTest(building=name):
                expenses = self.get_json(f"{reverse('expenses_api')}?building={name}")
                for row in expenses["expenses"]:
                    self.assertEqual(row["building"], name)

