import requests
import re
import os
import django
from django.conf import settings
from datetime import date, timedelta
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()
from rental.models import Guest, Room

def run_reassignment_test():
    session = requests.Session()
    base_url = "http://127.0.0.1:8003"
    
    print("="*60)
    print("      ROOM REASSIGNMENT & LONG-TERM TEST")
    print("="*60)
    
    # 1. Login
    print("[1] Logging in...")
    login_page = session.get(f"{base_url}/login/")
    csrf_token = login_page.cookies.get('csrftoken')
    if not csrf_token:
        match = re.search(r'name="csrfmiddlewaretoken" value="(.+?)"', login_page.text)
        if match: csrf_token = match.group(1)
    
    login_data = {'username': 'admin', 'password': 'admin', 'csrfmiddlewaretoken': csrf_token}
    session.post(f"{base_url}/login/", data=login_data, headers={'Referer': f"{base_url}/login/"})
    csrf_token = session.cookies.get('csrftoken')

    # 2. Select Test Room
    # We need a completely empty room to be sure.
    # occupancy is a property, so filter in Python
    all_rooms = Room.objects.filter(is_available=True)
    test_room = None
    for r in all_rooms:
        if r.current_occupancy == 0:
            test_room = r
            break
            
    if not test_room: 
        print("❌ FATAL: No empty rooms available.")
        return
    print(f"✅ Selected Test Room: {test_room.number} (Empty)")

    # 3. Tenant A: "Old Resident" (Check-in 2 months ago)
    check_in_date = date.today() - timedelta(days=60)
    print(f"\n[2] Registering Tenant A (Old Resident)...")
    print(f"    - Check-in Date: {check_in_date}")
    
    data_a = {
        'first_name': 'Tenant', 'last_name': 'Alpha',
        'phone': '1111111111', 'email': 'alpha@test.com',
        'room_id': test_room.id,
        'check_in_date': str(check_in_date),
        'agreed_rent': '7000', 'occupancy_preference': 'double', 'occupation': 'student',
        'csrfmiddlewaretoken': csrf_token
    }
    resp = session.post(f"{base_url}/api/guest/add/", data=data_a, headers={'Referer': f"{base_url}/manage-guests/"})
    
    if resp.status_code != 200:
        print(f"❌ Tenant A Registration Failed: {resp.text}")
        return
        
    guest_a = Guest.objects.get(first_name='Tenant', last_name='Alpha')
    print(f"✅ Tenant A Registered (ID: {guest_a.id}). Room Occupancy: {test_room.current_occupancy + 1}")

    # 4. Checkout Tenant A (Today)
    print(f"\n[3] Checking out Tenant A...")
    checkout_url = f"{base_url}/api/guest/{guest_a.id}/checkout/"
    session.post(checkout_url, data={'csrfmiddlewaretoken': csrf_token}, headers={'Referer': f"{base_url}/manage-guests/"})
    
    guest_a.refresh_from_db()
    test_room.refresh_from_db()
    
    if not guest_a.is_active and guest_a.check_out_date == date.today():
        print(f"✅ Tenant A Archived. Check-out Date: {guest_a.check_out_date}")
        print(f"✅ Room {test_room.number} Status: Available (Occupancy: {test_room.current_occupancy})")
    else:
        print("❌ Checkout Failed.")
        return

    # 5. Tenant B: "New Resident" (Check-in Today)
    print(f"\n[4] Registering Tenant B (New Resident) into SAME Room {test_room.number}...")
    data_b = {
        'first_name': 'Tenant', 'last_name': 'Beta',
        'phone': '2222222222', 'email': 'beta@test.com',
        'room_id': test_room.id, # SAME ROOM ID
        'check_in_date': str(date.today()),
        'agreed_rent': '7500', # Higher rent maybe?
        'occupancy_preference': 'double', 'occupation': 'professional',
        'csrfmiddlewaretoken': csrf_token
    }
    
    resp_b = session.post(f"{base_url}/api/guest/add/", data=data_b, headers={'Referer': f"{base_url}/manage-guests/"})
    
    if resp_b.status_code != 200:
        print(f"❌ Tenant B Reassignment Failed: {resp_b.text}")
        return

    guest_b = Guest.objects.get(first_name='Tenant', last_name='Beta')
    test_room.refresh_from_db()
    
    if guest_b.room == test_room and guest_b.is_active:
        print(f"✅ REASSIGNMENT SUCCESSFUL!")
        print(f"   - Room {test_room.number} is now occupied by Tenant B (ID: {guest_b.id}).")
        print(f"   - Current Occupancy: {test_room.current_occupancy}")
        print(f"   - Tenant A is still Archived (History preserved).")
    else:
        print("❌ Reassignment Logic Failed.")

    # Cleanup
    guest_a.delete()
    guest_b.delete()
    print("\nTest Data Cleaned up.")

if __name__ == "__main__":
    run_reassignment_test()
