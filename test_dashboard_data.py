#!/usr/bin/env python
"""
Test dashboard functionality and check for bugs
"""
import os
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Room, Guest, MonthlyPayment, PaymentRecord, ElectricityBill

def test_dashboard_data():
    """Test the data that would be displayed on the dashboard"""
    
    print("=" * 60)
    print("DASHBOARD DATA VERIFICATION")
    print("=" * 60)
    
    # Test Buildings E and F
    for building_letter, building_name in [('E', 'Building 4'), ('F', 'Building 5')]:
        print(f"\n{building_name} ({building_letter}):")
        print("-" * 40)
        
        rooms = Room.objects.filter(number__startswith=f'{building_letter}-').order_by('number')
        
        for room in rooms:
            print(f"\n  Room {room.number}:")
            
            # Get active tenants
            active_guests = Guest.objects.filter(room=room, is_active=True)
            
            if active_guests.exists():
                for guest in active_guests:
                    print(f"    👤 Tenant: {guest.full_name}")
                    print(f"       Phone: {guest.phone}")
                    print(f"       Check-in: {guest.check_in_date}")
                    
                    # Get payment records
                    monthly_payments = MonthlyPayment.objects.filter(guest=guest).order_by('-month')
                    print(f"       Payments: {monthly_payments.count()} months")
                    
                    for payment in monthly_payments[:3]:  # Show last 3 months
                        print(f"         • {payment.month.strftime('%B %Y')}: ₹{payment.rent_amount} ({payment.payment_status})")
                    
                    # Get electricity bills
                    elec_bills = ElectricityBill.objects.filter(guest=guest).order_by('-month')
                    print(f"       Electricity Bills: {elec_bills.count()} months")
                    
                    for bill in elec_bills[:3]:  # Show last 3 months
                        print(f"         • {bill.month.strftime('%B %Y')}: {bill.units_consumed} units = ₹{bill.bill_amount} ({bill.bill_status})")
            else:
                print(f"    ⚪ Vacant")
    
    print("\n" + "=" * 60)
    print("POTENTIAL BUGS CHECK")
    print("=" * 60)
    
    # Check for common issues
    bugs_found = []
    
    # Bug 1: Guests without monthly payments
    guests_without_payments = Guest.objects.filter(is_active=True, monthly_payments__isnull=True).distinct()
    if guests_without_payments.exists():
        bugs_found.append(f"⚠️  {guests_without_payments.count()} active guests have no monthly payments")
        for guest in guests_without_payments:
            print(f"    - {guest.full_name} in Room {guest.room.number}")
    
    # Bug 2: Guests without electricity bills
    guests_without_bills = Guest.objects.filter(is_active=True, electricity_bills__isnull=True).distinct()
    if guests_without_bills.exists():
        bugs_found.append(f"⚠️  {guests_without_bills.count()} active guests have no electricity bills")
        for guest in guests_without_bills:
            print(f"    - {guest.full_name} in Room {guest.room.number}")
    
    # Bug 3: Monthly payments without payment records
    payments_without_records = MonthlyPayment.objects.filter(payment_records__isnull=True)
    if payments_without_records.exists():
        bugs_found.append(f"⚠️  {payments_without_records.count()} monthly payments have no payment records")
    
    # Bug 4: Rooms with more than 2 active tenants
    from django.db.models import Count
    overcrowded_rooms = Room.objects.annotate(
        active_count=Count('guest', filter=django.db.models.Q(guest__is_active=True))
    ).filter(active_count__gt=2)
    
    if overcrowded_rooms.exists():
        bugs_found.append(f"⚠️  {overcrowded_rooms.count()} rooms have more than 2 active tenants")
        for room in overcrowded_rooms:
            print(f"    - Room {room.number} has {room.guest_set.filter(is_active=True).count()} tenants")
    
    # Bug 5: Negative balances
    negative_balances = MonthlyPayment.objects.filter(paid_amount__gt=django.db.models.F('rent_amount'))
    if negative_balances.exists():
        bugs_found.append(f"⚠️  {negative_balances.count()} payments have paid more than rent amount")
    
    if not bugs_found:
        print("\n✅ No obvious bugs found in the data!")
    else:
        print(f"\n❌ Found {len(bugs_found)} potential issues:")
        for bug in bugs_found:
            print(f"   {bug}")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    test_dashboard_data()
