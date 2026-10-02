#!/usr/bin/env python
"""
Create payment records for monthly payments that are marked as paid but have no records
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import MonthlyPayment, PaymentRecord

def backfill_payment_records():
    """Create PaymentRecord entries for MonthlyPayments that have no records"""
    
    print("=" * 60)
    print("BACKFILLING PAYMENT RECORDS")
    print("=" * 60)
    
    # Find monthly payments with no payment records
    orphaned_payments = MonthlyPayment.objects.filter(
        payment_records__isnull=True
    ).order_by('room__number', 'month')
    
    print(f"\nFound {orphaned_payments.count()} monthly payments without payment records\n")
    
    created_count = 0
    
    for payment in orphaned_payments:
        print(f"📍 Room {payment.room.number} - {payment.month.strftime('%B %Y')}")
        print(f"   Status: {payment.payment_status}")
        print(f"   Rent: ₹{payment.rent_amount}, Paid: ₹{payment.paid_amount}")
        
        # Only create payment record if some amount was paid
        if payment.paid_amount > 0:
            PaymentRecord.objects.create(
                monthly_payment=payment,
                payment_date=payment.paid_date or payment.month,
                payment_amount=payment.paid_amount,
                payment_method='cash',  # Default assumption
                notes='Backfilled payment record - original payment method unknown'
            )
            print(f"   ✅ Created payment record for ₹{payment.paid_amount}")
            created_count += 1
        else:
            print(f"   ⏭️  Skipped (no payment made yet)")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Payment Records Created: {created_count}")
    print(f"Payments Skipped: {orphaned_payments.count() - created_count}")
    print("=" * 60)

if __name__ == '__main__':
    backfill_payment_records()
