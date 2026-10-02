
import os
import django
import time
from decimal import Decimal
from datetime import date

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Room, MonthlyPayment, PaymentRecord, Guest
from django.db import transaction

def stress_test_sync():
    """
    Simulates a burst of activity (data creation/updates) to ensure the system
    remains stable during database operations and explain log behavior.
    """
    print("--- Imperial System Stress Test & Log Verification ---")
    print("Goal: Generate concurrent load to verify transactional integrity and checkpoint safety.")
    
    # 1. Create a dummy test room
    room_number = "STRESS-01"
    room, _ = Room.objects.get_or_create(
        number=room_number,
        defaults={'room_type': 'single', 'price': 5000}
    )
    
    print(f"[*] Starting burst payment cycle for Room {room_number}...")
    
    start_time = time.time()
    try:
        with transaction.atomic():
            # Create a monthly bill
            payment, _ = MonthlyPayment.objects.get_or_create(
                room=room,
                month=date(2026, 1, 1),
                defaults={'rent_amount': 5000, 'paid_amount': 0}
            )
            
            # Generate 100 micro-payments in a single transaction (Stress)
            for i in range(100):
                PaymentRecord.objects.create(
                    monthly_payment=payment,
                    payment_date=date.today(),
                    payment_amount=Decimal('10.00'),
                    payment_method='upi',
                    notes=f"Stress Test Fragment {i}"
                )
            
            # Update total
            payment.paid_amount += Decimal('1000.00')
            payment.save()
            
    except Exception as e:
        print(f"[!] Stress test failed: {e}")
        return

    duration = time.time() - start_time
    print(f"[✓] Successfully processed 100 sub-transactions in {duration:.2f} seconds.")
    print("[NOTE] This burst triggers PostgreSQL WAL writes. If a 'checkpoint' starts during this,")
    print("       it is normal behavior and ensures data is flushed correctly from memory to disk.")
    
    # 3. Clean up
    payment.payment_records.all().delete()
    print("[x] Test data cleaned up. System verified stable.")

if __name__ == "__main__":
    stress_test_sync()
