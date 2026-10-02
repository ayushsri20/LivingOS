from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import random
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Guest, Room, MonthlyPayment, PaymentRecord, ElectricityBill

def run_population():
    print("🚀 STARTING: Full House Population... (Filling every room)")
    
    # Clean slate first? No, user said "fill out all rooms", maybe respecting existing ones?
    # Let's assume we want a fresh full house for testing, but let's check first.
    # To avoid conflicts, we'll just fill EMPTY slots.
    
    rooms = Room.objects.all().order_by('number')
    today = date.today()
    current_month = date(today.year, today.month, 1)
    
    room_count = 0
    guest_count = 0
    
    first_names = [ "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaam", "Krishna", "Ishaan",
                    "Diya", "Saanvi", "Aditi", "Myra", "Ananya", "Pari", "Riya", "Aadhya", "Kiara", "Shanaya" ]
    last_names = [ "Sharma", "Verma", "Gupta", "Malhotra", "Singh", "Patel", "Reddy", "Iyer", "Nair", "Das" ]
    
    for room in rooms:
        capacity = room.capacity
        current_occ = room.current_occupancy # This property is live
        
        slots_needed = capacity - current_occ
        
        if slots_needed <= 0:
            print(f"Room {room.number} is FULL ({current_occ}/{capacity}). Skipping.")
            continue
            
        print(f"Populating Room {room.number} ({slots_needed} slots open)...")
        
        for i in range(slots_needed):
            fname = random.choice(first_names)
            lname = random.choice(last_names)
            phone = f"9{random.randint(100000000, 999999999)}"
            email = f"{fname.lower()}.{lname.lower()}{random.randint(1,999)}@test.com"
            
            # Occupation logic
            occ_type = random.choice(['student', 'professional'])
            college = "IIT Delhi" if occ_type == 'student' else ""
            
            # Check-in date: varied over last 3 months
            check_in = today - timedelta(days=random.randint(5, 90))
            
            guest = Guest.objects.create(
                first_name=fname,
                last_name=lname,
                phone=phone,
                email=email,
                room=room,
                check_in_date=check_in,
                
                student_college=college,
                occupancy_preference='double' if capacity > 1 else 'single',
                is_active=True
            )
            
            # Create Monthly Payment (this month)
            rent = room.agreed_rent if getattr(room, 'agreed_rent', None) else room.price
            status = random.choice(['paid', 'partial', 'pending'])
            paid_amt = rent if status == 'paid' else (rent / 2 if status == 'partial' else 0)
            
            # Create or Get Monthly Payment (this month)
            rent = room.agreed_rent if getattr(room, 'agreed_rent', None) else room.price
            status = random.choice(['paid', 'partial', 'pending'])
            paid_amt_now = rent if status == 'paid' else (rent / 2 if status == 'partial' else 0)
            
            mp, created = MonthlyPayment.objects.get_or_create(
                room=room,
                month=current_month,
                defaults={
                    'rent_amount': rent,
                    'paid_amount': 0,
                    'payment_status': 'pending'
                }
            )
            
            # If we are adding a payment for this new tenant, update the MP
            if paid_amt_now > 0:
                mp.paid_amount += Decimal(paid_amt_now)
                # Cap at rent amount
                if mp.paid_amount >= mp.rent_amount:
                    mp.paid_amount = mp.rent_amount
                    mp.payment_status = 'paid'
                elif mp.paid_amount > 0:
                    mp.payment_status = 'partial'
                mp.save()

                PaymentRecord.objects.create(
                    monthly_payment=mp,
                    payment_amount=paid_amt_now,
                    payment_date=today - timedelta(days=random.randint(0, 5)),
                    payment_method='upi',
                    reference_number=f"TXN{random.randint(100000, 999999)}"
                )
            
            guest_count += 1
            
        # Create ElectricityBill (if not exists for this month)
        if not ElectricityBill.objects.filter(room=room, month=current_month).exists():
            last_reading = random.uniform(1000, 5000)
            units = random.uniform(50, 300)
            new_reading = last_reading + units
            rate = 13
            amount = Decimal(units * rate)
            
            is_paid_bool = random.choice([True, False])
            
            ElectricityBill.objects.create(
                room=room,
                guest=room.guest_set.first(), # Just pick first tenant as payer
                month=current_month,
                starting_reading=last_reading,
                ending_reading=new_reading,
                units_consumed=units,
                bill_amount=amount,
                rate_per_unit=rate,
                due_date=today + timedelta(days=10),
                
                paid_amount=amount if is_paid_bool else 0,
                bill_status='paid' if is_paid_bool else 'pending',
                paid_date=today if is_paid_bool else None
            )
            
        room_count += 1

    print("="*40)
    print(f"✅ FULL HOUSE POPULATION COMPLETE")
    print(f"   - Added {guest_count} new guests")
    print(f"   - Filled {room_count} rooms")
    print(f"   - Generated Financial Records for all.")
    print("="*40)

if __name__ == "__main__":
    run_population()
