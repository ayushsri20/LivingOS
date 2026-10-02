"""
Dashboard Metrics API Endpoint
Returns real-time metrics for Analytics Hub auto-refresh
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.db.models import Sum, F, Case, When, DecimalField, Count
from django.utils import timezone
from datetime import date, datetime, timedelta
from decimal import Decimal

from .models import Room, Guest, MonthlyPayment, PaymentRecord, ElectricityBill, MaintenanceExpense

def is_admin(user):
    """Check if user is admin"""
    return user.is_staff or user.is_superuser

@login_required(login_url='login')
def dashboard_metrics_api(request):
    """
    Lightweight API endpoint that returns dashboard metrics for real-time updates.
    Returns: Expected Yield, Realized Revenue, Accounts Receivable, Collection Efficiency
    """
    try:
        # Get all rooms
        all_rooms = Room.objects.all()
        total_rooms = all_rooms.count()
        occupied_rooms = Guest.objects.filter(
            room__isnull=False,
            is_active=True,
        ).values('room_id').distinct().count()
        
        # Get current month data
        today = date.today()
        current_month = date(today.year, today.month, 1)
        
        # Calculate metrics using Decimal for precision
        acc_expected_monthly = Decimal('0.00')
        acc_collected_this_month = Decimal('0.00')
        acc_pending_amount = Decimal('0.00')
        
        for room in all_rooms:
            # Get monthly payment for current month
            monthly_payment = MonthlyPayment.objects.filter(
                room=room,
                month=current_month
            ).first()
            electricity_bill = ElectricityBill.objects.filter(
                room=room,
                month=current_month,
            ).first()

            if monthly_payment:
                collected = monthly_payment.paid_amount
            else:
                collected = Decimal('0.00')
            rent = room.agreed_rent if room.agreed_rent is not None else room.price
            electricity = electricity_bill.bill_amount if electricity_bill else Decimal('0.00')
            expected = Decimal(str(rent)) + Decimal(str(electricity))
            pending = max(Decimal('0.00'), Decimal(str(expected)) - Decimal(str(collected)))

            # Accumulate totals
            acc_expected_monthly += Decimal(expected)
            acc_collected_this_month += Decimal(collected)
            acc_pending_amount += Decimal(pending)
        
        # Calculate derived metrics
        total_expected_rent = acc_expected_monthly
        total_collected = acc_collected_this_month
        total_pending = acc_pending_amount
        
        # Occupancy rate
        occupancy_rate = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
        
        # Collection efficiency
        collection_efficiency = (total_collected / total_expected_rent * 100) if total_expected_rent > 0 else 0
        
        # Return JSON response
        return JsonResponse({
            'success': True,
            'metrics': {
                'expected_yield': float(total_expected_rent),
                'realized_revenue': float(total_collected),
                'accounts_receivable': float(total_pending),
                'collection_efficiency': float(collection_efficiency),
                'occupancy_rate': float(occupancy_rate),
            },
            'meta': {
                'total_rooms': total_rooms,
                'occupied_rooms': occupied_rooms,
                'last_updated': datetime.now().isoformat(),
            }
        })
    
    except Exception as e:
        print(f"Error in dashboard_metrics_api: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return JsonResponse({
            'success': False,
            'message': f'Error fetching metrics: {str(e)}'
        }, status=500)
