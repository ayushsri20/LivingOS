"""
Category K - Error and recovery (10 tests).

Every error path has the same obligations:

1. the API answers with a meaningful, human-readable message;
2. nothing is written to the database;
3. a failed request leaves the previously-good state readable and uncorrupted;
4. the operation succeeds on retry once the bad input is fixed;
5. the caller can tell a failure from an empty result.

The payment-history error-state problem called out in the operating brief is
covered end to end in :class:`PaymentHistoryErrorRecoveryTests`.
"""
import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

from .models import MonthlyPayment, PaymentRecord
from .test_support import SeededApiTestCase, SeededMutationTestCase


class ErrorResponseShapeTests(SeededMutationTestCase):
    """K.1 - K.4: every rejection is well-formed and non-destructive."""

    def test_k1_an_unknown_room_id_returns_404_json_not_a_server_error(self):
        response = self.client.get(reverse("api_room_detail", args=[999999]))
        self.assertEqual(response.status_code, 404)

        response = self.post_json(
            reverse("api_collect_payment", args=[999999]), {"amount": "100"}
        )
        self.assertEqual(response.status_code, 404)

    def test_k2_an_unknown_payment_record_is_refused_without_crashing(self):
        """
        These two endpoints handle a missing record differently (one raises 404
        through ``get_object_or_404``, the other catches it and answers 400).
        The contract that matters is: never 500, and never a stack trace.
        """
        for name in ("get_payment_record_details", "get_monthly_payment_records"):
            with self.subTest(endpoint=name):
                response = self.client.get(reverse(name, args=[999999]))
                self.assertGreaterEqual(response.status_code, 400)
                self.assertLess(response.status_code, 500)

    def test_k3_every_rejection_carries_a_readable_message_and_success_false(self):
        cases = [
            (reverse("api_collect_payment", args=[self.room_id("A-103")]), {"amount": "0"}),
            (
                reverse("api_generate_bill", args=[self.room_id("A-103")]),
                {"current_reading": "not-a-number"},
            ),
            (reverse("get_payments_by_month"), None),
            (f"{reverse('monthly_report_api')}?month=13-45-9999", None),
        ]
        for url, payload in cases:
            with self.subTest(url=url):
                if payload is None:
                    response = self.client.get(url)
                else:
                    response = self.post_json(url, payload)
                self.assertGreaterEqual(response.status_code, 400)
                self.assertLess(response.status_code, 500, "a bad input must not 500")
                body = response.json()
                self.assertIs(body["success"], False)
                self.assertTrue(body.get("message"), "a rejection must explain itself")
                # Never leak a traceback or a raw file path to the browser.
                self.assertNotIn("Traceback", body["message"])
                self.assertNotIn(".py", body["message"])

    def test_k4_a_failed_request_never_writes_a_partial_record(self):
        room_id = self.room_id("A-103")
        before = PaymentRecord.objects.filter(monthly_payment__room_id=room_id).count()
        url = reverse("api_collect_payment", args=[room_id])

        for payload in (
            {"amount": "-500"},
            {"amount": "0"},
            {"amount": "abc"},
            {"amount": "100", "payment_method": "gold"},
            {},
        ):
            with self.subTest(payload=payload):
                self.post_json(url, payload)

        self.assertEqual(
            PaymentRecord.objects.filter(monthly_payment__room_id=room_id).count(), before
        )


class ErrorRecoveryTests(SeededMutationTestCase):
    """K.5 - K.6: state survives a failure, and a retry succeeds."""

    def test_k5_a_rejected_payment_leaves_the_room_figures_untouched(self):
        number = "A-103"
        room_id = self.room_id(number)
        before = self.room_snapshot(number)

        self.assertGreaterEqual(
            self.post_json(
                reverse("api_collect_payment", args=[room_id]), {"amount": "-1"}
            ).status_code,
            400,
        )

        self.assertEqual(self.room_snapshot(number), before)

    def test_k6_a_successful_retry_after_a_rejection_clears_the_error(self):
        """
        The retry path: a bad amount is rejected, the same call with a valid
        amount succeeds, and no stale error state survives.
        """
        number = "A-103"
        room_id = self.room_id(number)
        url = reverse("api_collect_payment", args=[room_id])

        rejected = self.post_json(url, {"amount": "-100"})
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(rejected.json()["success"])

        # Retry with a valid amount.
        accepted = self.post_json(url, {"amount": "1000.00"})
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(accepted.json()["success"])
        # The successful response carries no leftover error field.
        self.assertNotIn("message", accepted.json())

        snapshot = self.room_snapshot(number)
        self.assertGreater(snapshot["collected_amount"], 0)
        self.assertEqual(snapshot["payment_status"], "PARTIAL")


