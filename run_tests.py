#!/usr/bin/env python3
"""
Comprehensive Test Suite for Hotel Rental Management System
Tests all critical workflows, data integrity, and user experience
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/Users/ayush/hotel_rental/hotel_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from rental.models import Room, Guest, MonthlyPayment, ElectricityBill, PaymentRecord
from datetime import date, timedelta
from decimal import Decimal
import json

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test_name, message=""):
        self.passed.append(f"✅ {test_name}: {message}")
    
    def add_fail(self, test_name, message=""):
        self.failed.append(f"❌ {test_name}: {message}")
    
    def add_warning(self, test_name, message=""):
        self.warnings.append(f"⚠️  {test_name}: {message}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("TEST RESULTS SUMMARY")
        print("="*80)
        
        if self.passed:
            print(f"\n✅ PASSED ({len(self.passed)} tests):")
            for p in self.passed:
                print(f"  {p}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)} items):")
            for w in self.warnings:
                print(f"  {w}")
        
        if self.failed:
            print(f"\n❌ FAILED ({len(self.failed)} tests):")
            for f in self.failed:
                print(f"  {f}")
        
        print("\n" + "="*80)
        total = len(self.passed) + len(self.failed)
        pass_rate = (len(self.passed) / total * 100) if total > 0 else 0
        print(f"OVERALL: {len(self.passed)}/{total} tests passed ({pass_rate:.1f}%)")
        print("="*80 + "\n")

results = TestResults()

def test_database_connectivity():
    """Test 1: Database Connection"""
    try:
        room_count = Room.objects.count()
        results.add_pass("Database Connectivity", f"{room_count} rooms found")
        return True
    except Exception as e:
        results.add_fail("Database Connectivity", str(e))
        return False

def test_data_integrity():
    """Test 2: Data Integrity - No orphaned records"""
    try:
        # Check for monthly payments without rooms
        orphaned_payments = MonthlyPayment.objects.filter(room__isnull=True).count()
        if orphaned_payments > 0:
            results.add_fail("Data Integrity - Payments", f"{orphaned_payments} orphaned payment records")
        else:
            results.add_pass("Data Integrity - Payments", "No orphaned payment records")
        
        # Check for electricity bills without rooms
        orphaned_bills = ElectricityBill.objects.filter(room__isnull=True).count()
        if orphaned_bills > 0:
            results.add_fail("Data Integrity - Bills", f"{orphaned_bills} orphaned electricity bills")
        else:
            results.add_pass("Data Integrity - Bills", "No orphaned electricity bills")
        
        # Check for payment records without monthly payments
        orphaned_records = PaymentRecord.objects.filter(monthly_payment__isnull=True).count()
        if orphaned_records > 0:
            results.add_fail("Data Integrity - Records", f"{orphaned_records} orphaned payment records")
        else:
            results.add_pass("Data Integrity - Records", "No orphaned payment records")
        
        return True
    except Exception as e:
        results.add_fail("Data Integrity Check", str(e))
        return False

def test_active_tenant_logic():
    """Test 3: Active Tenant Logic - Only one active tenant per room"""
    try:
        rooms_with_multiple_active = []
        for room in Room.objects.all():
            active_tenants = Guest.objects.filter(room=room, is_active=True).count()
            if active_tenants > 1:
                rooms_with_multiple_active.append(f"Room {room.number}: {active_tenants} active tenants")
        
        if rooms_with_multiple_active:
            results.add_fail("Active Tenant Logic", f"Multiple active tenants: {', '.join(rooms_with_multiple_active)}")
        else:
            results.add_pass("Active Tenant Logic", "Each room has at most one active tenant")
        
        return len(rooms_with_multiple_active) == 0
    except Exception as e:
        results.add_fail("Active Tenant Logic", str(e))
        return False

def test_monthly_payment_calculation():
    """Test 4: Monthly Payment Calculation - Total = Rent + Electricity"""
    try:
        errors = []
        current_month = date.today().replace(day=1)
        
        payments = MonthlyPayment.objects.filter(month=current_month)[:10]
        
        for payment in payments:
            electricity_amount = payment.get_electricity_amount()
            total_due = payment.get_total_amount_due()
            expected_total = payment.rent_amount + electricity_amount
            
            if total_due != expected_total:
                errors.append(f"Room {payment.room.number}: Total={total_due}, Expected={expected_total}")
        
        if errors:
            results.add_fail("Payment Calculation", f"Calculation errors: {'; '.join(errors)}")
        else:
            results.add_pass("Payment Calculation", f"Checked {len(payments)} payments - all calculations correct")
        
        return len(errors) == 0
    except Exception as e:
        results.add_fail("Payment Calculation", str(e))
        return False

def test_payment_status_logic():
    """Test 5: Payment Status Logic"""
    try:
        errors = []
        payments = MonthlyPayment.objects.all()[:20]
        
        for payment in payments:
            total_due = payment.get_total_amount_due()
            paid = payment.paid_amount
            status = payment.payment_status
            
            # Check status logic
            if paid >= total_due and status != 'paid':
                errors.append(f"Room {payment.room.number}: Fully paid but status is '{status}'")
            elif paid > 0 and paid < total_due and status not in ['partial', 'paid']:
                errors.append(f"Room {payment.room.number}: Partially paid but status is '{status}'")
            elif paid == 0 and status not in ['pending', 'overdue']:
                errors.append(f"Room {payment.room.number}: No payment but status is '{status}'")
        
        if errors:
            results.add_fail("Payment Status Logic", f"Status errors: {'; '.join(errors[:3])}")
        else:
            results.add_pass("Payment Status Logic", f"Checked {len(payments)} payments - all statuses correct")
        
        return len(errors) == 0
    except Exception as e:
        results.add_fail("Payment Status Logic", str(e))
        return False

def test_electricity_bill_calculation():
    """Test 6: Electricity Bill Calculation"""
    try:
        errors = []
        bills = ElectricityBill.objects.all()[:10]
        
        for bill in bills:
            units = bill.ending_reading - bill.starting_reading
            expected_amount = units * bill.rate_per_unit
            
            if abs(bill.bill_amount - expected_amount) > Decimal('0.01'):
                errors.append(f"Room {bill.room.number}: Bill={bill.bill_amount}, Expected={expected_amount}")
            
            if bill.ending_reading < bill.starting_reading:
                errors.append(f"Room {bill.room.number}: Ending reading < Starting reading")
        
        if errors:
            results.add_fail("Electricity Calculation", f"Errors: {'; '.join(errors)}")
        else:
            results.add_pass("Electricity Calculation", f"Checked {len(bills)} bills - all calculations correct")
        
        return len(errors) == 0
    except Exception as e:
        results.add_fail("Electricity Calculation", str(e))
        return False

def test_page_accessibility():
    """Test 7: Page Accessibility"""
    try:
        client = Client()
        
        # Create test user
        user, created = User.objects.get_or_create(
            username='testadmin',
            defaults={'is_staff': True, 'is_superuser': True}
        )
        if created:
            user.set_password('testpass')
            user.save()
        
        # Login
        login_success = client.login(username='testadmin', password='testpass')
        if not login_success:
            results.add_fail("Page Accessibility", "Login failed")
            return False
        
        # Test critical pages
        pages = {
            '/dashboard/': 'Dashboard',
            '/manage-payments/': 'Payment Management',
            '/manage-electricity-bills/': 'Electricity Bills',
            '/manage-guests/': 'Tenant Management',
            '/performance/': 'Performance Dashboard'
        }
        
        all_accessible = True
        for url, name in pages.items():
            response = client.get(url)
            if response.status_code == 200:
                results.add_pass(f"Page: {name}", f"Accessible (200)")
            else:
                results.add_fail(f"Page: {name}", f"Status {response.status_code}")
                all_accessible = False
        
        return all_accessible
    except Exception as e:
        results.add_fail("Page Accessibility", str(e))
        return False

def test_api_endpoints():
    """Test 8: API Endpoints"""
    try:
        client = Client()
        user = User.objects.filter(is_superuser=True).first()
        client.force_login(user)
        
        current_month = date.today().replace(day=1).strftime('%Y-%m-%d')
        
        endpoints = {
            f'/api/payments/by-month/?month={current_month}': 'Payments by Month',
            '/api/room/1/payment-history/': 'Payment History',
        }
        
        all_working = True
        for url, name in endpoints.items():
            try:
                response = client.get(url)
                data = response.json()
                if response.status_code == 200 or (response.status_code == 404 and 'not found' in str(data).lower()):
                    results.add_pass(f"API: {name}", "Working")
                else:
                    results.add_fail(f"API: {name}", f"Status {response.status_code}")
                    all_working = False
            except Exception as e:
                results.add_fail(f"API: {name}", str(e))
                all_working = False
        
        return all_working
    except Exception as e:
        results.add_fail("API Endpoints", str(e))
        return False

def test_tenant_checkin_checkout_data():
    """Test 9: Tenant Check-in/Check-out Data Integrity"""
    try:
        # Check for guests with invalid dates
        invalid_guests = []
        
        for guest in Guest.objects.all()[:50]:
            if guest.check_out_date and guest.check_in_date:
                if guest.check_out_date < guest.check_in_date:
                    invalid_guests.append(f"{guest.full_name}: Check-out before check-in")
            
            # Active guests should not have check-out dates in the past
            if guest.is_active and guest.check_out_date:
                if guest.check_out_date < date.today():
                    invalid_guests.append(f"{guest.full_name}: Active but check-out date passed")
        
        if invalid_guests:
            results.add_fail("Tenant Date Logic", f"Issues: {'; '.join(invalid_guests[:3])}")
        else:
            results.add_pass("Tenant Date Logic", "All tenant dates are valid")
        
        return len(invalid_guests) == 0
    except Exception as e:
        results.add_fail("Tenant Date Logic", str(e))
        return False

def test_duplicate_monthly_payments():
    """Test 10: No Duplicate Monthly Payments"""
    try:
        from django.db.models import Count
        
        duplicates = MonthlyPayment.objects.values('room', 'month').annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        if duplicates.exists():
            dup_list = [f"Room {d['room']}, Month {d['month']}: {d['count']} records" for d in duplicates[:3]]
            results.add_fail("Duplicate Payments", f"Found duplicates: {'; '.join(dup_list)}")
            return False
        else:
            results.add_pass("Duplicate Payments", "No duplicate monthly payments")
            return True
    except Exception as e:
        results.add_fail("Duplicate Payments", str(e))
        return False

def test_payment_record_totals():
    """Test 11: Payment Record Totals Match Monthly Payment"""
    try:
        from django.db.models import Sum
        
        errors = []
        payments = MonthlyPayment.objects.all()[:20]
        
        for payment in payments:
            # Sum all payment records
            total_recorded = PaymentRecord.objects.filter(
                monthly_payment=payment
            ).aggregate(total=Sum('payment_amount'))['total'] or Decimal('0.00')
            
            # Should match paid_amount
            if abs(total_recorded - payment.paid_amount) > Decimal('0.01'):
                errors.append(f"Room {payment.room.number}: Records={total_recorded}, Paid={payment.paid_amount}")
        
        if errors:
            results.add_fail("Payment Record Totals", f"Mismatches: {'; '.join(errors[:3])}")
        else:
            results.add_pass("Payment Record Totals", f"Checked {len(payments)} payments - all totals match")
        
        return len(errors) == 0
    except Exception as e:
        results.add_fail("Payment Record Totals", str(e))
        return False

def test_room_availability():
    """Test 12: Room Availability Logic"""
    try:
        warnings = []
        
        for room in Room.objects.all():
            active_tenants = Guest.objects.filter(room=room, is_active=True).count()
            
            # Room should have 0 or 1 active tenant
            if active_tenants > 1:
                warnings.append(f"Room {room.number}: {active_tenants} active tenants")
        
        if warnings:
            results.add_warning("Room Availability", f"Issues: {'; '.join(warnings[:5])}")
        else:
            results.add_pass("Room Availability", "All rooms have valid tenant assignments")
        
        return True
    except Exception as e:
        results.add_fail("Room Availability", str(e))
        return False

def main():
    print("\n" + "="*80)
    print("HOTEL RENTAL MANAGEMENT SYSTEM - COMPREHENSIVE TEST SUITE")
    print("="*80 + "\n")
    
    print("Running tests...\n")
    
    # Run all tests
    test_database_connectivity()
    test_data_integrity()
    test_active_tenant_logic()
    test_monthly_payment_calculation()
    test_payment_status_logic()
    test_electricity_bill_calculation()
    test_page_accessibility()
    test_api_endpoints()
    test_tenant_checkin_checkout_data()
    test_duplicate_monthly_payments()
    test_payment_record_totals()
    test_room_availability()
    
    # Print summary
    results.print_summary()
    
    # Return exit code
    return 0 if len(results.failed) == 0 else 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
