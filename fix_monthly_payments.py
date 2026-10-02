#!/usr/bin/env python
"""
Backfill missing monthly payments for all active guests
"""
import os
import django
from datetime import datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Guest, MonthlyPayment

def backfill_monthly_payments():
    """Generate monthly payment records for all active guests based on their check-in dates"""
    
    print("=" * 60)
    print("BACKFILLING MONTHLY PAYMENTS")
    print("=" * 60)
    
    guests = Guest.objects.filter(is_active=True).order_by('room__number')
    current_date = datetime.now().date()
    
    total_created = 0
    total_skipped = 0
    
    for guest in guests:
        print(f"\n📍 Processing: {guest.full_name} (Room {guest.room.number})")
        print(f"   Check-in: {guest.check_in_date}")
        
        # Start from check-in month
        month = guest.check_in_date.replace(day=1)
        current_month = current_date.replace(day=1)
        
        created_for_guest = 0
        
        while month <= current_month:
            # Check if payment already exists for this room and month
            existing = MonthlyPayment.objects.filter(room=guest.room, month=month).first()
            
            if existing:
                print(f"   ⏭️  {month.strftime('%B %Y')}: Already exists")
                total_skipped += 1
            else:
                # Create monthly payment
                MonthlyPayment.objects.create(
                    room=guest.room,
                    guest=guest,
                    month=month,
                    rent_amount=guest.room.price,
                    paid_amount=Decimal('0.00'),
                    payment_status='pending',
                    notes=f'Auto-generated for {guest.full_name}'
                )
                print(f"   ✅ {month.strftime('%B %Y')}: Created (₹{guest.room.price})")
                total_created += 1
                created_for_guest += 1
            
            # Move to next month
            month = month + relativedelta(months=1)
        
        print(f"   📊 Created {created_for_guest} payments for this guest")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Payments Created: {total_created}")
    print(f"Total Payments Skipped: {total_skipped}")
    print(f"Total Active Guests: {guests.count()}")
    print("=" * 60)

if __name__ == '__main__':
    backfill_monthly_payments()