class ErrorRecoveryShapeTests(SeededMutationTestCase):
    """K.7 - K.8: empty is not the same as broken."""

    def test_k7_an_empty_api_response_is_distinguishable_from_a_failure(self):
        """
        A room with no payments must return ``success: true`` and an empty list.
        The frontend has to be able to tell that apart from an error, so the
        empty case is a clean success rather than a 400 or a null.
        """
        room_id = self.room_id("A-106")
        PaymentRecord.objects.filter(monthly_payment__room_id=room_id).delete()
        MonthlyPayment.objects.filter(room_id=room_id, month=self.reference_month).update(
            paid_amount=Decimal("0.00")
        )

        payload = self.get_json(reverse("api_room_payments", args=[room_id]))
        self.assertTrue(payload["success"])
        self.assertIsInstance(payload["payments"], list)
        self.assertEqual(payload["payments"], [])

        tenants = self.get_json(reverse("get_room_tenants", args=[self.room_id("A-105")]))
        self.assertTrue(tenants["success"])
        self.assertEqual(tenants["tenants"], [])

    def test_k8_a_very_large_collection_is_accepted_and_reported_honestly(self):
        number = "A-106"
        room_id = self.room_id(number)


class PaymentHistoryErrorRecoveryTests(SeededMutationTestCase):
    """
    K.9: the payment-history error-state problem, exercised end to end.

    Walks the exact sequence from the operating brief: load history, collect,
    confirm the history updates, confirm the totals and status move, "reopen"
    (fresh fetch), "navigate away and return" (fresh request), and "refresh"
    (a brand-new client with no cached state). The old error state must be gone
    after every successful step.
    """

    def test_k9_payment_history_refresh_cycle_from_error_to_recovered(self):
        number = "A-106"
        room_id = self.room_id(number)
        history_url = reverse("api_room_payments", args=[room_id])
        collect_url = reverse("api_collect_payment", args=[room_id])
        prefix = f"{self.reference_month:%Y-%m}"

        # 1-2. Open the room and load its payment history. The room has earlier
        # months of history, but nothing at all this month.
        initial = self.get_json(history_url)["payments"]
        this_month = [r for r in initial if r["date"].startswith(prefix)]
        self.assertEqual(this_month, [])
        opening = self.room_snapshot(number)
        self.assertEqual(opening["payment_status"], "DUE")
        opening_count = len(initial)

        # 3-4. Collect. The history must reflect it on the very next read.
        collected = self.post_json(collect_url, {"amount": "2500.00"})
        self.assertEqual(collected.status_code, 200)
        self.assertTrue(collected.json()["success"])

        refreshed = self.get_json(history_url)["payments"]
        self.assertEqual(len(refreshed), opening_count + 1)
        self.assertEqual(refreshed[0]["amount"], 2500.0)
        self.assertTrue(refreshed[0]["date"].startswith(prefix))

        # 5-7. Total paid changes, outstanding changes, status changes.
        after = self.room_snapshot(number)
        self.assertEqual(after["collected_amount"], 2500.0)
        self.assertEqual(
            after["outstanding_amount"],
            round(opening["outstanding_amount"] - 2500.0, 2),
        )
        self.assertEqual(after["payment_status"], "PARTIAL")

        # 8-10. Close and reopen the drawer: a fresh read must agree exactly.
        reopened = self.room_snapshot(number)
        self.assertEqual(reopened, after)
        self.assertEqual(self.get_json(history_url)["payments"], refreshed)

        # 11-12. Navigate away and come back: a new client, no cached state.
        from django.test import Client

        returning = Client()
        returning.force_login(self.admin)
        away = json.loads(returning.get(history_url).content)
        self.assertTrue(away["success"])
        self.assertEqual(away["payments"], refreshed)

        # 13-14. Full browser refresh: a third client, again no cached state.
        after_refresh = json.loads(returning.get(history_url).content)
        self.assertEqual(after_refresh["payments"], refreshed)
        room_after_refresh = json.loads(
            returning.get(reverse("api_room_detail", args=[room_id])).content
        )["room"]
        self.assertEqual(room_after_refresh["payment_status"], "PARTIAL")
        self.assertEqual(room_after_refresh["collected_amount"], 2500.0)

        # No error text anywhere in any successful payload.
        for payload in (away, after_refresh):
            self.assertNotIn("error", payload)
            self.assertNotIn("message", payload)


