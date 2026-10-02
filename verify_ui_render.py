import requests
import time
import re

BASE_URL = "http://127.0.0.1:8003"
LOGIN_URL = f"{BASE_URL}/login/"
DASHBOARD_URL = f"{BASE_URL}/dashboard/"
GUESTS_URL = f"{BASE_URL}/manage-guests/"
BILLS_URL = f"{BASE_URL}/manage-electricity-bills/"

def verify_ui():
    session = requests.Session()
    
    # 1. Login
    print(f"Logging in...")
    # Get CSRF token first
    login_page = session.get(LOGIN_URL)
    scrf_token = login_page.cookies['csrftoken']
    
    login_data = {
        'username': 'admin',
        'password': 'admin',
        'csrfmiddlewaretoken': scrf_token,
        'next': '/dashboard/'
    }
    
    headers = {'Referer': LOGIN_URL}
    response = session.post(LOGIN_URL, data=login_data, headers=headers)
    
    if response.url == DASHBOARD_URL:
        print("✅ Login Successful")
    else:
        print(f"❌ Login Failed (Redirected to {response.url})")
        return

    # 2. Check Dashboard
    start = time.time()
    resp = session.get(DASHBOARD_URL)
    duration = time.time() - start
    
    print(f"\n[DASHBOARD] Status: {resp.status_code} | Time: {duration:.2f}s")
    if resp.status_code == 200:
        if "Room F-106" in resp.text:
            print("   ✅ Found 'Room F-106' (Full dataset loaded)")
        else:
            print("   ⚠️  'Room F-106' not found in HTML (Truncated?)")
    else:
        print(f"   ❌ Failed to load")

    # 3. Check Guests
    start = time.time()
    resp = session.get(GUESTS_URL)
    duration = time.time() - start
    
    print(f"\n[TENANCY REGISTER] Status: {resp.status_code} | Time: {duration:.2f}s")
    if resp.status_code == 200:
        # Check active residents count
        # Looking for <div class="badge-premium badge-success">80 Active Residents</div>
        match = re.search(r'badge-success">\s*(\d+)\s*Active', resp.text)
        if match:
            count = match.group(1)
            print(f"   ✅ Active Residents Count: {count}")
        else:
            print("   ⚠️  Could not find 'Active Residents' count")
            
        # Check for paginated or long list
        cards = resp.text.count('class="card-premium guest-card"')
        print(f"   ℹ️  Guest Cards Rendered: {cards}")
    else:
        print(f"   ❌ Failed to load")

    # 4. Check Bills
    start = time.time()
    resp = session.get(BILLS_URL)
    duration = time.time() - start
    
    print(f"\n[UTILITY MATRIX] Status: {resp.status_code} | Time: {duration:.2f}s")
    if resp.status_code == 200:
        # Check for rows in the table
        rows = resp.text.count('<tr')
        print(f"   ℹ️  Table Rows: {rows}")
        if "generate-bills-modal" in resp.text or "Generate Monthly Bills" in resp.text:
             print("   ✅ Modal HTML present")
    else:
        print(f"   ❌ Failed to load")

if __name__ == "__main__":
    verify_ui()
