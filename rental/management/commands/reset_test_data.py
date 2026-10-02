"""
Management command to reset tenant data and create realistic test entries
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
import random

from rental.models import Guest, Room, MonthlyPayment, PaymentRecord, ElectricityBill


class Command(BaseCommand):
    help = 'Archive all current tenants and create fresh test data'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('Starting data reset...'))
        
        # Delete all inactive/archived guests
        archived_count = Guest.objects.filter(is_active=False).delete()[0]
        self.stdout.write(self.style.SUCCESS(f'✓ Deleted {archived_count} archived tenants'))
        
        # Archive all active guests
        active_guests = Guest.objects.filter(is_active=True)
        count = active_guests.count()
        active_guests.update(is_active=False)
        self.stdout.write(self.style.SUCCESS(f'✓ Archived {count} active tenants'))
        
        # Delete the archived ones too to free up emails
        Guest.objects.filter(is_active=False).delete()
        self.stdout.write(self.style.SUCCESS('✓ Deleted all archived tenants to free up emails'))
        
        # Free up all occupied rooms
        Room.objects.filter(is_available=False).update(is_available=True)
        self.stdout.write(self.style.SUCCESS('✓ Freed all occupied rooms'))
        
        # Create realistic test tenants
        test_tenants = [
            {'first_name': 'Aman', 'last_name': 'Singh', 'phone': '9876543210', 
             'email': 'aman.singh@email.com', 'room': 'A-01', 'student_college': 'Delhi University'},
            {'first_name': 'Priya', 'last_name': 'Sharma', 'phone': '9876543211',
             'email': 'priya.sharma@email.com', 'room': 'A-02', 'student_college': 'Jamia Millia Islamia'},
            {'first_name': 'Rahul', 'last_name': 'Verma', 'phone': '9876543212',
             'email': 'rahul.verma@email.com', 'room': 'A-03', 'student_college': 'IIT Delhi'},
            {'first_name': 'Sneha', 'last_name': 'Gupta', 'phone': '9876543213',
             'email': 'sneha.gupta@email.com', 'room': 'B-01', 'student_college': 'Lady Shri Ram College'},
            {'first_name': 'Vikas', 'last_name': 'Kumar', 'phone': '9876543214',
             'email': 'vikas.kumar@email.com', 'room': 'B-02', 'student_college': 'Delhi Technological University'},
            {'first_name': 'Anjali', 'last_name': 'Reddy', 'phone': '9876543215',
             'email': 'anjali.reddy@email.com', 'room': 'B-03', 'student_college': 'Hansraj College'},
            {'first_name': 'Karan', 'last_name': 'Patel', 'phone': '9876543216',
             'email': 'karan.patel@email.com', 'room': 'C-01', 'student_college': 'SRCC'},
            {'first_name': 'Neha', 'last_name': 'Joshi', 'phone': '9876543217',
             'email': 'neha.joshi@email.com', 'room': 'C-02', 'student_college': 'Miranda House'}
        ]
        
        created_guests = []
        self.stdout.write(self.style.WARNING('\nCreating test tenants...'))
        
        for tenant_data in test_tenants:
            try:
                room = Room.objects.get(number=tenant_data['room'])
                
                # Create guest
                guest = Guest.objects.create(
                    first_name=tenant_data['first_name'],
                    last_name=tenant_data['last_name'],
                    phone=tenant_data['phone'],
                    email=tenant_data['email'],
                    room=room,
                    check_in_date=date.today() - timedelta(days=random.randint(30, 90)),
                    student_college=tenant_data.get('student_college', ''),
                    is_active=True
                )
                
                # Mark room as occupied
                room.is_available = False
                room.save()
                
                created_guests.append(guest)
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ Created: {guest.first_name} {guest.last_name} in Room {room.number}'
                ))
                
            except Room.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f'  ✗ Room {tenant_data["room"]} not found - skipping'
                ))
        
        # Create monthly payments for current month
        self.stdout.write(self.style.WARNING('\nCreating payment records...'))
        today = date.today()
        current_month = date(today.year, today.month, 1)
        
        # Delete existing payments for current month to avoid conflicts
        MonthlyPayment.objects.filter(month=current_month).delete()
        self.stdout.write(self.style.SUCCESS('  Cleared existing monthly payments'))
        
        for guest in created_guests:
            # Create monthly payment - prefer agreed_rent if set
            rent_amount = guest.room.agreed_rent if getattr(guest.room, 'agreed_rent', None) is not None else guest.room.price
            
            # Randomly decide payment status
            payment_scenarios = ['full', 'partial', 'pending']
            scenario = random.choice(payment_scenarios)
            
            if scenario == 'full':
                paid_amount = rent_amount
                status = 'paid'
            elif scenario == 'partial':
                paid_amount = rent_amount * Decimal('0.5')  # 50% paid
                status = 'partial'
            else:
                paid_amount = Decimal('0.00')
                status = 'pending'
            
            monthly_payment = MonthlyPayment.objects.create(
                room=guest.room,
                month=current_month,
                rent_amount=rent_amount,
                paid_amount=paid_amount,
                payment_status=status
            )
            
            # If payment was made, create payment record
            if paid_amount > 0:
                PaymentRecord.objects.create(
                    monthly_payment=monthly_payment,
                    payment_amount=paid_amount,
                    payment_date=today,
                    payment_method='upi',
                    reference_number=f'UPI/{random.randint(10000, 99999)}'
                )
            
            status_emoji = '✓' if status == 'paid' else '½' if status == 'partial' else '✗'
            self.stdout.write(self.style.SUCCESS(
                f'  {status_emoji} Payment for {guest.first_name} - Room {guest.room.number}: ₹{paid_amount}/{rent_amount}'
            ))
        
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Test data created successfully!'))
        self.stdout.write(self.style.SUCCESS(f'  - {len(created_guests)} tenants registered'))
        self.stdout.write(self.style.SUCCESS(f'  - {len(created_guests)} monthly payments created'))
        self.stdout.write(self.style.SUCCESS(f'\n🌐 Access the app at: http://127.0.0.1:8080/'))
