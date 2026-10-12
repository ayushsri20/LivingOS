#!/usr/bin/env python3
"""Diagnose the live browser test environment. Read-only; writes nothing."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hotel_project.settings_test")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from rental.models import (  # noqa: E402
    ElectricityBill,
    Guest,
    MaintenanceExpense,
    MonthlyPayment,
    PaymentRecord,
    Room,
)
from rental.testdata import builder  # noqa: E402

name = settings.DATABASES["default"]["NAME"]
print(f"DB NAME      : {name}")
print(f"NAME type    : {type(name).__name__}  (login_view's isinstance(str) check -> "
      f"{isinstance(name, str)})")
print(f"Exists       : {os.path.exists(name)}")
print(f"Size         : {os.path.getsize(name) if os.path.exists(name) else 0}")

users = list(get_user_model().objects.values_list("username", "is_staff"))
print(f"Users        : {users}")

user = get_user_model().objects.filter(username=builder.TEST_ADMIN_USERNAME).first()
if user:
    ok = user.check_password(builder.TEST_ADMIN_PASSWORD)
else:
    ok = None
print(f"{builder.TEST_ADMIN_USERNAME!r} present: {bool(user)} | password valid: {ok}")
print(f"is_staff     : {user.is_staff if user else None}  (API endpoints require it)")

occupied = Guest.objects.filter(is_active=True, room__isnull=False).values("room_id").distinct().count()
print(f"ROOMS        : {Room.objects.count()}")
print(f"OCCUPIED     : {occupied}")
print(f"VACANT       : {Room.objects.count() - occupied}")
print(f"GUESTS       : {Guest.objects.count()}")
print(f"BILLS        : {MonthlyPayment.objects.count()}")
print(f"ELECTRICITY  : {ElectricityBill.objects.count()}")
print(f"PAYMENTS     : {PaymentRecord.objects.count()}")
print(f"HISTORY(mon) : {sorted(set(MonthlyPayment.objects.values_list('month', flat=True)))}")
print(f"EXPENSES     : {MaintenanceExpense.objects.count()}")
