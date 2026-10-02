import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from django.contrib.auth.models import User
from rental.models import Room, Guest, Booking
from datetime import date, timedelta
from django.utils import timezone

def setup_full():
    print("Initializing fresh database...")
    
    # 1. Create Superuser
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'admin')
        print("Created superuser 'admin'")

    # 2. Create Rooms (Test Set: M1, M2, M3... just a few for speed, or all 36?)
    # User mentioned "M1, 1-6" in previous context (6 bldgs * 6 rooms = 36).
    # Let's create a representative set for testing.
    # Buildings: M1, 1, 2, 3, 4, 5
    buildings = ['M1', '1', '2', '3', '4', '5']
    floors = ['GF', 'FF', 'SF'] # Assuming 2 rooms per floor? 
    # Actually, previous room names were "A-101", etc.
    # Let's check what the user had. User had "A-101", "102".
    # I will create a standard set "A-101" to "A-106" for verified testing.
    
    print("Creating Rooms...")
    rooms = []
    for i in range(1, 11): # 10 rooms
        room_num = f"A-10{i}"
        room = Room.objects.create(
            number=room_num,
            room_type='double',
            price=7000,
            capacity=2,
            is_available=True
        )
        rooms.append(room)
        print(f" - Created {room_num}")

    # 3. Create Guests
    print("Creating Guests...")
    guests_data = [
        ("Aarav", "Sharma", rooms[0]), # A-101
        ("Vivaan", "Patel", rooms[1]), # A-102
        ("Aditya", "Gupta", rooms[2]), # A-103
        ("Vihaan", "Singh", rooms[0]), # A-101 (Roommate for Aarav)
        ("Arjun", "Kumar", rooms[3]),  # A-104
    ]
    
    # Guest 1: Aarav
    check_in = timezone.now().date() - timedelta(days=30)
    
    for first, last, room in guests_data:
        # Check capacity
        if room.current_occupancy < room.capacity:
            g = Guest.objects.create(
                first_name=first,
                last_name=last,
                email=f"{first.lower()}@example.com",
                phone="9876543210",
                room=room,
                occupancy_preference='double',
                check_in_date=check_in,
                is_active=True
            )
            # Create Booking
            Booking.objects.create(
                customer_name=f"{first} {last}",
                room=room,
                check_in=check_in,
                check_out=check_in + timedelta(days=180),
                is_active=True
            )
            print(f" - Created {first} {last} in {room.number}")
            
            # Update room availability
            if room.current_occupancy >= room.capacity:
                room.is_available = False
                room.save()

    print("Setup complete.")

if __name__ == '__main__':
    setup_full()
