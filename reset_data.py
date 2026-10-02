import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from rental.models import Guest, Booking, PaymentRecord, MonthlyPayment, ElectricityBill, Room

def reset_data():
    print("WARNING: internal data reset initiated...")
    
    # 1. Delete dependent data first
    bills_count = ElectricityBill.objects.all().delete()[0]
    payments_count = PaymentRecord.objects.all().delete()[0]
    monthly_count = MonthlyPayment.objects.all().delete()[0]
    bookings_count = Booking.objects.all().delete()[0]
    
    # 2. Delete Guests
    guests_count = Guest.objects.all().delete()[0]
    
    # 3. Reset Rooms (but don't delete them)
    rooms = Room.objects.all()
    for room in rooms:
        room.is_available = True
        # room.agreed_rent = 7000 # Optional: reset rent adjustments? Let's keep them if they were set on the room level.
        # Actually, let's reset to defaults to be "perfectly clean"
        room.save()
        
    print(f"Deleted:")
    print(f" - {guests_count} Guests")
    print(f" - {bookings_count} Bookings")
    print(f" - {payments_count} Payment Records")
    print(f" - {bills_count} Electricity Bills")
    print(f"Reset {rooms.count()} Rooms to available.")
    print("\nData reset complete. Admin users and Rooms preserved.")

if __name__ == '__main__':
    reset_data()
