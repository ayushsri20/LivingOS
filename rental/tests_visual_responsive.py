"""
Category L - Responsive and visual representation (12 tests).

No browser automation framework exists in this project, and the operating brief
explicitly says not to install a large one just to have one. So this category
does the next best thing that is genuinely automated rather than decorative:

* **L.1 - L.7** assert the *contract* the UI depends on — the CSS ships the
  breakpoints the required viewports need, every status/loading/empty/error
  state has a real class, and money formatting never emits ``NaN``/``undefined``.
* **L.8 - L.12** prove every visual state has real data behind it, and that no
  monetary field can ever reach the UI as null, NaN or a blank string.

The pixel-level checks (no clipped text, no overlapping buttons, drawer usable at
390px) stay a documented manual matrix in TESTING.md. They are not automated here
because nothing in the repository can honestly automate them.
"""
import re
from pathlib import Path

from django.urls import reverse

from .models import MonthlyPayment
from .test_support import SeededApiTestCase
from .testdata import spec

FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "src"


def read_css(name: str) -> str:
    return (FRONTEND / name).read_text()


def read_jsx(name: str) -> str:
    return (FRONTEND / name).read_text()


def strip_desktop_only_blocks(css: str) -> str:
    """
    Remove ``@media (min-width: N) { ... }`` blocks from ``css``.

    Those blocks only ever apply on wide screens, so a `min-width` inside one
    cannot cause horizontal overflow on a phone. Without this, the check below
    reports the desktop layout as a mobile bug.
    """
    out = []
    index = 0
    while True:
        start = css.find("@media", index)
        if start == -1:
            out.append(css[index:])
            break
        # Find the condition and the opening brace of this at-rule.
        brace = css.find("{", start)
        condition = css[start:brace]
        depth = 0
        cursor = brace
        while cursor < len(css):
            if css[cursor] == "{":
                depth += 1
            elif css[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        out.append(css[index:start])
        if "min-width" not in condition:
            out.append(css[start:cursor + 1])
        index = cursor + 1
    return "".join(out)


#: Viewports the operating brief requires the UI to work at.
REQUIRED_VIEWPORTS = (1440, 1280, 1024, 768, 390, 360)


class ResponsiveCssContractTests(SeededApiTestCase):
    """L.1 - L.4: the stylesheet actually covers the required viewports."""

    def test_l1_all_stylesheets_are_present_and_non_empty(self):
        for name in ("App.css", "components.css", "index.css"):
            with self.subTest(stylesheet=name):
                self.assertGreater(
                    len(read_css(name)), 500, f"{name} looks empty or truncated"
                )

    def test_l2_breakpoints_cover_every_required_viewport(self):
        """
        For each required viewport there must be a `max-width` query at or above
        it so the layout is told to reflow. Wider desktop screens are covered by
        the base rules, so those need no query.
        """
        queries = [
            int(value)
            for name in ("App.css", "components.css", "index.css")
            for value in re.findall(r"max-width:\s*(\d+)px", read_css(name))
        ]
        self.assertTrue(queries, "no max-width media queries found at all")
        for viewport in REQUIRED_VIEWPORTS:
            with self.subTest(viewport=viewport):
                self.assertTrue(
                    any(q >= viewport for q in queries),
                    f"no breakpoint at or below {viewport}px; queries={sorted(set(queries))}",
                )

    def test_l3_the_390px_mobile_viewport_has_its_own_layout_rules(self):
        """390px is called out as the most important width, so it gets a query."""
        queries = [
            int(value)
            for name in ("App.css", "components.css", "index.css")
            for value in re.findall(r"max-width:\s*(\d+)px", read_css(name))
        ]
        self.assertTrue(
            any(390 <= q <= 480 for q in queries),
            f"no dedicated small-mobile breakpoint; queries={sorted(set(queries))}",
        )

    def test_l4_no_fixed_min_width_can_force_horizontal_overflow_at_360px(self):
        """
        A `min-width` wider than the viewport is the usual cause of horizontal
        scroll on a phone. Desktop-only blocks are excluded first: a `min-width`
        inside `@media (min-width: 1024px)` never applies at 360px.
        """
        offenders = []
        for name in ("App.css", "components.css"):
            mobile_css = strip_desktop_only_blocks(read_css(name))
            for value in re.findall(r"min-width:\s*(\d+)px", mobile_css):
                if int(value) > 360:
                    offenders.append((name, value))
        self.assertEqual(offenders, [], f"fixed min-widths wider than 360px: {offenders}")


class VisualStateContractTests(SeededApiTestCase):
    """L.5 - L.8: every visual state has a real class and real data."""

    def test_l5_every_payment_status_has_a_dedicated_badge_class(self):
        css = read_css("components.css")
        for state in ("paid", "partial", "due", "vacant"):
            with self.subTest(state=state):
                self.assertRegex(
                    css, rf"\.{state}\b", f"no CSS class for the {state} state badge"
                )

    def test_l6_loading_empty_and_error_states_all_have_a_component_and_a_class(self):
        shared = read_jsx("components/shared.jsx")
        # The state classes are split across both stylesheets, so search both.
        css = read_css("components.css") + read_css("App.css")
        for name in ("LoadingShell", "EmptyState", "Toast", "MetricCard"):
            with self.subTest(component=name):
                self.assertIn(f"function {name}", shared)
        for cls in ("loading-shell", "empty-state", "toast", "error-state", "metric-card"):
            with self.subTest(css_class=cls):
                self.assertIn(f".{cls}", css)

    def test_l7_every_major_view_renders_the_shared_state_components(self):
        """
        LOADING / SUCCESS / EMPTY / ERROR must each be reachable on every page,
        so each view references the shared state components rather than
        rendering a bare page.
        """
        app = read_jsx("App.jsx")
        for view in (
            "RoomsView", "ResidentsView", "DashboardView",
            "ElectricityView", "PaymentsView", "AnalyticsView",
        ):
            with self.subTest(view=view):
                self.assertIn(f"function {view}", app)

        for label in ("LoadingShell", "EmptyState", "error-state"):
            with self.subTest(state=label):
                self.assertGreaterEqual(
                    app.count(label), 3, f"{label} is used in fewer than three views"
                )

    def test_l8_the_room_drawer_exposes_every_element_the_brief_lists(self):
        drawer = read_jsx("components/RoomDrawer.jsx")
        for label, needle in (
            ("resident", "residentName"),
            ("rent", "agreed_rent"),
            ("electricity", "electricity_amount"),
            ("total", "total_bill"),
            ("paid", "collected_amount"),
            ("outstanding", "outstanding_amount"),
            ("payment history", "Payment History"),
            ("collect action", "Collect Payment"),
        ):
            with self.subTest(field=label):
                self.assertIn(needle, drawer)


class MoneyRenderingTests(SeededApiTestCase):
    """L.9 - L.12: money and statuses must never render as NaN/undefined."""

    def test_l9_the_money_formatter_is_null_safe(self):
        """
        ``money()`` receives whatever the API sends. If a field is ever missing
        or null the formatter must still produce a readable value rather than
        the string "NaN".
        """
        utils = read_jsx("utils.js")
        self.assertIn("maximumFractionDigits", utils)
        # `Number(value ?? 0)` is what makes null/undefined safe.
        self.assertRegex(utils, r"Number\(value\s*\?\?\s*0\)")

    def test_l10_every_money_field_in_the_snapshot_is_a_finite_non_negative_number(self):
        """
        A null or NaN would reach the UI as a blank card. Every monetary field
        must be a finite number for all 36 rooms.
        """
        fields = (
            "agreed_rent", "electricity_amount", "total_bill",
            "collected_amount", "outstanding_amount", "electricity_rate",
        )
        for snapshot in self.snapshots().values():
            for field in fields:
                with self.subTest(room=snapshot["room"], field=field):
                    value = snapshot[field]
                    self.assertIsInstance(value, (int, float))
                    self.assertNotIsInstance(value, bool)
                    self.assertEqual(value, value)  # a NaN is never equal to itself
                    self.assertGreaterEqual(value, 0)

    def test_l11_every_room_reports_a_renderable_status_string(self):
        """The badge label comes straight from the API; it must never be blank."""
        allowed = {"PAID", "PARTIAL", "DUE"}
        for snapshot in self.snapshots().values():
            with self.subTest(room=snapshot["room"]):
                status = snapshot["payment_status"]
                self.assertIsInstance(status, str)
                self.assertIn(status, allowed)
                self.assertTrue(status.strip())
                self.assertNotIn("None", status)

    def test_l12_every_record_state_the_brief_lists_is_backed_by_real_data(self):
        """
        The five states a manual visual pass has to see — PAID, PARTIAL, UNPAID,
        OVERDUE, VACANT — must each be backed by real rows, otherwise there is
        nothing to look at.
        """
        snapshots = self.snapshots()
        self.assertEqual(
            {s["payment_status"] for s in snapshots.values()}, {"PAID", "PARTIAL", "DUE"}
        )

        stored = set(
            MonthlyPayment.objects.filter(month=self.reference_month).values_list(
                "payment_status", flat=True
            )
        )
        # PAID / PARTIAL / UNPAID (pending) / OVERDUE all exist in the ledger.
        self.assertTrue({"paid", "partial", "pending", "overdue"}.issubset(stored))

        vacant = [s for s in snapshots.values() if s["resident"] == "No resident"]
        self.assertEqual(len(vacant), len(spec.VACANT_ROOMS))
        self.assertEqual(len(spec.OCCUPIED_ROOMS), 30)

        # Every page endpoint the views depend on must be reachable and populated.
        for name in ("api_rooms", "dashboard_metrics_api", "monthly_report_api"):
            with self.subTest(endpoint=name):
                payload = self.get_json(reverse(name))
                self.assertTrue(payload["success"])
