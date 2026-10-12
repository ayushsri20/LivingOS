#!/usr/bin/env python3
"""
Reproduce the drifted-password failure and prove the fix heals it.

Read-only apart from the test operator's own password, which is what
ensure_test_admin() exists to own.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hotel_project.settings_test")

import django  # noqa: E402

django.setup()

from django.contrib.auth import authenticate, get_user_model  # noqa: E402

from rental.testdata import builder  # noqa: E402

users = get_user_model()
user = users.objects.get(username=builder.TEST_ADMIN_USERNAME)

# Simulate the real-world drift: the account exists, but its password is not the
# documented one (older run, older constant, or a manual createsuperuser).
print("BEFORE — forcing a drifted password")
user.set_password("SomeOtherOldPassword!")
user.save()
print(f"  authenticate(correct password): "
      f"{authenticate(username=builder.TEST_ADMIN_USERNAME, password=builder.TEST_ADMIN_PASSWORD)}")
print(f"  authenticate(drifted password): "
      f"{authenticate(username=builder.TEST_ADMIN_USERNAME, password='SomeOtherOldPassword!')}")
print("  -> this is exactly 'POST /login/ -> 200' with a correct username")

print()
print("AFTER  — ensure_test_admin()")
builder.ensure_test_admin()
user.refresh_from_db()
print(f"  authenticate(correct password): "
      f"{authenticate(username=builder.TEST_ADMIN_USERNAME, password=builder.TEST_ADMIN_PASSWORD)}")
print(f"  is_active={user.is_active} is_staff={user.is_staff} is_superuser={user.is_superuser}")

print()
print("IDEMPOTENCE — run provisioning twice more")
builder.ensure_test_admin()
builder.ensure_test_admin()
print(f"  authenticate(correct password): "
      f"{authenticate(username=builder.TEST_ADMIN_USERNAME, password=builder.TEST_ADMIN_PASSWORD)}")

ok = authenticate(
    username=builder.TEST_ADMIN_USERNAME, password=builder.TEST_ADMIN_PASSWORD
) is not None
print()
print("RESULT:", "PASS — provisioning is self-healing" if ok else "FAIL")
sys.exit(0 if ok else 1)
