"""
Performance Dashboard Views
Handles all room collection, payment, and expense analytics
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.db.models import Sum, F, Case, When, DecimalField, Count
from django.utils import timezone
from datetime import date, datetime, timedelta
from decimal import Decimal

from .models import Building, Room, Guest, MonthlyPayment, PaymentRecord, ElectricityBill, MaintenanceExpense

def is_admin(user):
    """Check if user is admin"""
    return user.is_staff or user.is_superuser

@login_required(login_url='login')
@user_passes_test(is_admin)
def performance_dashboard(request):
    """
    Performance dashboard showing:
    - Total collection and expenses
    - Room-wise collection analysis
    - Payment status by room
    - Electricity bill tracking
    - Building complex summary
    """
    
    try:
        # Get all rooms
        all_rooms = Room.objects.select_related('building').all().order_by('building_id', 'number')
        total_rooms = all_rooms.count()
        occupied_room_ids = set(
            Guest.objects.filter(room__isnull=False, is_active=True)
            .values_list('room_id', flat=True)
            .distinct()
        )
        occupied_rooms = len(occupied_room_ids)
        
        # Calculate total collections
        total_collected = PaymentRecord.objects.aggregate(
            total=Sum('payment_amount', output_field=DecimalField())
        )['total'] or Decimal('0.00')
        
        # Get current month data
        today = date.today()
        current_month = date(today.year, today.month, 1)
        
        # Collection analysis by room
        room_collections = []
        # Use Decimal accumulators to avoid float rounding errors
        acc_expected_monthly = Decimal('0.00')
        acc_collected_this_month = Decimal('0.00')
        acc_pending_amount = Decimal('0.00')
        for room in all_rooms:
            guest = Guest.objects.filter(room=room, is_active=True).first()
            
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
                payment_status = monthly_payment.payment_status
                monthly_payment_id = monthly_payment.id
            else:
                collected = Decimal('0.00')
                payment_status = 'pending'
                monthly_payment_id = None
            rent = room.agreed_rent if room.agreed_rent is not None else room.price
            electricity = electricity_bill.bill_amount if electricity_bill else Decimal('0.00')
            monthly_expected = Decimal(str(rent)) + Decimal(str(electricity))
            if collected == 0:
                payment_status = 'pending'
            elif collected >= monthly_expected:
                payment_status = 'paid'
            else:
                payment_status = 'partial'
            pending = max(Decimal('0.00'), Decimal(str(monthly_expected)) - Decimal(str(collected)))
            
            # Calculate collection percentage
            if monthly_expected > 0:
                collection_percentage = int((collected / monthly_expected) * 100)
            else:
                collection_percentage = 0
            
            # Ensure percentage doesn't exceed 100
            collection_percentage = min(collection_percentage, 100)
            
            # update Decimal accumulators before converting to floats for the template
            acc_expected_monthly += Decimal(monthly_expected)
            acc_collected_this_month += Decimal(collected)
            acc_pending_amount += Decimal(pending)

            room_data = {
                'room_number': room.number,
                'room_type': room.get_room_type_display(),
                'guest_name': f"{guest.first_name} {guest.last_name}" if guest else "Vacant",
                'monthly_rent': float(monthly_expected),
                'collected': float(collected),
                'pending': float(pending),
                'collection_percentage': collection_percentage,
                'payment_status': payment_status,
                'monthly_payment_id': monthly_payment_id,
            }
            room_collections.append(room_data)
        
        # Calculate summary statistics
        total_expected_rent = acc_expected_monthly
        total_collected = acc_collected_this_month
        total_pending = acc_pending_amount
        
        # Occupancy rate
        occupancy_rate = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
        
        # Collection efficiency
        collection_efficiency = (total_collected / total_expected_rent * 100) if total_expected_rent > 0 else 0
        
        # Building occupancy breakdown
        building_occupancy = {
            building.name: sum(
                room.id in occupied_room_ids for room in all_rooms if room.building_id == building.id
            )
            for building in Building.objects.all()
        }

        # Prepare room_data for the detailed table
        room_data = []
        for rc in room_collections:
            room_data.append({
                'room_number': rc['room_number'],
                'room_type': rc['room_type'],
                'active_guest': rc['guest_name'],
                'price': rc['monthly_rent'],
                'expected': rc['monthly_rent'],
                'paid': rc['collected'],
                'balance': rc['pending'],
            })

        context = {
            'total_expected_rent': float(total_expected_rent),
            'total_collected': float(total_collected),
            'total_pending': float(total_pending),
            'collection_efficiency': float(collection_efficiency),
            'occupancy_rate': float(occupancy_rate),
            'building_occupancy': building_occupancy,
            'room_data': room_data,
            'electricity_bills': [], # Fallback for now
        }
        
        return render(request, 'performance_dashboard.html', context)
    
    except Exception as e:
        print(f"Error in performance_dashboard: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return with empty context on error
        context = {
            'kpis': {
                'total_collection': 0,
                'total_rooms': 0,
                'occupied_rooms': 0,
                'pending_amount': 0,
                'overdue_amount': 0,
                'total_bills': 0,
                'collection_efficiency': 0,
            },
            'summary': {
                'expected_monthly_collection': 0,
                'collected_this_month': 0,
            },
            'rooms': [],
            'bills': [],
            'meta': {
                'generated_at': datetime.now().isoformat(),
            },
            # Backwards compatibility
            'total_rooms': 0,
            'occupied_rooms': 0,
            'total_collection': 0,
            'pending_amount': 0,
            'overdue_amount': 0,
            'total_bills': 0,
            'room_collections': [],
            'expected_monthly_collection': 0,
            'collected_this_month': 0,
            'collection_efficiency': 0,
            'electricity_bills': [],
            'error': str(e),
        }
        return render(request, 'performance_dashboard.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def record_payment_from_dashboard(request):
    """Record payment from performance dashboard"""
    try:
        monthly_payment_id = request.POST.get('monthly_payment_id')
        payment_amount = request.POST.get('payment_amount')
        payment_method = request.POST.get('payment_method', 'cash')
        reference_number = request.POST.get('reference_number', '').strip()
        payment_date_str = request.POST.get('payment_date')
        notes = request.POST.get('notes', '').strip()
        
        # Validate inputs
        if not monthly_payment_id or not payment_amount:
            return JsonResponse({
                'success': False,
                'message': 'Monthly payment ID and amount are required'
            }, status=400)
        
        try:
            payment_amount = Decimal(payment_amount)
            if payment_amount <= 0:
                return JsonResponse({
                    'success': False,
                    'message': 'Payment amount must be greater than 0'
                }, status=400)
        except:
            return JsonResponse({
                'success': False,
                'message': 'Invalid payment amount'
            }, status=400)
        
        # Parse payment date
        try:
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        except:
            return JsonResponse({
                'success': False,
                'message': 'Invalid payment date format'
            }, status=400)
        
        # Get monthly payment
        monthly_payment = get_object_or_404(MonthlyPayment, id=monthly_payment_id)
        
        # Check if payment amount doesn't exceed remaining
        if payment_amount > monthly_payment.get_total_remaining():
            return JsonResponse({
                'success': False,
                'message': f'Payment amount exceeds remaining balance of ₹{monthly_payment.get_total_remaining()}'
            }, status=400)
        
        # Create payment record
        payment_record = PaymentRecord.objects.create(
            monthly_payment=monthly_payment,
            payment_date=payment_date,
            payment_amount=payment_amount,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            created_by=request.user
        )
        
        # Update monthly payment
        monthly_payment.paid_amount += payment_amount
        
        # Update payment status
        if monthly_payment.paid_amount >= monthly_payment.get_total_amount_due():
            monthly_payment.payment_status = 'paid'
            monthly_payment.paid_date = payment_date
        elif monthly_payment.paid_amount > 0:
            monthly_payment.payment_status = 'partial'
        
        monthly_payment.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Payment of ₹{payment_amount} recorded successfully',
            'payment_record_id': payment_record.id
        })
    
    except Exception as e:
        print(f"Error recording payment: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Error recording payment: {str(e)}'
        }, status=500)


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def record_bill_payment_from_dashboard(request):
    """Record electricity bill payment from performance dashboard"""
    try:
        bill_id = request.POST.get('bill_id')
        payment_amount = request.POST.get('bill_payment_amount')
        payment_date_str = request.POST.get('bill_payment_date')
        notes = request.POST.get('bill_notes', '').strip()
        
        # Validate inputs
        if not bill_id or not payment_amount:
            return JsonResponse({
                'success': False,
                'message': 'Bill ID and amount are required'
            }, status=400)
        
        try:
            payment_amount = Decimal(payment_amount)
            if payment_amount <= 0:
                return JsonResponse({
                    'success': False,
                    'message': 'Payment amount must be greater than 0'
                }, status=400)
        except:
            return JsonResponse({
                'success': False,
                'message': 'Invalid payment amount'
            }, status=400)
        
        # Parse payment date
        try:
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        except:
            return JsonResponse({
                'success': False,
                'message': 'Invalid payment date format'
            }, status=400)
        
        # Get electricity bill
        bill = get_object_or_404(ElectricityBill, id=bill_id)
        
        # Check if payment doesn't exceed remaining
        if payment_amount > bill.remaining_amount():
            return JsonResponse({
                'success': False,
                'message': f'Payment amount exceeds remaining balance of ₹{bill.remaining_amount()}'
            }, status=400)
        
        # Update bill payment
        bill.paid_amount += payment_amount
        
        # Update bill status
        if bill.paid_amount >= bill.bill_amount:
            bill.bill_status = 'paid'
            bill.paid_date = payment_date
        elif bill.paid_amount > 0:
            bill.bill_status = 'partial'
        
        bill.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Bill payment of ₹{payment_amount} recorded successfully'
        })
    
    except Exception as e:
        print(f"Error recording bill payment: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Error recording payment: {str(e)}'
        }, status=500)



@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def record_maintenance(request):
    """Record a maintenance expense from the performance dashboard"""
    try:
        building = request.POST.get('building_name') or request.POST.get('building') or ''
        category = request.POST.get('category', 'other')
        amount_raw = request.POST.get('amount') or request.POST.get('expense_amount')
        date_str = request.POST.get('date') or request.POST.get('expense_date')
        description = request.POST.get('description', '').strip()
        is_paid = request.POST.get('is_paid', 'true').lower() in ['true', '1', 'yes', 'on']

        if not building or not amount_raw or not date_str:
            return JsonResponse({'success': False, 'message': 'Building, amount and date are required'}, status=400)

        try:
            amount = Decimal(amount_raw)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid amount'}, status=400)

        try:
            exp_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid date format'}, status=400)

        expense = MaintenanceExpense.objects.create(
            building_name=building,
            category=category,
            amount=amount,
            date=exp_date,
            description=description,
            is_paid=is_paid,
        )

        return JsonResponse({'success': True, 'message': 'Maintenance expense recorded', 'expense_id': expense.id})

    except Exception as e:
        print(f"Error recording maintenance expense: {str(e)}")
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'}, status=500)
