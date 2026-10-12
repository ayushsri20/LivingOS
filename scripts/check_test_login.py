#!/usr/bin/env python3
"""Read-only login diagnostic for the test user. Writes nothing."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hotel_project.settings_test")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import authenticate, get_user_model  # noqa: E402

from rental.testdata import builder  # noqa: E402

USERNAME = builder.TEST_ADMIN_USERNAME
PASSWORD = builder.TEST_ADMIN_PASSWORD

print(f"AUTHENTICATION_BACKENDS: {getattr(settings, 'AUTHENTICATION_BACKENDS', '<django default: ModelBackend>')}")

users = get_user_model()
print(f"all users (username, is_active, is_staff): "
      f"{list(users.objects.values_list('username', 'is_active', 'is_staff'))}")

user = users.objects.filter(username=USERNAME).first()
print(f"user exists        : {bool(user)}")
if user is None:
    raise SystemExit(0)

print(f"is_active          : {user.is_active}")
print(f"is_staff           : {user.is_staff}")
print(f"is_superuser       : {user.is_superuser}")
print(f"has_usable_password: {user.has_usable_password()}")
print(f"check_password     : {user.check_password(PASSWORD)}")

authenticated = authenticate(username=USERNAME, password=PASSWORD)
print(f"authenticate()     : {authenticated}")

# Same path the view uses, to rule out a backend/model difference.
from django.contrib.auth import login as auth_login  # noqa: E402
from django.test import RequestFactory  # noqa: E402

request = RequestFactory().post("/login/", {"username": USERNAME, "password": PASSWORD})
if authenticated:
    auth_login(request, authenticated)
    print(f"login() sets session: {request.session.session_key is not None}")
    print(f"request.user authenticated: {request.user.is_authenticated}")
