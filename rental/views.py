from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.contrib.auth.models import User
import json
from django.db import transaction
from django.db.models import Sum, Q, Avg
from .models import Building, Room, Booking, Guest, MonthlyPayment, PaymentRecord, ElectricityBill
from collections import defaultdict
from datetime import datetime
from django.utils import timezone
from decimal import Decimal
import json

import logging
import re

logger = logging.getLogger(__name__)

def is_admin(user):
    return user.is_staff or user.is_superuser


def _configured_electricity_rate():
    return Decimal(str(settings.ELECTRICITY_RATE_PER_UNIT))


def _requested_electricity_rate_matches_configured(requested_rate):
    if requested_rate in (None, ''):
        return True
    try:
        return Decimal(str(requested_rate)) == _configured_electricity_rate()
    except (ArithmeticError, TypeError, ValueError):
        return False


def home(request):
    return render(request, 'home.html')

def health_check(request):
    return JsonResponse({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@require_http_methods(["GET", "POST"])
def login_view(request):
    """Handle user login with proper session management"""
    # If user is already logged in, redirect to dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            from django.db import connection
            import os
            from django.conf import settings
            
            db_path = settings.DATABASES['default'].get('NAME', 'N/A')
            exists = os.path.exists(db_path) if isinstance(db_path, str) else False
            size = os.path.getsize(db_path) if exists else 0
            cwd = os.getcwd()
            
            try:
                tables = connection.introspection.table_names()
                logger.info(f"DB LOGIN DIAGNOSTIC: Path: {db_path}, Exists: {exists}, Size: {size}, CWD: {cwd}, Tables: {tables}")
            except Exception as diag_err:
                logger.warning(f"DB DIAGNOSTIC FAILED: {diag_err}")
            
            user = authenticate(request, username=username, password=password)
        except Exception as db_err:
            logger.error(f"DB AUTH ERROR: {db_err}")
            migrate_log = "N/A"
            if os.path.exists("migrate_log.txt"):
                try:
                    with open("migrate_log.txt", "r") as f:
                        migrate_log = f.read()
                except:
                    migrate_log = "Error reading log"
            
            diag_str = f"Error: {db_err}. Path: {db_path}, Exists: {exists}, Size: {size}, CWD: {cwd}, Tables: {tables[:5] if 'tables' in locals() else 'N/A'}, Migrate: {migrate_log[-200:] if migrate_log else 'Empty'}"
            return render(request, 'login.html', {'error': f'Database connection error: {diag_str}'})
        
        if user is not None:
            # Clear any existing session data
            request.session.flush()
            
            # Login user (creates new session)
            login(request, user)
            
            # Regenerate session key for security
            request.session.cycle_key()
            
            # Set session expiry (optional - 2 weeks)
            if not request.POST.get('remember_me'):
                request.session.set_expiry(0)  # Session expires when browser closes
            else:
                request.session.set_expiry(1209600)  # 2 weeks
            
            logger.info(f"User {username} logged in successfully")
            return redirect('dashboard')
        else:
            context = {'error': 'Invalid username or password'}
            return render(request, 'login.html', context)
    
    return render(request, 'login.html')

def logout_view(request):
    """Logout user and clear all session data"""
    from django.contrib import messages
    
    # Clear session before logout
    request.session.flush()
    
    # Perform logout
    logout(request)
    
    # Add success message
    messages.success(request, 'You have been successfully logged out.')
    
    # Redirect to home with a fresh session
    response = redirect('home')
    
    # Clear any cached authentication
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response

@login_required(login_url='login')
def dashboard(request):
    try:
        rooms = Room.objects.select_related('building').all()
        bookings = Booking.objects.all()
        guests = Guest.objects.filter(is_active=True)
        
        # Fetch all active guests and map them to rooms
        active_guests = Guest.objects.filter(is_active=True).select_related('room')
        room_tenants = defaultdict(list)
        for guest in active_guests:
            if guest.room:
                room_tenants[guest.room.id].append(guest)
                
        
        # Enrich rooms with tenant data and calculate status
        for room in rooms:
            tenants = room_tenants.get(room.id, [])
            room.current_tenants = tenants
            
            # Determine occupancy status and color
            # Use database capacity and model properties
            count = len(tenants)
            if count == 0:
                room.occupancy_status = 'empty'
                room.status_color = 'green'  # Green for empty
                room.status_text = 'Available'
                room.status_badge = 'success'
            elif count < room.capacity:
                room.occupancy_status = 'partial'
                room.status_color = 'yellow'  # Yellow for partial
                room.status_text = f'Partial ({count}/{room.capacity})'
                room.status_badge = 'warning'
            else:
                room.occupancy_status = 'full'
                room.status_color = 'red'  # Red for full
                room.status_text = f'Full ({count}/{room.capacity})'
                room.status_badge = 'danger'
                
        # Group rooms by building
        buildings = defaultdict(list)
        for room in rooms:
            building_name = room.building.name
            buildings[building_name].append(room)
        
        mapped_buildings = []
        for building in Building.objects.all():
            building_rooms = buildings.get(building.name, [])
            mapped_buildings.append({
                'name': building.name,
                'rooms': building_rooms,
                'occupied_count': sum(bool(room.current_tenants) for room in building_rooms),
            })
        
        # Calculate active stats
        active_rooms_count = Guest.objects.filter(room__isnull=False, is_active=True).values('room_id').distinct().count()
        occupancy_rate = (active_rooms_count / rooms.count() * 100) if rooms.count() > 0 else 0
        
        context = {
            'total_rooms': rooms.count(),
            'available_rooms': rooms.filter(is_available=True).count(),
            'booked_rooms': active_rooms_count,
            'active_rooms_count': active_rooms_count,
            'occupancy_rate': round(occupancy_rate, 1),
            'active_bookings': bookings.filter(is_active=True).count(),
            'total_bookings': bookings.count(),
            'all_bookings': bookings[:5],
            'total_guests': guests.count(),
            'buildings': mapped_buildings,
            'is_admin': request.user.is_staff or request.user.is_superuser,
        }
        
        return render(request, 'dashboard.html', context)
    except Exception as e:
        logger.error(f"Error in dashboard: {e}", exc_info=True)
        return render(request, 'dashboard.html', {'error': str(e), 'total_rooms': 0, 'active_rooms_count': 0})

@login_required(login_url='login')
@user_passes_test(is_admin)
def manage_buildings(request):
    rooms = Room.objects.select_related('building').all().order_by('building_id', 'number')
    
    # Group rooms by building
    buildings = defaultdict(list)
    for room in rooms:
        building_name = room.building.name
        buildings[building_name].append(room)
    
    mapped_buildings = [
        (building.name, buildings[building.name])
        for building in Building.objects.all()
        if building.name in buildings
    ]
    
    context = {
        'buildings': mapped_buildings,
        'room_types': Room.ROOM_TYPES,
    }
    
    return render(request, 'rooms.html', context)

def get_available_rooms_for_allocation(exclude_guest_id=None):
    """
    Returns rooms available for tenant allocation with intelligent sorting.
    
    Filters:
    - is_available = True (manual override)
    - current_occupancy < MAX_CAPACITY (2)
    - Excludes the current guest's room if editing
    
    Sorting:
    - Partially filled rooms first (better for roommate pairing)
    - Then empty rooms
    - Ordered by room number within each group
    
    Args:
        exclude_guest_id: If provided, always include the guest's current room
    
    Returns:
        QuerySet of available rooms
    """
    from django.db.models import Count, Case, When, IntegerField
    
    # Base filter: manually available and not full
    available_rooms = Room.objects.filter(
        is_available=True
    ).annotate(
        active_tenant_count=Count(
            'guest',
            filter=Q(guest__is_active=True)
        )
    ).filter(
        active_tenant_count__lt=Room.MAX_CAPACITY
    )
    
    # If editing a guest, include their current room even if full
    if exclude_guest_id:
        try:
            guest = Guest.objects.get(id=exclude_guest_id)
            if guest.room:
                available_rooms = Room.objects.filter(
                    Q(id__in=available_rooms.values_list('id', flat=True)) |
                    Q(id=guest.room.id)
                ).annotate(
                    active_tenant_count=Count(
                        'guest',
                        filter=Q(guest__is_active=True)
                    )
                )
        except Guest.DoesNotExist:
            pass
    
    # Sort: partially filled first, then empty, then by room number
    available_rooms = available_rooms.annotate(
        sort_priority=Case(
            When(active_tenant_count=1, then=0),  # Partially filled (priority)
            When(active_tenant_count=0, then=1),  # Empty
            default=2,
            output_field=IntegerField()
        )
    ).order_by('sort_priority', 'number')
    
    return available_rooms

@login_required(login_url='login')
@user_passes_test(is_admin)
def manage_guests(request):
    """Manage guest information with structured data"""
    guests = Guest.objects.all().order_by('-created_at')
    rooms = Room.objects.select_related('building').all().order_by('number')
    
    # Get guest statistics
    guest_stats = {
        'total': guests.count(),
        'active': guests.filter(is_active=True).count(),
        'inactive': guests.filter(is_active=False).count(),
        'with_room': guests.filter(room__isnull=False).count(),
        'without_room': guests.filter(room__isnull=True).count(),
    }
    
    buildings = [
        {'prefix': building.name, 'name': building.name}
        for building in Building.objects.all()
    ]
    
    # Prepare rich room data for JS filtering
    rooms_data = []
    for r in rooms:
        rooms_data.append({
            'id': r.id,
            'number': r.number,
            'building': r.building.name,
            'type': r.room_type,
            'capacity': r.capacity,
            'occupancy': r.current_occupancy,
            'is_full': r.is_full,
            'tenants': [{'id': t.id, 'name': t.full_name} for t in r.get_active_tenants()]
        })

    context = {
        'guests': guests,
        'rooms': rooms,
        'rooms_data': json.dumps(rooms_data), # JSON for JS
        'available_rooms': get_available_rooms_for_allocation(),  # Use enhanced filtering
        'guest_stats': guest_stats,
        'buildings': buildings,  # Dynamic building list for filters
    }
    
    return render(request, 'manage_guests_v2.html', context)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def update_room(request, room_id):
    try:
        room = get_object_or_404(Room, id=room_id)
        
        # Allow updating room number (unique), room type, price and agreed_rent
        new_number = request.POST.get('number', None)
        if new_number and new_number != room.number:
            # Validate uniqueness
            if Room.objects.filter(number=new_number).exclude(id=room.id).exists():
                return JsonResponse({'success': False, 'message': f'Room number {new_number} already exists'}, status=400)
            room.number = new_number

        room.room_type = request.POST.get('room_type', room.room_type)
        room.capacity = int(request.POST.get('capacity', room.capacity))
        # Support per-room negotiated rent (agreed_rent). If provided, persist it.
        room.price = float(request.POST.get('price', room.price))
        agreed_val = request.POST.get('agreed_rent', None)
        if agreed_val is not None and agreed_val != '':
            try:
                room.agreed_rent = float(agreed_val)
            except ValueError:
                pass
        room.is_available = request.POST.get('is_available') == 'true'
        room.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Room {room.number} updated successfully',
                'room': {
                'id': room.id,
                'number': room.number,
                'room_type': room.room_type,
                'capacity': room.capacity,
                'price': str(room.price),
                'agreed_rent': str(room.agreed_rent) if room.agreed_rent is not None else None,
                'is_available': room.is_available,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def add_room(request):
    try:
        room_number = request.POST.get('room_number')
        building_name = request.POST.get('building_name')
        room_type = request.POST.get('room_type')
        price = float(request.POST.get('price', 0))
        capacity = int(request.POST.get('capacity', 1))
        agreed_val = request.POST.get('agreed_rent', None)
        agreed_rent = None
        if agreed_val is not None and agreed_val != '':
            try:
                agreed_rent = float(agreed_val)
            except ValueError:
                agreed_rent = None
        
        if Room.objects.filter(number=room_number).exists():
            return JsonResponse({
                'success': False,
                'message': f'Room {room_number} already exists'
            }, status=400)

        if not building_name:
            return JsonResponse({'success': False, 'message': 'A building must be selected'}, status=400)
        building = get_object_or_404(Building, name=building_name)
        
        room = Room.objects.create(
            number=room_number,
            building=building,
            room_type=room_type,
            price=price,
            capacity=capacity,
            agreed_rent=agreed_rent,
            is_available=True
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Room {room_number} created successfully',
            'room': {
                'id': room.id,
                'number': room.number,
                'building': room.building.name,
                'room_type': room.room_type,
                'capacity': room.capacity,
                    'price': str(room.price),
                    'agreed_rent': str(room.agreed_rent) if room.agreed_rent is not None else None,
                'is_available': room.is_available,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def delete_room(request, room_id):
    try:
        room = get_object_or_404(Room, id=room_id)
        room_number = room.number
        room.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Room {room_number} deleted successfully'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def add_guest(request):
    try:
        # Validate file size and type before processing
        ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        
        def validate_image_file(file_obj):
            if not file_obj:
                return True
            # Check file extension
            ext = file_obj.name.rsplit('.', 1)[1].lower() if '.' in file_obj.name else ''
            if ext not in ALLOWED_EXTENSIONS:
                raise ValueError(f'Invalid image type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}')
            # Check file size
            if file_obj.size > MAX_FILE_SIZE:
                raise ValueError(f'File size exceeds 5MB limit')
            return True
        
        # Validate all image files
        for file_field in ['govt_id_photo', 'college_id_photo', 'document_verification_image']:
            if file_field in request.FILES:
                validate_image_file(request.FILES[file_field])
        
        # Only first_name and last_name are required
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        if not first_name or not last_name:
            return JsonResponse({
                'success': False,
                'message': 'First name and last name are required'
            }, status=400)
        
        check_in = request.POST.get('check_in_date')
        check_out = request.POST.get('check_out_date')
        dob = request.POST.get('date_of_birth')
        
        # Parse dates if provided
        def parse_date(d):
            if not d: return None
            try: return datetime.strptime(d, '%Y-%m-%d').date()
            except: return None

        # Get room and agreed_rent
        room_id = request.POST.get('room_id') or None
        if room_id:
            room = get_object_or_404(Room, id=room_id)
            if room.is_full:
                 return JsonResponse({
                    'success': False,
                    'message': f'Room {room.number} is already full ({room.capacity}/{room.capacity})'
                }, status=400)

        agreed_rent_str = request.POST.get('agreed_rent', '').strip()
        occupancy_preference = request.POST.get('occupancy_preference', 'double')
        
        # Use transaction to ensure atomicity
        with transaction.atomic():
            guest = Guest.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=request.POST.get('email', '').strip(),
                phone=request.POST.get('phone', '').strip(),
                gender=request.POST.get('gender', 'M'),
                date_of_birth=parse_date(dob),
                address=request.POST.get('address', ''),
                city=request.POST.get('city', ''),
                state=request.POST.get('state', ''),
                country=request.POST.get('country', ''),
                zip_code=request.POST.get('zip_code', ''),
                id_type=request.POST.get('id_type', ''),
                id_number=request.POST.get('id_number', ''),
                college_id=request.POST.get('college_id', ''),
                student_college=request.POST.get('student_college', ''),
                check_in_date=parse_date(check_in),
                check_out_date=parse_date(check_out),
                room_id=room_id,
                notes=request.POST.get('notes', ''),
                occupancy_preference=occupancy_preference,
            )
            
            # Room status update and agreed_rent handling
            if guest.room:
                # Refresh room data from database to get accurate occupancy
                guest.room.refresh_from_db()
                
                # Mark as not available only if it reached capacity
                if guest.room.is_full:
                    guest.room.is_available = False
                
                # Set agreed_rent on the room if provided (default ₹7000)
                if agreed_rent_str:
                    try:
                        guest.room.agreed_rent = float(agreed_rent_str)
                    except ValueError:
                        guest.room.agreed_rent = 7000  # Default
                elif not guest.room.agreed_rent:
                    guest.room.agreed_rent = 7000  # Default if not set
                guest.room.save()

            if 'govt_id_photo' in request.FILES:
                guest.govt_id_photo = request.FILES['govt_id_photo']
            if 'college_id_photo' in request.FILES:
                guest.college_id_photo = request.FILES['college_id_photo']
            if 'document_verification_image' in request.FILES:
                guest.document_verification_image = request.FILES['document_verification_image']
            if 'aadhar_front' in request.FILES:
                guest.aadhar_front = request.FILES['aadhar_front']
            if 'aadhar_back' in request.FILES:
                guest.aadhar_back = request.FILES['aadhar_back']
            guest.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Guest {guest.full_name} added successfully',
            'guest': {
                'id': guest.id,
                'full_name': guest.full_name,
                'email': guest.email,
                'phone': guest.phone,
                'room': str(guest.room) if guest.room else 'Unassigned',
                'occupancy_preference': guest.get_occupancy_preference_display(),
            }
        })
    except ValueError as ve:
        return JsonResponse({
            'success': False,
            'message': str(ve)
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def update_guest(request, guest_id):
    """
    Update guest/tenant details with comprehensive validation.
    Ensures all updates propagate correctly throughout the system.
    """
    
    try:
        guest = get_object_or_404(Guest, id=guest_id)
        
        # Store old data for audit
        old_data = {
            'first_name': guest.first_name,
            'last_name': guest.last_name,
            'email': guest.email,
            'phone': guest.phone,
            'gender': guest.gender,
            'id_type': guest.id_type,
            'id_number': guest.id_number,
            'college_id': guest.college_id,
            'student_college': guest.student_college,
            'address': guest.address,
            'city': guest.city,
            'state': guest.state,
            'country': guest.country,
            'zip_code': guest.zip_code,
            'check_in_date': guest.check_in_date,
            'check_out_date': guest.check_out_date,
            'notes': guest.notes,
        }
        
        # Validate image files
        ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        
        def validate_image_file(file_obj):
            if not file_obj:
                return True
            ext = file_obj.name.rsplit('.', 1)[1].lower() if '.' in file_obj.name else ''
            if ext not in ALLOWED_EXTENSIONS:
                raise ValueError(f'Invalid image type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}')
            if file_obj.size > MAX_FILE_SIZE:
                raise ValueError(f'File size exceeds 5MB limit (File size: {file_obj.size / 1024 / 1024:.2f}MB)')
            return True
        
        for file_field in ['govt_id_photo', 'college_id_photo', 'document_verification_image']:
            if file_field in request.FILES:
                try:
                    validate_image_file(request.FILES[file_field])
                except ValueError as ve:
                    return JsonResponse({
                        'success': False,
                        'message': str(ve),
                        'field': file_field
                    }, status=400)
        
        # Prepare updates
        def parse_date(d):
            if not d: return None
            try: return datetime.strptime(d, '%Y-%m-%d').date()
            except: return d # Fallback to original if can't parse

        new_room_id = request.POST.get('room_id') or None
        if new_room_id: new_room_id = int(new_room_id)

        updates = {
            'first_name': request.POST.get('first_name', '').strip(),
            'last_name': request.POST.get('last_name', '').strip(),
            'email': request.POST.get('email', guest.email).strip(),
            'phone': request.POST.get('phone', '').strip(),
            'gender': request.POST.get('gender', guest.gender),
            'date_of_birth': parse_date(request.POST.get('date_of_birth')),
            'id_type': request.POST.get('id_type', guest.id_type),
            'id_number': request.POST.get('id_number', '').strip(),
            'college_id': request.POST.get('college_id', '').strip(),
            'student_college': request.POST.get('student_college', '').strip(),
            'address': request.POST.get('address', guest.address),
            'city': request.POST.get('city', guest.city),
            'state': request.POST.get('state', guest.state),
            'country': request.POST.get('country', guest.country),
            'zip_code': request.POST.get('zip_code', guest.zip_code),
            'check_in_date': parse_date(request.POST.get('check_in_date')),
            'check_out_date': parse_date(request.POST.get('check_out_date')),
            'notes': request.POST.get('notes', guest.notes),
            'room_id': new_room_id
        }
        
        # Validate updates
        errors = {}
        if not updates['first_name']: errors['first_name'] = 'First name is required'
        if not updates['last_name']: errors['last_name'] = 'Last name is required'
        if updates['email'] and not re.match(r"[^@]+@[^@]+\.[^@]+", updates['email']):
            errors['email'] = 'Invalid email format'
        
        if errors:
            return JsonResponse({'success': False, 'message': 'Validation failed', 'errors': errors}, status=400)
        
        # Use transaction to ensure atomicity
        with transaction.atomic():
            # Handle Room Change
            if guest.room_id != new_room_id:
                # Free old room
                old_room = guest.room
                if old_room:
                    # After this guest leaves, the room will definitely have a free slot
                    old_room.refresh_from_db()
                    old_room.is_available = True
                    old_room.save()
                
                # Occupy new room
                if new_room_id:
                    new_room = Room.objects.get(id=new_room_id)
                    new_room.refresh_from_db()
                    
                    # We check if NEW room is full (excluding the guest themselves if they were already there, 
                    # but here guest.room_id != new_room_id so they weren't)
                    if new_room.is_full:
                         return JsonResponse({
                            'success': False,
                            'message': f'Room {new_room.number} is already full ({new_room.capacity}/{new_room.capacity})'
                        }, status=400)
                    
                    # Update new room status if it becomes full after this guest joins
                    # Note: guest.room_id = new_room_id happens below, so for now current_occupancy doesn't include them
                    if new_room.current_occupancy + 1 >= new_room.capacity:
                        new_room.is_available = False
                        new_room.save()
            
            # Apply updates
            guest.first_name = updates['first_name'] or guest.first_name
            guest.last_name = updates['last_name'] or guest.last_name
            guest.email = updates['email']
            guest.phone = updates['phone'] or guest.phone
            guest.gender = updates['gender']
            guest.date_of_birth = updates['date_of_birth']
            guest.id_type = updates['id_type']
            guest.id_number = updates['id_number']
            guest.college_id = updates['college_id']
            guest.student_college = updates['student_college']
            guest.address = updates['address']
            guest.city = updates['city']
            guest.state = updates['state']
            guest.country = updates['country']
            guest.zip_code = updates['zip_code']
            guest.check_in_date = updates['check_in_date']
            guest.check_out_date = updates['check_out_date']
            guest.room_id = new_room_id
            guest.notes = updates['notes']
            
            # Update occupancy preference
            occupancy_preference = request.POST.get('occupancy_preference', guest.occupancy_preference)
            guest.occupancy_preference = occupancy_preference
            
            # Update images only if provided
            if 'govt_id_photo' in request.FILES:
                guest.govt_id_photo = request.FILES['govt_id_photo']
            if 'college_id_photo' in request.FILES:
                guest.college_id_photo = request.FILES['college_id_photo']
            if 'document_verification_image' in request.FILES:
                guest.document_verification_image = request.FILES['document_verification_image']
            
            # Mark as updated
            guest.updated_at = datetime.now()
            guest.save()
            
            # Audit logging
            logger.info(f"AUDIT - User: {request.user.username} - Updated Guest: {guest.id} ({guest.full_name})") 
        
        return JsonResponse({
            'success': True,
            'message': f'✓ Guest {guest.full_name} updated successfully and data synced',
            'guest': {
                'id': guest.id,
                'name': guest.full_name,
                'email': guest.email,
                'phone': guest.phone,
                'college_id': guest.college_id,
                'check_in': guest.check_in_date.strftime('%Y-%m-%d') if guest.check_in_date else None,
                'check_out': guest.check_out_date.strftime('%Y-%m-%d') if guest.check_out_date else None,
            }
        })
    except ValueError as ve:
        return JsonResponse({
            'success': False,
            'message': f'Validation Error: {str(ve)}'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error updating guest: {str(e)}'
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def checkout_guest(request, guest_id):
    """Mark guest as inactive and free up their room slot."""
    try:
        guest = get_object_or_404(Guest, id=guest_id)
        room = guest.room
        
        with transaction.atomic():
            guest.is_active = False
            # Fix: Record checkout date
            guest.check_out_date = timezone.now().date()
            
            # Fix: Do NOT clear guest.room to preserve history
            # guest.room = None 
            guest.save()
            
            if room:
                # Once a guest checks out, the room is definitely not full anymore
                # Only mark available if it was previously marked unavailable due to capacity
                # But typically we want it available now.
                room.is_available = True
                room.save()
                
        return JsonResponse({
            'success': True,
            'message': f'Guest {guest.full_name} checked out successfully. Room {room.number if room else "N/A"} now has a free slot.'
        })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"CHECKOUT ERROR for guest {guest_id}: {error_details}") # Print to console/logs
        return JsonResponse({'success': False, 'message': f"System Error: {str(e)}"}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def delete_guest(request, guest_id):
    try:
        guest = get_object_or_404(Guest, id=guest_id)
        name = guest.full_name
        
        # Free room and archive
        if guest.room:
            guest.room.is_available = True
            guest.room.save()
            guest.room = None # Remove room assignment
            
        guest.is_active = False
        guest.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Guest {name} archived successfully'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_guests(request):
    try:
        # Default to showing active guests unless specified
        show_archived = request.GET.get('archived') == 'true'
        if show_archived:
            guests = Guest.objects.all().select_related('room').order_by('-created_at')
        else:
            guests = Guest.objects.filter(is_active=True).select_related('room').order_by('-created_at')
            
        guests_data = []
        
        for g in guests:
            guests_data.append({
                'id': g.id,
                'first_name': g.first_name,
                'last_name': g.last_name,
                'full_name': g.full_name,
                'email': g.email,
                'phone': g.phone,
                'gender': g.gender,
                'date_of_birth': g.date_of_birth.strftime('%Y-%m-%d') if g.date_of_birth else None,
                'address': g.address,
                'city': g.city,
                'state': g.state,
                'country': g.country,
                'zip_code': g.zip_code,
                'id_type': g.id_type,
                'id_number': g.id_number,
                'college_id': g.college_id,
                'student_college': g.student_college,
                'check_in_date': g.check_in_date.strftime('%Y-%m-%d') if g.check_in_date else '',
                'check_out_date': g.check_out_date.strftime('%Y-%m-%d') if g.check_out_date else '',
                'notes': g.notes,
                'is_active': g.is_active,
                'created_at': g.created_at.isoformat() if g.created_at else None,
                'room': {
                    'id': g.room.id,
                    'number': g.room.number,
                    'price': str(g.room.price),
                    'agreed_rent': str(g.room.agreed_rent) if g.room.agreed_rent is not None else None
                } if g.room else None,
                'govt_id_photo': g.govt_id_photo.url if g.govt_id_photo else None,
                'college_id_photo': g.college_id_photo.url if g.college_id_photo else None,
            })
        
        return JsonResponse({
            'success': True,
            'guests': guests_data,
            'guest_list': guests_data # For compatibility
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
def manage_users(request):
    """View to manage owners/superusers ONLY as per latest requirement"""
    try:
        # User requested to only show users with superuser property
        managed_users = User.objects.filter(is_superuser=True).order_by('-date_joined')
        return render(request, 'manage_users.html', {
            'managed_users': managed_users,
            'is_admin': request.user.is_superuser
        })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in manage_users view: {e}\n{error_details}")
        return render(request, 'manage_users.html', {
            'managed_users': [],
            'is_admin': request.user.is_superuser,
            'error': f'Unable to load owner accounts: {str(e)}'
        })

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def add_user(request):
    """API to create a new staff user"""
    try:
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        is_staff = request.POST.get('is_staff') == 'true'

        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'message': 'Username already exists'}, status=400)

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        user.is_staff = is_staff
        user.save()
        return JsonResponse({'success': True, 'message': '✓ Staff member added successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def update_user(request, user_id):
    """API to update staff user details"""
    try:
        managed_user = get_object_or_404(User, id=user_id)
        managed_user.first_name = request.POST.get('first_name', managed_user.first_name)
        managed_user.last_name = request.POST.get('last_name', managed_user.last_name)
        managed_user.email = request.POST.get('email', managed_user.email)
        managed_user.is_staff = request.POST.get('is_staff') == 'true'
        managed_user.save()
        return JsonResponse({'success': True, 'message': '✓ User updated successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def delete_user(request, user_id):
    """API to delete staff user"""
    try:
        if request.user.id == user_id:
            return JsonResponse({'success': False, 'message': 'You cannot delete yourself'}, status=400)
        managed_user = get_object_or_404(User, id=user_id)
        managed_user.delete()
        return JsonResponse({'success': True, 'message': '✓ User deleted successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
def manage_payments(request):
    """Monthly payment tracking and management with advanced analytics"""
    from datetime import date, timedelta
    from django.db.models import Count, DecimalField
    from calendar import monthrange
    import calendar
    
    # render with v3 to bypass cache
    template_name = 'manage_payments_v3.html'
    today = date.today()
    current_month = date(today.year, today.month, 1)
    
    # Handle filtering parameters
    filter_status = request.GET.get('status', 'all')
    filter_month = request.GET.get('month', '')
    filter_room = request.GET.get('room', '')
    filter_building = request.GET.get('building', '')
    
    # Base queryset
    rooms = Room.objects.all().order_by('number')
    payments = MonthlyPayment.objects.select_related('room', 'guest').prefetch_related('payment_records')
    
    # Apply filters
    if filter_status != 'all':
        payments = payments.filter(payment_status=filter_status)
    
    if filter_month:
        try:
            filter_date = datetime.strptime(filter_month, '%Y-%m').date()
            payments = payments.filter(month=filter_date)
        except ValueError:
            pass
    
    if filter_room:
        payments = payments.filter(room__number__icontains=filter_room)
    
    if filter_building:
        payments = payments.filter(room__building__name=filter_building)
    
    # Order by month (newest first)
    payments = payments.order_by('-month', 'room__number')
    
    # Get payments for display - show all room payment cards
    # If no filters applied, default to current month to avoid overwhelming display
    if not any([filter_status != 'all', filter_month, filter_room, filter_building]):
        monthly_payments = payments.filter(month=current_month).order_by('room__number')
    else:
        monthly_payments = payments.order_by('-month', 'room__number')
    
    
    # Calculate comprehensive analytics
    all_payments = MonthlyPayment.objects.select_related('room', 'guest')
    
    # Current month analytics
    current_month_payments = all_payments.filter(month=current_month)
    current_month_revenue = sum(p.paid_amount for p in current_month_payments)
    current_month_expected = sum(p.rent_amount for p in current_month_payments)
    current_month_pending = sum(p.remaining_amount() for p in current_month_payments)
    
    # Overall analytics
    total_collected = PaymentRecord.objects.aggregate(
        total=Sum('payment_amount', output_field=DecimalField())
    )['total'] or Decimal('0.00')
    
    total_pending = sum(
        p.remaining_amount() for p in all_payments.filter(
            payment_status__in=['pending', 'partial', 'overdue']
        )
    )
    
    total_expected = sum(p.rent_amount for p in all_payments)
    
    # Collection rate calculation
    collection_rate = 0
    if total_expected > 0:
        collection_rate = (float(total_collected) / float(total_expected)) * 100
    
    # Payment status distribution
    status_distribution = {
        'pending': all_payments.filter(payment_status='pending').count(),
        'partial': all_payments.filter(payment_status='partial').count(),
        'paid': all_payments.filter(payment_status='paid').count(),
        'overdue': all_payments.filter(payment_status='overdue').count(),
    }
    
    # Overdue payments (older than current month and not paid)
    overdue_payments = all_payments.filter(
        month__lt=current_month,
        payment_status__in=['pending', 'partial']
    ).order_by('month')
    
    overdue_count = overdue_payments.count()
    overdue_amount = sum(p.remaining_amount() for p in overdue_payments)
    
    # Recent payment activity (last 10 payments)
    recent_payments = PaymentRecord.objects.select_related(
        'monthly_payment__room', 'monthly_payment__guest'
    ).order_by('-payment_date', '-created_at')[:10]
    
    # Monthly trend data (last 6 months)
    monthly_trends = []
    for i in range(5, -1, -1):
        trend_month = date(today.year, today.month, 1) - timedelta(days=i*30)
        trend_month = date(trend_month.year, trend_month.month, 1)
        
        trend_payments = all_payments.filter(month=trend_month)
        trend_collected = sum(p.paid_amount for p in trend_payments)
        trend_expected = sum(p.rent_amount for p in trend_payments)
        
        monthly_trends.append({
            'month': trend_month.strftime('%b %Y'),
            'collected': float(trend_collected),
            'expected': float(trend_expected),
            'rate': (float(trend_collected) / float(trend_expected) * 100) if trend_expected > 0 else 0
        })
    
    # Payment method breakdown
    payment_methods = PaymentRecord.objects.values('payment_method').annotate(
        count=Count('id'),
        total=Sum('payment_amount', output_field=DecimalField())
    ).order_by('-total')
    
    # Buildings list for filter - extract building codes and map to display names
    buildings = list(Building.objects.values_list('name', flat=True))
    
    # Prepare context
    context = {
        'rooms': rooms,
        'payments': payments[:100],  # Limit for performance
        'monthly_payments': monthly_payments,
        'recent_payments': recent_payments,
        'overdue_payments': overdue_payments[:20],  # Limit overdue display
        
        # Analytics data
        'analytics': {
            'current_month_revenue': current_month_revenue,
            'current_month_expected': current_month_expected,
            'current_month_pending': current_month_pending,
            'total_collected': total_collected,
            'total_pending': total_pending,
            'total_expected': total_expected,
            'collection_rate': round(collection_rate, 2),
            'overdue_count': overdue_count,
            'overdue_amount': overdue_amount,
        },
        
        # Status distribution
        'status_distribution': status_distribution,
        
        # Trends
        'monthly_trends': json.dumps(monthly_trends),
        'payment_methods': payment_methods,
        
        # Filter data
        'buildings': buildings,
        'current_filters': {
            'status': filter_status,
            'month': filter_month,
            'room': filter_room,
            'building': filter_building,
        },
        
        # Legacy stats (for compatibility)
        'payment_stats': {
            'pending': status_distribution['pending'],
            'partial': status_distribution['partial'],
            'paid': status_distribution['paid'],
            'overdue': status_distribution['overdue'],
            'total_pending_amount': total_pending,
        },
        'electricity_rate': _configured_electricity_rate(),
    }
    
    return render(request, template_name, context)

@login_required(login_url='login')
@user_passes_test(is_admin)
def manage_electricity_bills(request):
    """Electricity bill tracking and management"""
    rooms = Room.objects.select_related('building').all().order_by('building_id', 'number')
    
    # Build room data list expected by template
    bill_stats = []
    
    for room in rooms:
        # Get active tenant for this room
        tenant = Guest.objects.filter(room=room, is_active=True).first()
        
        # Get all bills for this room
        room_bills = ElectricityBill.objects.filter(room=room).order_by('-month')
        
        # Get latest reading (ending_reading from most recent bill)
        latest_reading = 13  # Default
        latest_units = 0  # Units consumed in latest bill
        if room_bills.exists():
            latest_bill = room_bills.first()
            latest_reading = latest_bill.ending_reading if latest_bill.ending_reading else 13
            latest_units = latest_bill.units_consumed if latest_bill.units_consumed else 0
        
        # Calculate total billed amount for this room
        total_billed = Decimal('0.00')
        try:
            for bill in room_bills:
                try:
                    total_billed += Decimal(str(bill.bill_amount)) if bill.bill_amount else Decimal('0.00')
                except (AttributeError, TypeError, ValueError):
                    continue
        except Exception as e:
            logger.error(f"Error calculating total billed for room {room.number}: {e}")
        
        # Get recent bills (last 5)
        recent_bills = room_bills[:5]
        
        # Add room data to list
        bill_stats.append({
            'room': room,
            'building_name': room.building.name,
            'tenant': tenant,
            'latest_reading': latest_reading,
            'latest_units': latest_units,
            'total_billed': total_billed,
            'recent_bills': recent_bills,
        })
    
    context = {
        'rooms': rooms,
        'bill_stats': bill_stats,
        'electricity_rate': _configured_electricity_rate(),
    }
    
    return render(request, 'manage_electricity_bills_v2.html', context)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def create_monthly_payment(request):
    """Create monthly payment record for a room"""
    try:
        room_id = request.POST.get('room_id')
        month_str = request.POST.get('month')
        
        if not room_id or not room_id.strip():
            return JsonResponse({'success': False, 'message': 'Room ID is required'}, status=400)
        if not month_str or not month_str.strip():
            return JsonResponse({'success': False, 'message': 'Month is required'}, status=400)
        
        # Determine rent amount: prefer explicit POSTed value, otherwise use room.agreed_rent, then fallback to room.price
        rent_amount_raw = request.POST.get('rent_amount', None)
        rent_amount = None
        if rent_amount_raw is not None and rent_amount_raw != '':
            try:
                rent_amount = float(rent_amount_raw)
            except ValueError:
                return JsonResponse({'success': False, 'message': 'Invalid rent amount'}, status=400)

        
        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Room not found'}, status=404)
        
        # If rent_amount not provided, use agreed_rent if set, otherwise room.price
        if not rent_amount or rent_amount <= 0:
            if getattr(room, 'agreed_rent', None) is not None:
                rent_amount = float(room.agreed_rent)
            else:
                rent_amount = float(room.price)

        # Parse month - handle both YYYY-MM-DD and YYYY-MM formats
        try:
            if len(month_str) == 10 and month_str[4] == '-' and month_str[7] == '-':
                # YYYY-MM-DD format
                month = datetime.strptime(month_str, '%Y-%m-%d').date()
            elif len(month_str) == 7 and month_str[4] == '-':
                # YYYY-MM format
                month = datetime.strptime(month_str, '%Y-%m').date()
            else:
                return JsonResponse({'success': False, 'message': f'Invalid month format: {month_str}. Use YYYY-MM or YYYY-MM-DD'}, status=400)
        except ValueError as e:
            return JsonResponse({'success': False, 'message': f'Error parsing month: {str(e)}'}, status=400)
        
        payment, created = MonthlyPayment.objects.get_or_create(
            room=room,
            month=month,
            defaults={'rent_amount': rent_amount}
        )
        
        if not created:
            payment.rent_amount = rent_amount
            payment.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Payment record {"created" if created else "updated"} for {room.number}',
            'payment': {
                'id': payment.id,
                'room': room.number,
                'month': month.strftime('%B %Y'),
                'rent_amount': str(payment.rent_amount),
                'paid_amount': str(payment.paid_amount),
                'status': payment.payment_status,
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error creating payment: {str(e)}'
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def record_payment(request):
    """Record a payment against monthly rent"""
    try:
        payment_id = request.POST.get('payment_id')
        if not payment_id:
            return JsonResponse({'success': False, 'message': 'Payment ID is required'}, status=400)
        
        # Validate and parse amount
        try:
            payment_amount = float(request.POST.get('payment_amount', 0))
            if payment_amount <= 0:
                return JsonResponse({'success': False, 'message': 'Payment amount must be greater than 0'}, status=400)
        except ValueError:
            return JsonResponse({'success': False, 'message': 'Invalid payment amount'}, status=400)
        
        # Validate and parse date
        payment_date_str = request.POST.get('payment_date')
        if not payment_date_str:
            return JsonResponse({'success': False, 'message': 'Payment date is required'}, status=400)
        
        try:
            from datetime import datetime as dt
            payment_date = dt.strptime(payment_date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'success': False, 'message': f'Invalid date format. Please use YYYY-MM-DD format. Received: {payment_date_str}'}, status=400)
        
        payment_method = request.POST.get('payment_method', 'cash')
        reference = request.POST.get('reference_number', '').strip()
        notes = request.POST.get('notes', '').strip()
        
        monthly_payment = get_object_or_404(MonthlyPayment, id=payment_id)
        
        # Create payment record
        record = PaymentRecord.objects.create(
            monthly_payment=monthly_payment,
            payment_date=payment_date,
            payment_amount=payment_amount,
            payment_method=payment_method,
            reference_number=reference,
            notes=notes,
            created_by=request.user
        )
        
        # Update monthly payment
        monthly_payment.paid_amount += payment_amount
        if monthly_payment.paid_amount >= monthly_payment.get_total_amount_due():
            monthly_payment.payment_status = 'paid'
            monthly_payment.paid_date = payment_date
        elif monthly_payment.paid_amount > 0:
            monthly_payment.payment_status = 'partial'
        
        monthly_payment.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Payment of ₹{payment_amount:.2f} recorded successfully on {payment_date.strftime("%d-%m-%Y")}',
            'payment': {
                'id': monthly_payment.id,
                'paid_amount': str(monthly_payment.paid_amount),
                'status': monthly_payment.payment_status,
                'remaining': str(monthly_payment.get_total_remaining()),
            }
        })
    except MonthlyPayment.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Payment record not found'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error recording payment: {str(e)}'
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def create_electricity_bill(request):
    """Create electricity bill for a room"""
    try:
        room_id = request.POST.get('room_id')
        month_str = request.POST.get('month')
        due_date_str = request.POST.get('due_date')

        # Validate required fields
        if not room_id:
            return JsonResponse({'success': False, 'message': 'Room ID is required'}, status=400)
        if not month_str:
            return JsonResponse({'success': False, 'message': 'Month is required (YYYY-MM or YYYY-MM-DD)'}, status=400)

        # Parse numeric fields with validation and defaults
        try:
            starting_reading = float(request.POST.get('starting_reading') or 13)  # Default: 13 units
            ending_reading = float(request.POST.get('ending_reading') or (starting_reading + 150))  # Default: +150 units  
            requested_rate = request.POST.get('rate_per_unit')
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Invalid numeric input for readings or rate'}, status=400)

        rate_per_unit = float(_configured_electricity_rate())
        if not _requested_electricity_rate_matches_configured(requested_rate):
            return JsonResponse({'success': False, 'message': 'Electricity rate is set by the server and cannot be overridden'}, status=400)
        if ending_reading < starting_reading:
            return JsonResponse({'success': False, 'message': 'Ending reading must be greater than or equal to starting reading'}, status=400)
        if rate_per_unit <= 0:
            return JsonResponse({'success': False, 'message': 'Rate per unit must be greater than 0'}, status=400)

        # Get room
        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Room not found'}, status=404)

        # Parse month - accept YYYY-MM-DD or YYYY-MM
        try:
            if len(month_str) == 10 and month_str[4] == '-' and month_str[7] == '-':
                month = datetime.strptime(month_str, '%Y-%m-%d').date()
            elif len(month_str) == 7 and month_str[4] == '-':
                month = datetime.strptime(month_str, '%Y-%m').date()
            else:
                return JsonResponse({'success': False, 'message': f'Invalid month format: {month_str}. Use YYYY-MM or YYYY-MM-DD'}, status=400)
        except ValueError as e:
            return JsonResponse({'success': False, 'message': f'Error parsing month: {str(e)}'}, status=400)

        # Parse due date if provided, otherwise default to last day of billing month
        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'message': 'Invalid due date format. Use YYYY-MM-DD'}, status=400)
        else:
            # Default to last day of billing month
            from calendar import monthrange
            last_day = monthrange(month.year, month.month)[1]
            due_date = month.replace(day=last_day)

        units_consumed = ending_reading - starting_reading
        bill_amount = units_consumed * rate_per_unit

        # Get current active guest for the room
        guest = Guest.objects.filter(room=room, is_active=True).first()

        bill, created = ElectricityBill.objects.get_or_create(
            room=room,
            month=month,
            defaults={
                'guest': guest,
                'starting_reading': starting_reading,
                'ending_reading': ending_reading,
                'units_consumed': units_consumed,
                'rate_per_unit': rate_per_unit,
                'bill_amount': bill_amount,
                'due_date': due_date,
            }
        )

        if not created:
            if Decimal(str(bill.rate_per_unit)) != _configured_electricity_rate():
                return JsonResponse({
                    'success': False,
                    'message': 'This bill already exists at a different electricity rate and was not changed.',
                }, status=409)
            bill.guest = guest
            bill.starting_reading = starting_reading
            bill.ending_reading = ending_reading
            bill.units_consumed = units_consumed
            bill.rate_per_unit = rate_per_unit
            bill.bill_amount = bill_amount
            bill.due_date = due_date
            bill.save()

        return JsonResponse({
            'success': True,
            'message': f'Electricity bill created for {room.number}',
            'bill': {
                'id': bill.id,
                'room': room.number,
                'month': month.strftime('%B %Y'),
                'units': str(bill.units_consumed),
                'bill_amount': str(bill.bill_amount),
                'status': bill.bill_status,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])

def ensure_monthly_payment_exists(room, month, guest=None):
    """
    Ensure a MonthlyPayment record exists for the given room and month.
    Auto-creates if missing using guest's agreed rent.
    Returns the MonthlyPayment object.
    """
    from decimal import Decimal
    
    # Get active guest if not provided
    if not guest:
        guest = Guest.objects.filter(room=room, is_active=True).first()
    
    # Determine rent amount (from guest's agreed rent or room's default rent)
    rent_amount = Decimal('7000.00')  # Default fallback
    if guest and hasattr(guest, 'agreed_rent') and guest.agreed_rent:
        rent_amount = Decimal(str(guest.agreed_rent))
    elif hasattr(room, 'rent_amount') and room.rent_amount:
        rent_amount = Decimal(str(room.rent_amount))
    
    # Get or create monthly payment
    monthly_payment, created = MonthlyPayment.objects.get_or_create(
        room=room,
        month=month,
        defaults={
            'guest': guest,
            'rent_amount': rent_amount,
            'payment_status': 'pending',
            'paid_amount': Decimal('0.00')
        }
    )
    
    # Update guest and rent if record exists but data changed
    if not created:
        updated = False
        if guest and monthly_payment.guest != guest:
            monthly_payment.guest = guest
            updated = True
        # Update rent amount if it changed (e.g., guest's agreed rent was updated)
        if monthly_payment.rent_amount != rent_amount:
            monthly_payment.rent_amount = rent_amount
            updated = True
        if updated:
            monthly_payment.save()
    
    return monthly_payment

def bulk_create_electricity_bills(request):
    """Create electricity bills for multiple rooms at once"""
    try:
        import json
        from calendar import monthrange
        
        month_str = request.POST.get('month')
        rate_per_unit_str = request.POST.get('rate_per_unit')
        readings_json = request.POST.get('readings')

        # Validate required fields
        if not month_str:
            return JsonResponse({'success': False, 'message': 'Month is required'}, status=400)
        if not readings_json:
            return JsonResponse({'success': False, 'message': 'No readings provided'}, status=400)

        # Parse rate
        try:
            rate_per_unit = float(_configured_electricity_rate())
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Invalid rate per unit'}, status=400)
        if not _requested_electricity_rate_matches_configured(rate_per_unit_str):
            return JsonResponse({'success': False, 'message': 'Electricity rate is set by the server and cannot be overridden'}, status=400)

        # Parse month
        try:
            if len(month_str) == 10 and month_str[4] == '-' and month_str[7] == '-':
                month = datetime.strptime(month_str, '%Y-%m-%d').date()
            elif len(month_str) == 7 and month_str[4] == '-':
                month = datetime.strptime(month_str, '%Y-%m').date()
            else:
                return JsonResponse({'success': False, 'message': f'Invalid month format: {month_str}'}, status=400)
        except ValueError as e:
            return JsonResponse({'success': False, 'message': f'Error parsing month: {str(e)}'}, status=400)

        # Calculate due date (last day of month)
        last_day = monthrange(month.year, month.month)[1]
        due_date = month.replace(day=last_day)

        # Parse readings JSON
        try:
            readings = json.loads(readings_json)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid readings data'}, status=400)

        created_count = 0
        updated_count = 0
        errors = []

        # Process each reading
        for reading_data in readings:
            try:
                room_id = reading_data.get('room_id')
                starting_reading = float(reading_data.get('starting_reading', 13))
                ending_reading = float(reading_data.get('ending_reading'))

                # Validate
                if not room_id:
                    errors.append({'room': 'Unknown', 'error': 'Room ID missing'})
                    continue

                if ending_reading < starting_reading:
                    errors.append({'room': room_id, 'error': 'Ending reading less than starting'})
                    continue

                # Get room
                try:
                    room = Room.objects.get(id=room_id)
                except Room.DoesNotExist:
                    errors.append({'room': room_id, 'error': 'Room not found'})
                    continue

                # Calculate bill
                units_consumed = ending_reading - starting_reading
                bill_amount = units_consumed * rate_per_unit

                # Get active guest
                guest = Guest.objects.filter(room=room, is_active=True).first()

                # Create or update bill
                bill, created = ElectricityBill.objects.get_or_create(
                    room=room,
                    month=month,
                    defaults={
                        'guest': guest,
                        'starting_reading': starting_reading,
                        'ending_reading': ending_reading,
                        'units_consumed': units_consumed,
                        'rate_per_unit': rate_per_unit,
                        'bill_amount': bill_amount,
                        'due_date': due_date,
                    }
                )

                if created:
                    created_count += 1
                else:
                    if Decimal(str(bill.rate_per_unit)) != _configured_electricity_rate():
                        errors.append({
                            'room': room_id,
                            'error': 'Existing bill has a different electricity rate and was not changed',
                        })
                        continue
                    # Update existing bill
                    bill.guest = guest
                    bill.starting_reading = starting_reading
                    bill.ending_reading = ending_reading
                    bill.units_consumed = units_consumed
                    bill.rate_per_unit = rate_per_unit
                    bill.bill_amount = bill_amount
                    bill.due_date = due_date
                    bill.save()
                    updated_count += 1

            except Exception as e:
                errors.append({'room': reading_data.get('room_id', 'Unknown'), 'error': str(e)})

        # Prepare response
        message = f'Created {created_count} bills'
        if updated_count > 0:
            message += f', updated {updated_count} bills'
        if errors:
            message += f', {len(errors)} errors'

        return JsonResponse({
            'success': True,
            'message': message,
            'created_count': created_count,
            'updated_count': updated_count,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error processing bulk bills: {str(e)}'
        }, status=400)


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def record_electricity_payment(request):
    """Record electricity bill payment"""
    try:
        bill_id = request.POST.get('bill_id')
        paid_amount = float(request.POST.get('paid_amount', 0))
        paid_date = request.POST.get('paid_date')
        
        bill = get_object_or_404(ElectricityBill, id=bill_id)
        bill.paid_amount += paid_amount
        
        if bill.paid_amount >= bill.bill_amount:
            bill.bill_status = 'paid'
            bill.paid_date = paid_date
        
        bill.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Electricity payment of ₹{paid_amount} recorded',
            'bill': {
                'id': bill.id,
                'paid_amount': str(bill.paid_amount),
                'status': bill.bill_status,
                'remaining': str(bill.remaining_amount()),
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_payment_history(request, room_id):
    """Get payment history for a room"""
    try:
        room = get_object_or_404(Room, id=room_id)
        payments = MonthlyPayment.objects.filter(room=room).order_by('-month')
        
        history = []
        for payment in payments:
            records = PaymentRecord.objects.filter(monthly_payment=payment).order_by('-payment_date')
            history.append({
                'id': payment.id,
                'month': payment.month.strftime('%B %Y'),
                'rent_amount': str(payment.rent_amount),
                'paid_amount': str(payment.paid_amount),
                'remaining': str(payment.remaining_amount()),
                'status': payment.payment_status,
                'paid_date': payment.paid_date.strftime('%Y-%m-%d') if payment.paid_date else None,
                'records': [{
                    'date': r.payment_date.strftime('%Y-%m-%d'),
                    'amount': str(r.payment_amount),
                    'method': r.get_payment_method_display(),
                    'ref': r.reference_number,
                } for r in records]
            })
        
        return JsonResponse({
            'success': True,
            'room': room.number,
            'history': history
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


# =====================
# BOOKING MANAGEMENT
# =====================

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def booking_page(request):
    """Display booking form page for creating new guest bookings"""
    return render(request, 'book_room.html', {'buildings': Building.objects.all()})


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_available_rooms(request):
    """Get list of available rooms"""
    try:
        # Get only available rooms
        available_rooms = Room.objects.filter(is_available=True)
        
        rooms_data = [{
            'id': room.id,
            'number': room.number,
            'room_type': room.get_room_type_display(),
            'price': str(room.price),
            'agreed_rent': str(room.agreed_rent) if room.agreed_rent is not None else None
        } for room in available_rooms]
        
        return JsonResponse({
            'success': True,
            'rooms': rooms_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def submit_booking(request):
    """Submit booking with guest information"""
    try:
        from dateutil.relativedelta import relativedelta
        
        # Parse form data
        room_id = request.POST.get('room_id')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        gender = request.POST.get('gender', 'M')
        date_of_birth = request.POST.get('date_of_birth', None)
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        country = request.POST.get('country', 'India').strip()
        zip_code = request.POST.get('zip_code', '').strip()
        id_type = request.POST.get('id_type', '').strip()
        id_number = request.POST.get('id_number', '').strip()
        check_in_date = request.POST.get('check_in_date')
        check_out_date = request.POST.get('check_out_date')
        notes = request.POST.get('notes', '').strip()
        
        # Validate required fields
        if not all([room_id, first_name, last_name, email, phone, id_type, id_number, check_in_date, check_out_date]):
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields'
            }, status=400)
        
        # Get room
        room = get_object_or_404(Room, id=room_id)
        if not room.is_available:
            return JsonResponse({
                'success': False,
                'message': 'This room is no longer available'
            }, status=400)
        
        # Parse dates
        try:
            check_in = datetime.strptime(check_in_date, '%Y-%m-%d').date()
            check_out = datetime.strptime(check_out_date, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid date format'
            }, status=400)
        
        # Validate dates
        if check_in >= check_out:
            return JsonResponse({
                'success': False,
                'message': 'Check-out date must be after check-in date'
            }, status=400)
        
        # Check if email already exists
        existing_guest = Guest.objects.filter(email=email).first()
        if existing_guest:
            guest = existing_guest
            # Update guest information
            guest.first_name = first_name
            guest.last_name = last_name
            guest.phone = phone
            guest.gender = gender
            guest.date_of_birth = date_of_birth if date_of_birth else guest.date_of_birth
            guest.address = address
            guest.city = city
            guest.state = state
            guest.country = country
            guest.zip_code = zip_code
            guest.id_type = id_type
            guest.id_number = id_number
            guest.notes = notes
        else:
            # Create new guest
            guest = Guest(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                gender=gender,
                date_of_birth=date_of_birth if date_of_birth else None,
                address=address,
                city=city,
                state=state,
                country=country,
                zip_code=zip_code,
                id_type=id_type,
                id_number=id_number,
                notes=notes,
                is_active=True
            )
        
        guest.check_in_date = check_in
        guest.check_out_date = check_out
        guest.room = room
        guest.save()
        
        # Create or update booking
        booking = Booking.objects.create(
            room=room,
            customer_name=f"{first_name} {last_name}",
            check_in=check_in,
            check_out=check_out,
            created_by=request.user if request.user.is_authenticated else None,
            is_active=True
        )
        
        # Create monthly payment record if needed
        current = check_in.replace(day=1)
        # When creating monthly payments for the booking range prefer agreed_rent if set
        while current < check_out:
            monthly_payment, created = MonthlyPayment.objects.get_or_create(
                room=room,
                month=current,
                defaults={
                    'guest': guest,
                    'rent_amount': (room.agreed_rent if getattr(room, 'agreed_rent', None) is not None else room.price),
                    'paid_amount': 0,
                    'payment_status': 'pending',
                }
            )
            if created:
                monthly_payment.guest = guest
                monthly_payment.save()
            
            current = current + relativedelta(months=1)
        
        console_log_data = {
            'action': 'booking_created',
            'guest': f"{guest.first_name} {guest.last_name}",
            'room': room.number,
            'check_in': check_in.strftime('%Y-%m-%d'),
            'check_out': check_out.strftime('%Y-%m-%d'),
            'booking_id': booking.id
        }
        
        print(f"✓ Booking created successfully: {json.dumps(console_log_data, indent=2)}")
        
        return JsonResponse({
            'success': True,
            'message': 'Booking completed successfully',
            'booking_id': booking.id,
            'guest_id': guest.id
        })
        
    except Exception as e:
        print(f"✗ Booking error: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Error creating booking: {str(e)}'
        }, status=400)


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_room_tenants(request, room_id):
    """Get current and past tenants for a room"""
    try:
        room = get_object_or_404(Room, id=room_id)
        
        # Get active guests in this room
        guests = Guest.objects.filter(room=room, is_active=True).order_by('-check_in_date')
        
        guests_data = []
        for guest in guests:
            guests_data.append({
                'id': guest.id,
                'name': guest.full_name,
                'email': guest.email,
                'phone': guest.phone,
                'check_in': guest.check_in_date.strftime('%Y-%m-%d') if guest.check_in_date else None,
                'check_out': guest.check_out_date.strftime('%Y-%m-%d') if guest.check_out_date else None,
                'gender': guest.get_gender_display() if hasattr(guest, 'get_gender_display') else guest.gender,
                'id_type': guest.id_type,
                'id_number': guest.id_number,
                'address': guest.address,
                'city': guest.city,
                'state': guest.state,
                'country': guest.country,
                'zip_code': guest.zip_code,
                'notes': guest.notes,
                'college_id': guest.college_id,
                'student_college': guest.student_college,
                'govt_id_photo': guest.govt_id_photo.url if guest.govt_id_photo else None,
                'aadhar_front': guest.aadhar_front.url if guest.aadhar_front else None,
                'aadhar_back': guest.aadhar_back.url if guest.aadhar_back else None,
                'college_id_photo': guest.college_id_photo.url if guest.college_id_photo else None,
                'document_verification_image': (
                    guest.document_verification_image.url
                    if guest.document_verification_image
                    else None
                ),
            })
        
        return JsonResponse({
            'success': True,
            'room': room.number,
            'tenants': guests_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


def _get_room_billing_snapshot(room):
    """Return the authoritative room billing state using Django models as the source of truth."""
    from decimal import Decimal

    active_guest = Guest.objects.filter(room=room, is_active=True).first()
    month = timezone.now().date().replace(day=1)
    monthly_payment = MonthlyPayment.objects.filter(room=room, month=month).first()
    current_bill = ElectricityBill.objects.filter(room=room, month=month).first()
    previous_bill = ElectricityBill.objects.filter(room=room, month__lt=month).order_by('-month').first()
    rent_amount = Decimal(str(room.agreed_rent if room.agreed_rent is not None else room.price))
    electricity_amount = Decimal(str(current_bill.bill_amount)) if current_bill else Decimal('0.00')
    total_bill = rent_amount + electricity_amount
    collected = Decimal(str(monthly_payment.paid_amount)) if monthly_payment else Decimal('0.00')
    outstanding = max(Decimal('0.00'), total_bill - collected)

    if collected == 0:
        status = 'DUE'
    elif collected >= total_bill:
        status = 'PAID'
    else:
        status = 'PARTIAL'

    return {
        'id': room.id,
        'room': room.number,
        'building': room.building.name,
        'resident': active_guest.full_name if active_guest else 'No resident',
        'agreed_rent': float(rent_amount),
        'current_bill': float(total_bill),
        'previous_reading': float(current_bill.starting_reading) if current_bill else float(previous_bill.ending_reading) if previous_bill else 0,
        'current_reading': float(current_bill.ending_reading) if current_bill else None,
        'units_used': float(current_bill.units_consumed) if current_bill else 0,
        'electricity_rate': float(current_bill.rate_per_unit) if current_bill else float(_configured_electricity_rate()),
        'new_bill_rate': float(_configured_electricity_rate()),
        'electricity_amount': float(electricity_amount),
        'collected_amount': float(collected),
        'outstanding_amount': float(outstanding),
        'payment_status': status,
        'total_bill': float(total_bill),
    }

@ensure_csrf_cookie
@require_http_methods(["GET"])
def api_csrf(request):
    """
    Hand the browser a CSRF token it can actually read.

    When the React app is served from a different origin than this API (Vercel
    -> Render), the `csrftoken` cookie is set on the API's domain and is
    therefore invisible to `document.cookie` on the page's origin. The client
    then sends an empty X-CSRFToken header, which Django rejects as "incorrect
    length".

    This endpoint returns the token in the response body so the client can send
    it explicitly. It uses Django's own `get_token()` and `ensure_csrf_cookie`,
    so the CSRF mechanism is unchanged — the token is still masked/verified by
    CsrfViewMiddleware, and the cookie is still set. Read-only: no database
    access and no session or authentication changes.
    """
    return JsonResponse({'csrfToken': get_token(request)})


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_rooms(request):
    """Return room inventory and authoritative billing state for room-first operations."""
    rooms = Room.objects.select_related('building').all().order_by('number')
    building_map = {}
    rooms_data = []
    for room in rooms:
        snapshot = _get_room_billing_snapshot(room)
        rooms_data.append(snapshot)
        building_map.setdefault(snapshot['building'], []).append(snapshot)

    response = {
        'success': True,
        'count': rooms.count(),
        'buildings': [
            {'name': name, 'rooms': rooms_for_building}
            for name, rooms_for_building in sorted(
                building_map.items(),
                key=lambda item: ['M1', '1', '2', '3', '4', '5'].index(item[0]) if item[0] in ['M1', '1', '2', '3', '4', '5'] else 999,
            )
        ],
        'rooms': rooms_data,
    }
    return JsonResponse(response)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_room_detail(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    return JsonResponse({'success': True, 'room': _get_room_billing_snapshot(room)})

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def api_generate_bill(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        else:
            data = request.POST
        if 'current_reading' not in data or str(data['current_reading']).strip() == '':
            return JsonResponse({'success': False, 'message': 'Current electricity reading is required'}, status=400)

        current_reading = Decimal(str(data['current_reading']))
        rate_per_unit = _configured_electricity_rate()
        if not rate_per_unit.is_finite() or rate_per_unit <= 0:
            return JsonResponse({'success': False, 'message': 'Electricity rate must be configured as a positive finite value'}, status=500)
        currency_precision = Decimal('0.01')
        if current_reading.is_finite() and current_reading != current_reading.quantize(currency_precision):
            return JsonResponse({'success': False, 'message': 'Current reading supports at most two decimal places'}, status=400)
        if rate_per_unit != rate_per_unit.quantize(currency_precision):
            return JsonResponse({'success': False, 'message': 'Configured electricity rate supports at most two decimal places'}, status=500)
        if 'electricity_rate' in data:
            requested_rate = Decimal(str(data['electricity_rate']))
            if not requested_rate.is_finite() or requested_rate <= 0 or requested_rate != rate_per_unit:
                return JsonResponse({'success': False, 'message': 'Electricity rate is set by the server and cannot be overridden'}, status=400)
        if not current_reading.is_finite() or current_reading < 0:
            return JsonResponse({'success': False, 'message': 'Current reading must be a finite, non-negative number'}, status=400)

        month = timezone.now().date().replace(day=1)
        existing_bill = ElectricityBill.objects.filter(room=room, month=month).first()
        if existing_bill and Decimal(str(existing_bill.rate_per_unit)) != rate_per_unit:
            return JsonResponse({
                'success': False,
                'message': 'This bill already exists at a different electricity rate and was not changed.',
            }, status=409)
        previous_bill = ElectricityBill.objects.filter(room=room, month__lt=month).order_by('-month').first()
        previous_reading = Decimal(str(previous_bill.ending_reading)) if previous_bill else Decimal('0')
        if current_reading < previous_reading:
            return JsonResponse({'success': False, 'message': f'Current reading must be greater than or equal to previous reading ({previous_reading})'}, status=400)

        units_used = current_reading - previous_reading
        from decimal import ROUND_HALF_UP

        electricity_amount = (units_used * rate_per_unit).quantize(currency_precision, rounding=ROUND_HALF_UP)
        agreed_rent = Decimal(str(room.agreed_rent)) if getattr(room, 'agreed_rent', None) is not None else Decimal(str(room.price))
        total_bill = (agreed_rent + electricity_amount).quantize(currency_precision, rounding=ROUND_HALF_UP)

        guest = Guest.objects.filter(room=room, is_active=True).first()
        from calendar import monthrange

        due_date = month.replace(day=monthrange(month.year, month.month)[1])
        with transaction.atomic():
            monthly_payment, _ = MonthlyPayment.objects.get_or_create(
                room=room,
                month=month,
                defaults={'guest': guest, 'rent_amount': agreed_rent, 'paid_amount': Decimal('0.00'), 'payment_status': 'pending'}
            )
            monthly_payment.guest = guest
            monthly_payment.rent_amount = agreed_rent
            monthly_payment.save(update_fields=['guest', 'rent_amount'])

            bill, _ = ElectricityBill.objects.get_or_create(
                room=room,
                month=month,
                defaults={
                    'guest': guest,
                    'starting_reading': previous_reading,
                    'ending_reading': current_reading,
                    'units_consumed': units_used,
                    'rate_per_unit': rate_per_unit,
                    'bill_amount': electricity_amount,
                    'due_date': due_date,
                },
            )
            bill.guest = guest
            bill.starting_reading = previous_reading
            bill.ending_reading = current_reading
            bill.units_consumed = units_used
            bill.rate_per_unit = rate_per_unit
            bill.bill_amount = electricity_amount
            bill.due_date = due_date
            bill.save()

            if monthly_payment.paid_amount == 0:
                monthly_payment.payment_status = 'pending'
            elif monthly_payment.paid_amount >= total_bill:
                monthly_payment.payment_status = 'paid'
            else:
                monthly_payment.payment_status = 'partial'
            monthly_payment.save(update_fields=['payment_status'])

        payload = {
            'success': True,
            'room': room.number,
            'building': room.building.name,
            'resident': guest.full_name if guest else 'No resident',
            'agreed_rent': float(agreed_rent),
            'previous_reading': float(previous_reading),
            'current_reading': float(current_reading),
            'units_used': float(units_used),
            'electricity_rate': float(rate_per_unit),
            'electricity_amount': float(electricity_amount),
            'total_bill': float(total_bill),
            'bill': {
                'id': bill.id,
                'month': month.strftime('%Y-%m'),
                'status': bill.bill_status,
            },
        }
        return JsonResponse(payload)
    except (ValueError, TypeError, ArithmeticError) as exc:
        return JsonResponse({'success': False, 'message': f'Invalid bill request: {exc}'}, status=400)
    except Exception:
        logger.exception('Failed to generate room bill for room %s', room_id)
        return JsonResponse({'success': False, 'message': 'Unable to generate the room bill'}, status=500)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_current_bill(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    snapshot = _get_room_billing_snapshot(room)
    return JsonResponse({'success': True, **snapshot})

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def api_collect_payment(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        else:
            data = request.POST
        if 'amount' not in data or str(data['amount']).strip() == '':
            return JsonResponse({'success': False, 'message': 'Payment amount is required'}, status=400)

        amount = Decimal(str(data['amount']))
        if not amount.is_finite() or amount <= 0:
            return JsonResponse({'success': False, 'message': 'Payment amount must be greater than 0'}, status=400)
        currency_precision = Decimal('0.01')
        if amount != amount.quantize(currency_precision):
            return JsonResponse({'success': False, 'message': 'Payment amount supports at most two decimal places'}, status=400)

        month = timezone.now().date().replace(day=1)
        method = str(data.get('payment_method') or 'cash')
        valid_methods = {choice[0] for choice in PaymentRecord._meta.get_field('payment_method').choices}
        if method not in valid_methods:
            return JsonResponse({'success': False, 'message': 'Invalid payment method'}, status=400)

        with transaction.atomic():
            monthly_payment, _ = MonthlyPayment.objects.select_for_update().get_or_create(
                room=room,
                month=month,
                defaults={
                    'guest': Guest.objects.filter(room=room, is_active=True).first(),
                    'rent_amount': Decimal(str(room.agreed_rent)) if room.agreed_rent is not None else Decimal(str(room.price)),
                    'paid_amount': Decimal('0.00'),
                    'payment_status': 'pending',
                },
            )
            monthly_payment.rent_amount = Decimal(str(room.agreed_rent if room.agreed_rent is not None else room.price))
            current_bill = ElectricityBill.objects.filter(room=room, month=month).first()
            total_bill = monthly_payment.rent_amount + (Decimal(str(current_bill.bill_amount)) if current_bill else Decimal('0.00'))
            monthly_payment.paid_amount += amount
            if monthly_payment.paid_amount == 0:
                monthly_payment.payment_status = 'pending'
                monthly_payment.paid_date = None
            elif monthly_payment.paid_amount >= total_bill:
                monthly_payment.payment_status = 'paid'
                monthly_payment.paid_date = timezone.now().date()
            else:
                monthly_payment.payment_status = 'partial'
                monthly_payment.paid_date = None
            monthly_payment.save()

            record = PaymentRecord.objects.create(
                monthly_payment=monthly_payment,
                payment_date=timezone.now().date(),
                payment_amount=amount,
                payment_method=method,
                reference_number=str(data.get('reference_number') or '').strip(),
                notes=str(data.get('notes') or '').strip(),
                created_by=request.user,
            )
            collected = Decimal(str(monthly_payment.paid_amount))
            outstanding = max(Decimal('0.00'), total_bill - collected)
            status = 'DUE' if collected == 0 else 'PAID' if collected >= total_bill else 'PARTIAL'

        return JsonResponse({
            'success': True,
            'room': room.number,
            'amount': float(amount),
            'total_bill': float(total_bill),
            'collected_amount': float(collected),
            'outstanding_amount': float(outstanding),
            'payment_status': status,
            'record_id': record.id,
        })
    except (ValueError, TypeError, ArithmeticError) as exc:
        return JsonResponse({'success': False, 'message': f'Invalid payment request: {exc}'}, status=400)
    except Exception:
        logger.exception('Failed to collect payment for room %s', room_id)
        return JsonResponse({'success': False, 'message': 'Unable to record the room payment'}, status=500)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_room_payments(request, room_id):
    room = get_object_or_404(Room, id=room_id)
    payments = PaymentRecord.objects.filter(monthly_payment__room=room).order_by('-payment_date', '-id')
    return JsonResponse({
        'success': True,
        'room': room.number,
        'payments': [
            {
                'id': payment.id,
                'amount': float(payment.payment_amount),
                'date': payment.payment_date.isoformat(),
                'method': payment.payment_method,
                'reference_number': payment.reference_number,
                'notes': payment.notes,
            }
            for payment in payments
        ],
    })

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_room_details(request, room_id):
    """Return basic room details for booking UI (price, agreed_rent, description)"""
    try:
        room = get_object_or_404(Room, id=room_id)
        room_data = {
            'id': room.id,
            'number': room.number,
            'room_type': room.get_room_type_display(),
            'price_per_month': str(room.price),
            'agreed_rent': str(room.agreed_rent) if getattr(room, 'agreed_rent', None) is not None else '',
            'description': getattr(room, 'description', '') if hasattr(room, 'description') else '',
        }
        return JsonResponse({'success': True, 'room': room_data})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_electricity_history(request, room_id):
    """Get electricity bill history for a room"""
    try:
        room = get_object_or_404(Room, id=room_id)
        bills = ElectricityBill.objects.filter(room=room).order_by('-month')
        
        history = []
        for bill in bills:
            history.append({
                'id': bill.id,
                'month': bill.month.strftime('%B %Y'),
                'units': str(bill.units_consumed),
                'rate': str(bill.rate_per_unit),
                'bill_amount': str(bill.bill_amount),
                'paid_amount': str(bill.paid_amount),
                'remaining': str(bill.remaining_amount()),
                'status': bill.bill_status,
                'due_date': bill.due_date.strftime('%Y-%m-%d'),
                'paid_date': bill.paid_date.strftime('%Y-%m-%d') if bill.paid_date else None,
            })
        
        return JsonResponse({
            'success': True,
            'room': room.number,
            'history': history
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def update_payment_record(request, record_id):
    """Update an existing payment record and sync monthly payment total"""
    try:
        record = get_object_or_404(PaymentRecord, id=record_id)
        monthly_payment = record.monthly_payment
        
        old_amount = record.payment_amount
        raw_amount = request.POST.get('payment_amount', str(old_amount))
        new_amount = Decimal(raw_amount)
        
        record.payment_amount = new_amount
        date_str = request.POST.get('payment_date')
        if date_str:
            record.payment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
        record.payment_method = request.POST.get('payment_method', record.payment_method)
        record.notes = request.POST.get('notes', record.notes)
        record.save()
        
        # Recalculate total paid for the month
        total_paid = PaymentRecord.objects.filter(monthly_payment=monthly_payment).aggregate(
            total=Sum('payment_amount'))['total'] or Decimal('0.00')
        
        monthly_payment.paid_amount = total_paid
        # Update status
        if monthly_payment.paid_amount >= monthly_payment.get_total_amount_due():
            monthly_payment.payment_status = 'paid'
        elif monthly_payment.paid_amount > 0:
            monthly_payment.payment_status = 'partial'
        else:
            monthly_payment.payment_status = 'pending'
        monthly_payment.save()
        
        return JsonResponse({'success': True, 'message': 'Payment record updated'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def delete_payment_record(request, record_id):
    """Delete a payment record and sync monthly payment total"""
    try:
        record = get_object_or_404(PaymentRecord, id=record_id)
        monthly_payment = record.monthly_payment
        record.delete()
        
        # Recalculate
        total_paid = PaymentRecord.objects.filter(monthly_payment=monthly_payment).aggregate(
            total=Sum('payment_amount'))['total'] or Decimal('0.00')
        
        monthly_payment.paid_amount = total_paid
        if monthly_payment.paid_amount >= monthly_payment.get_total_amount_due():
            monthly_payment.payment_status = 'paid'
        elif monthly_payment.paid_amount > 0:
            monthly_payment.payment_status = 'partial'
        else:
            monthly_payment.payment_status = 'pending'
        monthly_payment.save()
        
        return JsonResponse({'success': True, 'message': 'Payment record deleted'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_payment_record_details(request, record_id):
    """Get details of a specific payment record for editing"""
    try:
        record = get_object_or_404(PaymentRecord, id=record_id)
        
        return JsonResponse({
            'success': True,
            'record': {
                'id': record.id,
                'amount': str(record.payment_amount),
                'date': record.payment_date.strftime('%Y-%m-%d'),
                'method': record.payment_method,
                'method_display': record.get_payment_method_display(),
                'reference_number': record.reference_number or '',
                'notes': record.notes or '',
                'created_by': record.created_by.get_full_name() if record.created_by else 'Unknown',
                'created_at': record.created_at.strftime('%Y-%m-%d %H:%M')
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_monthly_payment_records(request, payment_id):
    """Get all payment records for a monthly payment"""
    try:
        monthly_payment = get_object_or_404(MonthlyPayment, id=payment_id)
        records = PaymentRecord.objects.filter(monthly_payment=monthly_payment).order_by('-payment_date')
        
        records_data = []
        for record in records:
            records_data.append({
                'id': record.id,
                'amount': str(record.payment_amount),
                'date': record.payment_date.strftime('%d %b %Y'),
                'method': record.payment_method,
                'method_display': record.get_payment_method_display(),
                'reference_number': record.reference_number or '',
                'notes': record.notes or '',
                'created_by': record.created_by.get_full_name() if record.created_by else 'Unknown',
                'created_at': record.created_at.strftime('%d %b %Y %H:%M')
            })
        
        return JsonResponse({
            'success': True,
            'payment': {
                'id': monthly_payment.id,
                'room_number': monthly_payment.room.number,
                'month': monthly_payment.month.strftime('%B %Y'),
                'total_due': str(monthly_payment.get_total_amount_due()),
                'paid_amount': str(monthly_payment.paid_amount),
                'remaining': str(monthly_payment.get_total_remaining()),
                'status': monthly_payment.payment_status
            },
            'records': records_data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def get_payments_by_month(request):
    """Get all monthly payments for a specific month"""
    try:
        month_str = request.GET.get('month')
        if not month_str:
            return JsonResponse({'success': False, 'message': 'Month required'}, status=400)
        
        month = datetime.strptime(month_str, '%Y-%m-%d').date()
        
        # Get all monthly payments for this month
        payments = MonthlyPayment.objects.filter(month=month).select_related('room', 'guest').order_by('room__number')
        
        payments_data = []
        for payment in payments:
            # Show all payments, but indicate which are already paid
            payments_data.append({
                'id': payment.id,
                'room_number': payment.room.number,
                'tenant_name': payment.guest.full_name if payment.guest else 'No Tenant',
                'total_due': str(payment.get_total_amount_due()),
                'paid': str(payment.paid_amount),
                'remaining': str(payment.get_total_remaining()),
                'status': payment.payment_status,
                'status_display': payment.get_payment_status_display()
            })
        
        return JsonResponse({
            'success': True,
            'payments': payments_data,
            'month': month.strftime('%B %Y')
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def generate_single_room_bill(request):
    """Generate electricity bill for a single room from rental ledger"""
    try:
        from calendar import monthrange
        
        room_id = request.POST.get('room_id')
        month_str = request.POST.get('month')
        ending_reading_str = request.POST.get('ending_reading')
        rate_per_unit_str = request.POST.get('rate_per_unit')
        
        # Validate required fields
        if not room_id:
            return JsonResponse({'success': False, 'message': 'Room ID is required'}, status=400)
        if not month_str:
            return JsonResponse({'success': False, 'message': 'Month is required'}, status=400)
        if not ending_reading_str:
            return JsonResponse({'success': False, 'message': 'Meter reading is required'}, status=400)
        
        # Parse numeric fields
        try:
            from decimal import Decimal
            ending_reading = Decimal(str(ending_reading_str))
            rate_per_unit = _configured_electricity_rate()
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Invalid numeric input'}, status=400)
        if not _requested_electricity_rate_matches_configured(rate_per_unit_str):
            return JsonResponse({'success': False, 'message': 'Electricity rate is set by the server and cannot be overridden'}, status=400)
        
        # Get room
        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Room not found'}, status=404)
        
        # Parse month
        try:
            if len(month_str) == 10 and month_str[4] == '-' and month_str[7] == '-':
                month = datetime.strptime(month_str, '%Y-%m-%d').date()
            elif len(month_str) == 7 and month_str[4] == '-':
                month = datetime.strptime(month_str, '%Y-%m').date()
            else:
                return JsonResponse({'success': False, 'message': f'Invalid month format: {month_str}'}, status=400)
        except ValueError as e:
            return JsonResponse({'success': False, 'message': f'Error parsing month: {str(e)}'}, status=400)
        
        # Get previous bill to determine starting reading
        previous_bill = ElectricityBill.objects.filter(
            room=room,
            month__lt=month
        ).order_by('-month').first()
        
        starting_reading = previous_bill.ending_reading if previous_bill else Decimal('13.0')
        
        # Validate readings
        if ending_reading < starting_reading:
            return JsonResponse({
                'success': False,
                'message': f'Ending reading ({ending_reading}) must be greater than or equal to starting reading ({starting_reading})'
            }, status=400)
        
        # Calculate bill
        units_consumed = ending_reading - starting_reading
        bill_amount = units_consumed * rate_per_unit
        
        # Calculate due date (last day of month)
        last_day = monthrange(month.year, month.month)[1]
        due_date = month.replace(day=last_day)
        
        # Get active guest
        guest = Guest.objects.filter(room=room, is_active=True).first()
        
        # Create or update bill
        bill, created = ElectricityBill.objects.get_or_create(
            room=room,
            month=month,
            defaults={
                'guest': guest,
                'starting_reading': starting_reading,
                'ending_reading': ending_reading,
                'units_consumed': units_consumed,
                'rate_per_unit': rate_per_unit,
                'bill_amount': bill_amount,
                'due_date': due_date,
            }
        )
        
        if not created:
            if Decimal(str(bill.rate_per_unit)) != rate_per_unit:
                return JsonResponse({
                    'success': False,
                    'message': 'This bill already exists at a different electricity rate and was not changed.',
                }, status=409)
            # Update existing bill
            bill.guest = guest
            bill.starting_reading = starting_reading
            bill.ending_reading = ending_reading
            bill.units_consumed = units_consumed
            bill.rate_per_unit = rate_per_unit
            bill.bill_amount = bill_amount
            bill.due_date = due_date
            bill.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Electricity bill {"created" if created else "updated"} for {room.number}',
            'bill': {
                'id': bill.id,
                'room': room.number,
                'month': month.strftime('%B %Y'),
                'starting_reading': str(starting_reading),
                'ending_reading': str(ending_reading),
                'units_consumed': str(units_consumed),
                'rate_per_unit': str(rate_per_unit),
                'bill_amount': str(bill_amount),
                'status': bill.bill_status,
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error generating bill: {str(e)}'
        }, status=400)
