#!/usr/bin/env python3
"""
Data Integrity Fix Script
Fixes all data integrity issues found in the test suite
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/Users/ayush/hotel_rental/hotel_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Room, Guest, MonthlyPayment, PaymentRecord
from datetime import date
from decimal import Decimal
from django.db.models import Sum

print("\n" + "="*80)
print("DATA INTEGRITY FIX SCRIPT")
print("="*80 + "\n")

# Fix 1: Deactivate tenants with past check-out dates
print("Fix 1: Deactivating tenants with past check-out dates...")
past_checkout_tenants = Guest.objects.filter(
    is_active=True,
    check_out_date__lt=date.today()
)
count = past_checkout_tenants.count()
if count > 0:
    for tenant in past_checkout_tenants:
        print(f"  - Deactivating {tenant.full_name} (Room {tenant.room.number if tenant.room else 'N/A'}) - Check-out: {tenant.check_out_date}")
        tenant.is_active = False
        tenant.save()
    print(f"✅ Deactivated {count} tenants with past check-out dates\n")
else:
    print("✅ No tenants with past check-out dates found\n")

# Fix 2: Ensure only one active tenant per room
print("Fix 2: Ensuring only one active tenant per room...")
fixed_rooms = []
for room in Room.objects.all():
    active_tenants = Guest.objects.filter(room=room, is_active=True).order_by('-check_in_date')
    
    if active_tenants.count() > 1:
        # Keep the most recent tenant active, deactivate others
        most_recent = active_tenants.first()
        others = active_tenants.exclude(id=most_recent.id)
        
        print(f"  Room {room.number}:")
        print(f"    - Keeping active: {most_recent.full_name} (Check-in: {most_recent.check_in_date})")
        
        for tenant in others:
            print(f"    - Deactivating: {tenant.full_name} (Check-in: {tenant.check_in_date})")
            tenant.is_active = False
            tenant.save()
        
        fixed_rooms.append(room.number)

if fixed_rooms:
    print(f"✅ Fixed {len(fixed_rooms)} rooms with multiple active tenants\n")
else:
    print("✅ All rooms have at most one active tenant\n")

# Fix 3: Recalculate payment record totals
print("Fix 3: Recalculating payment record totals...")
fixed_payments = []
for payment in MonthlyPayment.objects.all():
    # Sum all payment records
    total_recorded = PaymentRecord.objects.filter(
        monthly_payment=payment
    ).aggregate(total=Sum('payment_amount'))['total'] or Decimal('0.00')
    
    # Update if mismatch
    if abs(total_recorded - payment.paid_amount) > Decimal('0.01'):
        print(f"  Room {payment.room.number} ({payment.month.strftime('%b %Y')}): {payment.paid_amount} → {total_recorded}")
        payment.paid_amount = total_recorded
        
        # Recalculate status
        total_due = payment.get_total_amount_due()
        if payment.paid_amount >= total_due:
            payment.payment_status = 'paid'
        elif payment.paid_amount > 0:
            payment.payment_status = 'partial'
        else:
            payment.payment_status = 'pending'
        
        payment.save()
        fixed_payments.append(payment.room.number)

if fixed_payments:
    print(f"✅ Fixed {len(fixed_payments)} payment totals\n")
else:
    print("✅ All payment totals are correct\n")

# Fix 4: Update payment statuses
print("Fix 4: Updating payment statuses...")
status_updates = []
for payment in MonthlyPayment.objects.all():
    total_due = payment.get_total_amount_due()
    paid = payment.paid_amount
    
    # Determine correct status
    correct_status = None
    if paid >= total_due:
        correct_status = 'paid'
    elif paid > 0:
        correct_status = 'partial'
    elif payment.month < date.today().replace(day=1):
        correct_status = 'overdue'
    else:
        correct_status = 'pending'
    
    # Update if wrong
    if payment.payment_status != correct_status:
        print(f"  Room {payment.room.number} ({payment.month.strftime('%b %Y')}): {payment.payment_status} → {correct_status}")
        payment.payment_status = correct_status
        payment.save()
        status_updates.append(payment.room.number)

if status_updates:
    print(f"✅ Updated {len(status_updates)} payment statuses\n")
else:
    print("✅ All payment statuses are correct\n")

print("="*80)
print("DATA INTEGRITY FIX COMPLETE")
print("="*80 + "\n")
