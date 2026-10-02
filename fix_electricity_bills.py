#!/usr/bin/env python
"""
Generate electricity bills for all active guests who don't have bills
"""
import os
import django
from datetime import datetime, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Guest, ElectricityBill, Room

def backfill_electricity_bills():
    """Create electricity bills for rooms that don't have them"""
    
    print("=" * 60)
    print("BACKFILLING ELECTRICITY BILLS")
    print("=" * 60)
    
    # Get all rooms with active guests
    rooms_with_guests = Room.objects.filter(guest__is_active=True).distinct().order_by('number')
    current_date = datetime.now().date()
    
    total_created = 0
    total_skipped = 0
    
    for room in rooms_with_guests:
        print(f"\n📍 Room {room.number}")
        
        # Get active guests in this room
        active_guests = Guest.objects.filter(room=room, is_active=True).order_by('check_in_date')
        
        if not active_guests.exists():
            continue
        
        # Use the earliest check-in date as the starting point
        earliest_checkin = active_guests.first().check_in_date
        print(f"   Earliest check-in: {earliest_checkin}")
        
        # Generate bills from earliest check-in month to current month
        month = earliest_checkin.replace(day=1)
        current_month = current_date.replace(day=1)
        
        created_for_room = 0
        base_reading = 1000 + (hash(room.number) % 1000)  # Pseudo-random starting reading
        
        while month <= current_month:
            # Check if bill already exists for this room and month
            if ElectricityBill.objects.filter(room=room, month=month).exists():
                print(f"   ⏭️  {month.strftime('%B %Y')}: Already exists")
                total_skipped += 1
            else:
                # Get the primary guest for this month (first one who was there)
                guest_for_month = active_guests.filter(check_in_date__lte=month).first()
                if not guest_for_month:
                    guest_for_month = active_guests.first()
                
                # Generate realistic consumption (100-300 units per month)
                import random
                random.seed(hash(f"{room.id}{month}"))  # Deterministic randomness
                units = Decimal(str(random.randint(100, 300)))
                
                previous_reading = Decimal(str(base_reading))
                current_reading = previous_reading + units
                rate_per_unit = Decimal('8.00')
                bill_amount = units * rate_per_unit
                
                # Set due date to 15th of the month
                due_date = month + timedelta(days=14)
                
                ElectricityBill.objects.create(
                    room=room,
                    guest=guest_for_month,
                    month=month,
                    starting_reading=previous_reading,
                    ending_reading=current_reading,
                    units_consumed=units,
                    rate_per_unit=rate_per_unit,
                    bill_amount=bill_amount,
                    paid_amount=Decimal('0.00'),
                    bill_status='pending',
                    due_date=due_date,
                    notes=f'Auto-generated bill for room {room.number}'
                )
                
                print(f"   ✅ {month.strftime('%B %Y')}: {units} units = ₹{bill_amount}")
                total_created += 1
                created_for_room += 1
                
                # Update base reading for next month
                base_reading = int(current_reading)
            
            # Move to next month
            month = month + relativedelta(months=1)
        
        if created_for_room > 0:
            print(f"   📊 Created {created_for_room} bills for this room")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Electricity Bills Created: {total_created}")
    print(f"Bills Skipped: {total_skipped}")
    print(f"Total Rooms Processed: {rooms_with_guests.count()}")
    print("=" * 60)

if __name__ == '__main__':
    backfill_electricity_bills()