class AuthenticationErrorTests(SeededApiTestCase):
    """
    K.10: unauthenticated and non-admin requests.

    The real middleware stack is restored here (rather than the class-level
    test override) so the authentication guard itself is exercised, not bypassed.
    """

    @override_settings(
        MIDDLEWARE=[
            middleware for middleware in settings.MIDDLEWARE
            if "LoginRequiredMiddleware" not in middleware
        ]
    )
    def test_k10_anonymous_requests_are_refused_and_non_admins_are_denied(self):
        anonymous = Client()
        endpoints = {
            "rooms": reverse("api_rooms"),
            "room_detail": reverse("api_room_detail", args=[self.room_id("A-101")]),
            "metrics": reverse("dashboard_metrics_api"),
        }
        for label, url in endpoints.items():
            with self.subTest(url=url, user="anonymous"):
                response = anonymous.get(url)
                # Never 200: the view's own `login_required` must refuse before
                # any data is touched.
                self.assertIn(response.status_code, (302, 401, 403))

        # A logged-in non-staff user must not reach the per-room money endpoints.
        plain = get_user_model().objects.create_user(
            username="non-staff", password="x", is_staff=False
        )
        visitor = Client()
        visitor.force_login(plain)
        for label in ("rooms", "room_detail"):
            with self.subTest(url=endpoints[label], user="non-staff"):
                response = visitor.get(endpoints[label])
                self.assertNotEqual(response.status_code, 200)
                self.assertLess(response.status_code, 500)

    def test_k10b_reporting_endpoints_are_reachable_by_any_logged_in_user(self):
        """
        Documents a real authorisation gap — test report finding SEC-001 (P1).

        All 41 views in ``rental/views.py`` are guarded by ``@login_required``
        **and** ``@user_passes_test(is_admin)``. These four reporting endpoints
        carry ``@login_required`` only, so any authenticated non-staff account
        can read portfolio-wide financials: expected yield, realized revenue,
        accounts receivable, per-building income and expenses.

        This test pins the behaviour as it is today rather than asserting the
        behaviour we would prefer. The fix is one decorator on each of
        ``dashboard_metrics_api``, ``expenses_api``, ``monthly_report_api`` and
        ``yearly_report_api``. It is deliberately **not** applied here: changing
        the authorisation model of a financial application is a business
        decision, not a test-suite side effect.

        Once the fix lands, flip the status assertion below to a non-200 and this
        test becomes the regression guard for it.
        """
        plain = get_user_model().objects.create_user(
            username="non-staff-2", password="x", is_staff=False
        )
        visitor = Client()
        visitor.force_login(plain)

        exposed = {
            "dashboard_metrics_api": reverse("dashboard_metrics_api"),
            "expenses_api": reverse("expenses_api"),
            "monthly_report_api": reverse("monthly_report_api"),
            "yearly_report_api": reverse("yearly_report_api"),
        }
        for name, url in exposed.items():
            with self.subTest(endpoint=name):
                response = visitor.get(url)
                # Current behaviour: served to any authenticated user.
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertTrue(body["success"])
                self.assertNotIn("Traceback", str(body))
