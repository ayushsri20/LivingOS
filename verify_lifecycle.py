import requests
import re
import os
import django
from django.conf import settings
from datetime import date
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()
from rental.models import Guest, Room

def run_lifecycle_test():
    session = requests.Session()
    base_url = "http://127.0.0.1:8003"
    
    print("="*60)
    print("      FULL TENANT LIFECYCLE VERIFICATION REPORT")
    print("="*60)
    
    # 1. Login
    print("[1] Logging in as Admin...")
    login_page = session.get(f"{base_url}/login/")
    csrf_token = login_page.cookies.get('csrftoken')
    if not csrf_token:
        match = re.search(r'name="csrfmiddlewaretoken" value="(.+?)"', login_page.text)
        if match: csrf_token = match.group(1)
    
    login_data = {'username': 'admin', 'password': 'admin', 'csrfmiddlewaretoken': csrf_token}
    post = session.post(f"{base_url}/login/", data=login_data, headers={'Referer': f"{base_url}/login/"})
    
    if "dashboard" not in post.url and post.status_code != 302:
        print("❌ FATAL: Login Failed.")
        return
    print("✅ Login Successful.")
    csrf_token = session.cookies.get('csrftoken')

    # 2. Baseline Stats
    print("\n[2] Establishing Baseline...")
    initial_active = Guest.objects.filter(is_active=True).count()
    print(f"   - Initial Active Guests: {initial_active}")
    
    # Find an empty room
    test_room = Room.objects.filter(is_available=True).first()
    if not test_room:
        print("❌ FATAL: No available rooms for testing.")
        return
    initial_room_occupancy = test_room.current_occupancy
    print(f"   - Selected Room: {test_room.number} (Occupancy: {initial_room_occupancy}/{test_room.capacity})")

    # 3. Entry (Registration)
    print("\n[3] ACTION: Registering New Tenant 'LifeCycle TestUser'...")
    form_data = {
        'first_name': 'LifeCycle',
        'last_name': 'TestUser',
        'phone': '9998887777',
        'email': 'lifecycle@test.com',
        'room_id': test_room.id,
        'check_in_date': str(date.today()),
        'agreed_rent': '7000',
        'occupancy_preference': 'double',
        'occupation': 'student',
        'csrfmiddlewaretoken': csrf_token
    }
    
    resp = session.post(f"{base_url}/api/guest/add/", data=form_data, headers={'Referer': f"{base_url}/manage-guests/"})
    print(f"   - HTTP Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ Registration Failed: {resp.text}")
        return

    # 4. Verify Entry
    print("\n[4] VERIFICATION: Post-Entry State...")
    new_active = Guest.objects.filter(is_active=True).count()
    test_room.refresh_from_db()
    
    guest = Guest.objects.get(first_name='LifeCycle', last_name='TestUser')
    
    failures = []
    if new_active != initial_active + 1:
        failures.append(f"Guest Count did not increment correctly (Expected {initial_active + 1}, Got {new_active})")
    if test_room.current_occupancy != initial_room_occupancy + 1:
        failures.append(f"Room Occupancy did not increment (Expected {initial_room_occupancy + 1}, Got {test_room.current_occupancy})")
    if not guest.is_active:
         failures.append("Guest record is not marked ACTIVE")

    if failures:
        print("❌ INTEGRITY ERROR POST-ENTRY:")
        for f in failures: print(f"   - {f}")
        return
    else:
        print("✅ Data Integrity Confirmed: Guest Active, Room Occupancy Updated.")

    # 5. Dashboard Visual Check (Simulation)
    print("\n[5] VERIFICATION: Dashboard Visibility...")
    dash_resp = session.get(f"{base_url}/dashboard/")
    if "LifeCycle TestUser" in dash_resp.text or str(new_active) in dash_resp.text:
         # Note: Name might not be on dashboard summary, but count should be.
         # Actually checking manage-guests is better for name.
         mg_resp = session.get(f"{base_url}/manage-guests/")
         if "LifeCycle TestUser" in mg_resp.text:
             print("✅ Guest appears on Manage Guests page.")
         else:
             print("❌ Guest NOT found on HTML page.")
    
    # 6. Checkout (End Tenancy)
    print("\n[6] ACTION: Ending Tenancy...")
    checkout_url = f"{base_url}/api/guest/{guest.id}/checkout/"
    co_resp = session.post(checkout_url, data={'csrfmiddlewaretoken': csrf_token}, headers={'Referer': f"{base_url}/manage-guests/"})
    
    print(f"   - HTTP Status: {co_resp.status_code}")

    # 7. Final Verification
    print("\n[7] VERIFICATION: Post-Checkout State...")
    final_active = Guest.objects.filter(is_active=True).count()
    test_room.refresh_from_db()
    guest.refresh_from_db()
    
    failures = []
    if final_active != initial_active:
        failures.append(f"Guest Count did not return to baseline (Expected {initial_active}, Got {final_active})")
    if test_room.current_occupancy != initial_room_occupancy:
         failures.append(f"Room Occupancy did not return to baseline (Expected {initial_room_occupancy}, Got {test_room.current_occupancy})")
    if guest.is_active:
        failures.append("Guest is still marked ACTIVE in DB")
    if not guest.check_out_date:
        failures.append("Check-out date was not set")

    if failures:
        print("❌ INTEGRITY ERROR POST-CHECKOUT:")
        for f in failures: print(f"   - {f}")
    else:
        print("✅ SYSTEM INTEGRITY CONFIRMED 100%")
        print("   - Guest moved to Archive.")
        print("   - Room slot freed.")
        print("   - Active counts balanced.")

    # Cleanup
    guest.delete()
    print("\nTest User Deleted from DB.")

if __name__ == "__main__":
    run_lifecycle_test()
