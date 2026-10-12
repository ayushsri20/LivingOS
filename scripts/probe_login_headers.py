#!/usr/bin/env python3
"""Dump the exact response headers of a successful and a failed login."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = f"http://127.0.0.1:{os.environ.get('PORT', '8034')}"
USER, PASSWORD = "tester", "TesterPass!2026"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def opener():
    jar = CookieJar()
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)
    o.jar = jar
    return o


def token(o):
    with o.open(urllib.request.Request(BASE + "/api/csrf/")) as r:
        t = json.loads(r.read())["csrfToken"]
    for c in o.jar:
        if c.name == "csrftoken":
            t = c.value
    return t


def login(o, body, headers, label):
    req = urllib.request.Request(BASE + "/login/", data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        r = o.open(req)
        status, hdrs = r.status, r.headers
    except urllib.error.HTTPError as e:
        status, hdrs = e.code, e.headers
    print(f"--- {label}: status {status}")
    for raw in hdrs.get_all("Set-Cookie") or []:
        print(f"    Set-Cookie: {raw}")
    if hdrs.get("Location"):
        print(f"    Location:   {hdrs.get('Location')}")
    return status


o = opener()
t = token(o)
login(o, urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode(),
       {"X-CSRFToken": t, "Content-Type": "application/x-www-form-urlencoded"},
       "valid credentials")

print()
print("session cookie stored by the client:", [c.name for c in o.jar])

# Does the authenticated session survive to the API?
req = urllib.request.Request(BASE + "/api/rooms/")
for c in o.jar:
    req.add_header("Cookie", f"{c.name}={c.value}")
try:
    with o.open(req) as r:
        body = json.loads(r.read())
    print("GET /api/rooms/ ->", r.status, "count =", body.get("count"))
except urllib.error.HTTPError as e:
    print("GET /api/rooms/ ->", e.code)
