import os
import django
import random
from datetime import date, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Guest, Room, Booking

def populate_data():
    print("Populating smart test data...")
    
    # Preset names for realism
    names = [
        ("Aarav", "Sharma"), ("Vivaan", "Patel"), ("Aditya", "Gupta"), ("Vihaan", "Singh"),
        ("Arjun", "Kumar"), ("Sai", "Reddy"), ("Reyansh", "Das"), ("Ayaan", "Mehta")
    ]
    
    # Get some rooms (Using M1-M3 for active demo)
    # Filter for known clean rooms locally if needed, but db should be clean now.
    rooms = list(Room.objects.filter(is_available=True).order_by('number'))
    
    if not rooms:
        print("No rooms available! Please ensure rooms exist.")
        return

    # Create 5 Active Guests
    created_count = 0
    today = timezone.now().date()
    
    for i in range(min(5, len(rooms))):
        first, last = names[i]
        room = rooms[i]
        
        # Stagger check-in dates
        check_in = today - timedelta(days=random.randint(1, 30))
        
        guest = Guest.objects.create(
            first_name=first,
            last_name=last,
            email=f"{first.lower()}.{last.lower()}@example.com",
            phone=f"98765432{i:02d}",
            room=room,
            room_id=room.id, # redundancy for safety
            check_in_date=check_in,
            occupancy_preference='double', # explicit lowercase
            student_college='Imperial College',
            is_active=True
        )
        
        # Update room status
        room.is_available = (room.current_occupancy + 1 < room.capacity)
        room.save()
        
        # Create a Booking record (if system uses it, good for reports)
        Booking.objects.create(
            customer_name=f"{first} {last}",
            room=room,
            check_in=check_in,
            check_out=check_in + timedelta(days=180), # 6 months default
            is_active=True
        )
        
        print(f"Created Active Guest: {first} {last} in {room.number}")
        created_count += 1

    # Create 1 Archived Guest (History Test)
    if len(rooms) > 5:
        room = rooms[5]
        first, last = "Ex", "Tenant"
        check_in = today - timedelta(days=60)
        check_out = today - timedelta(days=10)
        
        guest = Guest.objects.create(
            first_name=first,
            last_name=last,
            email="ex.tenant@example.com",
            phone="9998887776",
            room=room, # Historical link
            check_in_date=check_in,
            check_out_date=check_out,
            occupancy_preference='single',
            is_active=False
        )
        
        # Room is free since he left
        # We don't mark room unavailable.
        
        print(f"Created Archived Guest: {first} {last} (Values -> Check-out: {check_out})")
        created_count += 1

    print(f"\nSuccessfully populated {created_count} guests.")

if __name__ == '__main__':
    populate_data()
