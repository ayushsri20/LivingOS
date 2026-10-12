#!/usr/bin/env python3
"""End-to-end browser-equivalent check against a live settings_test server.

Read-only apart from one throwaway payment against a DUE room, which is rolled
back by the process exiting. Reports the same numbers the UI renders.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = f"http://127.0.0.1:{os.environ.get('PORT', '8031')}"
class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep 302 visible: the browser follows it, urllib would not."""

    def redirect_request(self, *args, **kwargs):
        return None


jar = CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar), NoRedirect
)
opener.addheaders = [("Accept", "application/json")]


def call(path, data=None, headers=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    request = urllib.request.Request(BASE + path, data=body, method="POST" if data else "GET")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with opener.open(request) as response:
            status, payload = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, payload = error.code, error.read()
    except urllib.error.URLError as error:
        return 0, {"error": str(error)}
    try:
        return status, json.loads(payload or b"{}")
    except (json.JSONDecodeError, ValueError):
        # HTML response (login page, dashboard shell) — the status is what matters.
        return status, {}


def cookie(name):
    for item in jar:
        if item.name == name:
            return item.value
    return ""


status, csrf = call("/api/csrf/")
token = csrf.get("csrfToken", "")
print(f"GET  /api/csrf/            -> {status}")

status, _ = call(
    "/login/",
    {"username": "tester", "password": "TesterPass!2026"},
    {"X-CSRFToken": token, "Content-Type": "application/x-www-form-urlencoded"},
)
print(f"POST /login/               -> {status} (302 = authenticated)")

status, rooms = call("/api/rooms/")
occupied = [r for r in rooms.get("rooms", []) if r["resident"] != "No resident"]
print(f"GET  /api/rooms/           -> {status}")
print(f"      count      = {rooms.get('count')}")
print(f"      occupied   = {len(occupied)}")
print(f"      vacant     = {rooms.get('count', 0) - len(occupied)}")
print(f"      buildings  = {len(rooms.get('buildings', []))}")

sample = occupied[0]
print(f"      sample     = {sample['room']} / {sample['resident']} / "
      f"total {sample['total_bill']} / {sample['payment_status']}")

status, dash = call("/api/dashboard/metrics/")
meta = dash.get("meta", {})
metrics = dash.get("metrics", {})
print(f"GET  /api/dashboard/metrics/ -> {status}")
print(f"      total_rooms     = {meta.get('total_rooms')}")
print(f"      occupied_rooms  = {meta.get('occupied_rooms')}")
print(f"      vacant          = {meta.get('total_rooms', 0) - meta.get('occupied_rooms', 0)}")
print(f"      expected_yield  = {metrics.get('expected_yield')}")
print(f"      realized        = {metrics.get('realized_revenue')}")
print(f"      receivable      = {metrics.get('accounts_receivable')}")

# A vacant room must carry no resident and no receivable.
vacant = [r for r in rooms["rooms"] if r["resident"] == "No resident"]
print(f"      vacant sample   = {vacant[0]['room']} resident={vacant[0]['resident']!r} "
      f"outstanding={vacant[0]['outstanding_amount']}")

ok = (
    status == 200
    and rooms.get("count") == 36
    and len(occupied) == 30
    and meta.get("total_rooms") == 36
    and meta.get("occupied_rooms") == 30
)
print()
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
