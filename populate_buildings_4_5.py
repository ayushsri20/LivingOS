#!/usr/bin/env python
"""
Populate Buildings 4-5 with sample tenant data and 2-3 months of rent payments
"""
import os
import django
from datetime import datetime, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Room, Guest, MonthlyPayment, PaymentRecord, ElectricityBill

def populate_buildings_4_5():
    """Create sample entries for buildings 4-5 with 2-3 months of rent"""
    
    # Sample tenant data
    tenants_data = [
        # Building 4 (E)
        {'room': 'E-101', 'name': 'Rajesh Kumar', 'phone': '9876543210', 'months': 3},
        {'room': 'E-102', 'name': 'Priya Sharma', 'phone': '9876543211', 'months': 2},
        {'room': 'E-103', 'name': 'Amit Patel', 'phone': '9876543212', 'months': 3},
        {'room': 'E-104', 'name': 'Sneha Reddy', 'phone': '9876543213', 'months': 2},
        {'room': 'E-105', 'name': 'Vikram Singh', 'phone': '9876543214', 'months': 3},
        {'room': 'E-106', 'name': 'Anita Desai', 'phone': '9876543215', 'months': 2},
        
        # Building 5 (F)
        {'room': 'F-101', 'name': 'Suresh Iyer', 'phone': '9876543216', 'months': 3},
        {'room': 'F-102', 'name': 'Kavita Nair', 'phone': '9876543217', 'months': 2},
        {'room': 'F-103', 'name': 'Ravi Menon', 'phone': '9876543218', 'months': 3},
        {'room': 'F-104', 'name': 'Deepa Joshi', 'phone': '9876543219', 'months': 2},
        {'room': 'F-105', 'name': 'Arjun Rao', 'phone': '9876543220', 'months': 3},
        {'room': 'F-106', 'name': 'Meera Gupta', 'phone': '9876543221', 'months': 2},
    ]
    
    print("=" * 60)
    print("POPULATING BUILDINGS 4-5 WITH SAMPLE DATA")
    print("=" * 60)
    
    for tenant_info in tenants_data:
        room_number = tenant_info['room']
        
        try:
            # Get the room
            room = Room.objects.get(number=room_number)
            print(f"\n📍 Processing Room {room_number}")
            
            # Check if room already has an active tenant
            existing_guest = Guest.objects.filter(room=room, is_active=True).first()
            if existing_guest:
                print(f"   ⚠️  Room already occupied by {existing_guest.first_name} {existing_guest.last_name}")
                continue
            
            # Calculate check-in date based on number of months
            check_in_date = datetime.now().date() - timedelta(days=tenant_info['months'] * 30)
            
            # Create guest
            guest = Guest.objects.create(
                room=room,
                first_name=tenant_info['name'].split()[0],
                last_name=' '.join(tenant_info['name'].split()[1:]) if len(tenant_info['name'].split()) > 1 else '',
                phone=tenant_info['phone'],
                check_in_date=check_in_date,
                is_active=True
            )
            print(f"   ✅ Created tenant: {guest.full_name()}")
            
            # Create monthly payments and payment records for the specified months
            base_rent = Decimal('7000.00')
            
            for month_offset in range(tenant_info['months']):
                # Calculate the month (first day of each month)
                payment_month = (datetime.now().date().replace(day=1) - relativedelta(months=tenant_info['months'] - month_offset - 1))
                payment_date = payment_month + timedelta(days=5)  # Payment made on 5th of month
                
                # Create MonthlyPayment
                monthly_payment = MonthlyPayment.objects.create(
                    room=room,
                    guest=guest,
                    month=payment_month,
                    rent_amount=base_rent,
                    paid_amount=base_rent,
                    payment_status='paid',
                    paid_date=payment_date,
                    notes=f'Rent for {payment_month.strftime("%B %Y")}'
                )
                
                # Create PaymentRecord
                payment_record = PaymentRecord.objects.create(
                    monthly_payment=monthly_payment,
                    payment_date=payment_date,
                    payment_amount=base_rent,
                    payment_method='cash',
                    notes=f'Full rent payment for {payment_month.strftime("%B %Y")}'
                )
                
                print(f"   💰 Payment #{month_offset + 1}: ₹{base_rent} for {payment_month.strftime('%B %Y')}")
                
                # Create electricity bills
                initial_reading = 1000 + (int(room_number.split('-')[1]) * 100)
                previous_reading = initial_reading + (month_offset * 150)
                current_reading = previous_reading + 150
                units_consumed = current_reading - previous_reading
                rate_per_unit = Decimal('8.00')
                bill_amount = Decimal(str(units_consumed)) * rate_per_unit
                
                due_date = payment_month + timedelta(days=15)
                
                electricity_bill = ElectricityBill.objects.create(
                    room=room,
                    guest=guest,
                    month=payment_month,
                    starting_reading=Decimal(str(previous_reading)),
                    ending_reading=Decimal(str(current_reading)),
                    units_consumed=Decimal(str(units_consumed)),
                    rate_per_unit=rate_per_unit,
                    bill_amount=bill_amount,
                    paid_amount=bill_amount,
                    bill_status='paid',
                    due_date=due_date,
                    paid_date=payment_date
                )
                
                print(f"   ⚡ Bill #{month_offset + 1}: {units_consumed} units = ₹{bill_amount}")
            
        except Room.DoesNotExist:
            print(f"   ❌ Room {room_number} not found in database")
        except Exception as e:
            print(f"   ❌ Error processing room {room_number}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    # Count active tenants in buildings 4-5
    building_4_count = Guest.objects.filter(
        room__building__name='4',
        is_active=True
    ).count()
    building_5_count = Guest.objects.filter(
        room__building__name='5',
        is_active=True
    ).count()
    
    total_payments = MonthlyPayment.objects.filter(
        room__number__in=[f'{b}-{r}' for b in ['E', 'F'] for r in range(101, 107)]
    ).count()
    
    total_bills = ElectricityBill.objects.filter(
        room__number__in=[f'{b}-{r}' for b in ['E', 'F'] for r in range(101, 107)]
    ).count()
    
    print(f"Building 4: {building_4_count} active tenants")
    print(f"Building 5: {building_5_count} active tenants")
    print(f"Total Monthly Payments: {total_payments}")
    print(f"Total Electricity Bills: {total_bills}")
    print("=" * 60)

if __name__ == '__main__':
    populate_buildings_4_5()
