#!/usr/bin/env python3
"""
Probe every way the login request can actually arrive, against a live server.

Distinguishes the failure modes:
  200 -> the view re-rendered the login page (authenticate() returned None)
  302 -> authenticated
  403 -> CSRF rejected the request before the view ran
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402
import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402
from http.cookiejar import CookieJar  # noqa: E402

BASE = f"http://127.0.0.1:{os.environ.get('PORT', '8033')}"
USER = "tester"
PASSWORD = "TesterPass!2026"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fresh_opener():
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), NoRedirect
    )
    opener.jar = jar
    return opener


def get_token(opener):
    with opener.open(urllib.request.Request(BASE + "/api/csrf/")) as response:
        token = json.loads(response.read())["csrfToken"]
    for cookie in opener.jar:
        if cookie.name == "csrftoken":
            token = cookie.value
    return token


def send(opener, path, body, headers):
    request = urllib.request.Request(BASE + path, data=body, method="POST")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with opener.open(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def classify(status, payload):
    if status == 302:
        return "302 AUTHENTICATED"
    if status == 403:
        return "403 CSRF REJECTED (view never ran)"
    if status == 200:
        text = payload.decode("utf-8", "replace")
        if "Invalid username or password" in text:
            return "200 LOGIN REJECTED (authenticate() returned None)"
        if "Database connection error" in text:
            return "200 DATABASE ERROR inside login_view"
        if "CSRF" in text:
            return "200 page re-rendered (CSRF note)"
        return "200 LOGIN RE-RENDERED (unknown reason)"
    return f"{status}"


# 1. urlencoded + CSRF header  (Django test client / curl equivalent)
opener = fresh_opener()
token = get_token(opener)
status, payload = send(
    opener, "/login/",
    urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode(),
    {"X-CSRFToken": token, "Content-Type": "application/x-www-form-urlencoded"},
)
print(f"urlencoded + X-CSRFToken : {classify(status, payload)}")

# 2. multipart/form-data + CSRF header  (what the React client's FormData sends)
boundary = uuid.uuid4().hex
parts = []
for field, value in (("username", USER), ("password", PASSWORD)):
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"\r\n\r\n{value}\r\n")
body = ("".join(parts) + f"--{boundary}--\r\n").encode()
opener = fresh_opener()
token = get_token(opener)
status, payload = send(
    opener, "/login/", body,
    {"X-CSRFToken": token, "Content-Type": f"multipart/form-data; boundary={boundary}"},
)
print(f"multipart + X-CSRFToken  : {classify(status, payload)}")

# 3. multipart, no CSRF header (a browser FormData POST without the header)
opener = fresh_opener()
get_token(opener)
status, payload = send(
    opener, "/login/", body,
    {"Content-Type": f"multipart/form-data; boundary={boundary}"},
)
print(f"multipart, no CSRF header: {classify(status, payload)}")

# 4. urlencoded, no CSRF header
opener = fresh_opener()
get_token(opener)
status, payload = send(
    opener, "/login/",
    urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode(),
    {"Content-Type": "application/x-www-form-urlencoded"},
)
print(f"urlencoded, no CSRF hdr  : {classify(status, payload)}")

# 5. JSON body (a client that forgets the view reads request.POST)
opener = fresh_opener()
token = get_token(opener)
status, payload = send(
    opener, "/login/", json.dumps({"username": USER, "password": PASSWORD}).encode(),
    {"X-CSRFToken": token, "Content-Type": "application/json"},
)
print(f"JSON body                : {classify(status, payload)}")

# 6. wrong password, for contrast
opener = fresh_opener()
token = get_token(opener)
status, payload = send(
    opener, "/login/",
    urllib.parse.urlencode({"username": USER, "password": "wrong"}).encode(),
    {"X-CSRFToken": token, "Content-Type": "application/x-www-form-urlencoded"},
)
print(f"wrong password (control) : {classify(status, payload)}")
