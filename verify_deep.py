import requests
import re
import os
import django
from django.conf import settings
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()
from rental.models import Guest, Room

def run_verification():
    session = requests.Session()
    base_url = "http://127.0.0.1:8003"
    
    # 1. Login
    print(f"Logging in to {base_url}...")
    login_page = session.get(f"{base_url}/login/")
    csrf_token = login_page.cookies.get('csrftoken')
    if not csrf_token:
        match = re.search(r'name="csrfmiddlewaretoken" value="(.+?)"', login_page.text)
        if match:
            csrf_token = match.group(1)
    
    login_data = {
        'username': 'admin',
        'password': 'admin',
        'csrfmiddlewaretoken': csrf_token
    }
    
    post = session.post(f"{base_url}/login/", data=login_data, headers={'Referer': f"{base_url}/login/"})
    if post.status_code not in [200, 302] or "dashboard" not in post.url:
        print("LOGIN FAILED")
        return

    # Update CSRF from session
    csrf_token = session.cookies.get('csrftoken')

    # 2. PROOF OF LIFE: Check HTML for data
    print("\n[CHECK 1] Verifying Data Presence...")
    resp = session.get(f"{base_url}/manage-guests/")
    if "Aarav Sharma" in resp.text:
        print("PASS: 'Aarav Sharma' found in HTML.")
    else:
        print("FAIL: 'Aarav Sharma' NOT found in HTML.")

    # 3. FUNCTIONAL TEST: Create Guest -> Checkout
    print("\n[CHECK 2] Testing 'End Tenancy' Workflow...")
    
    # Create Test Guest
    # Need a room. Let's use Room 10 (A-110) which should be empty.
    room = Room.objects.last() # A-1010 likely
    print(f"Using Room: {room}")
    
    create_data = {
        'first_name': 'TestBot',
        'last_name': 'Automated',
        'phone': '0000000000',
        'email': 'testbot@example.com',
        'room_id': room.id,
        'check_in_date': str(date.today()),
        'agreed_rent': '7000',
        'occupancy_preference': 'double',
        'occupation': 'student',
        'csrfmiddlewaretoken': csrf_token
    }
    
    print("Creating Guest 'TestBot'...")
    # Add guest usually expects files now? The view handles request.FILES.get(...), so empty might be okay if not strict.
    # checking view... it says 'if request.method == "POST": ... aadhar_front = request.FILES.get...' 
    # It doesn't strictly validate files are present in the view logic I saw earlier (it was optional in model).
    
    # The URL in template is '{% url "add_guest" %}' which maps to /api/guest/add/
    create_resp = session.post(f"{base_url}/api/guest/add/", data=create_data, headers={'Referer': f"{base_url}/manage-guests/"})
    print(f"Create Response: {create_resp.status_code}")
    print(create_resp.text[:200])
    
    try:
        test_guest = Guest.objects.get(first_name='TestBot')
        print(f"PASS: Guest 'TestBot' created with ID {test_guest.id}.")
    except Guest.DoesNotExist:
        print("FAIL: Guest 'TestBot' was NOT created.")
        return

    # 4. Perform Checkout
    print(f"Attempting Checkout for ID {test_guest.id}...")
    checkout_url = f"{base_url}/api/guest/{test_guest.id}/checkout/"
    checkout_resp = session.post(checkout_url, data={'csrfmiddlewaretoken': csrf_token}, headers={'Referer': f"{base_url}/manage-guests/"})
    
    print(f"Checkout Status: {checkout_resp.status_code}")
    print(f"Checkout Body: {checkout_resp.text}")
    
    test_guest.refresh_from_db()
    if not test_guest.is_active and test_guest.check_out_date:
        print(f"PASS: Guest 'TestBot' is now ARCHIVED. Check-out Date: {test_guest.check_out_date}")
    else:
        print(f"FAIL: Guest 'TestBot' is still ACTIVE.")

    # Cleanup
    test_guest.delete()
    print("Test Guest deleted.")

if __name__ == "__main__":
    run_verification()
