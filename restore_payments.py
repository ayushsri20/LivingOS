import os
import re

backup_path = "rental/templates/manage_payments.html.backup"
target_path = "rental/templates/manage_payments.html"

if os.path.exists(backup_path):
    with open(backup_path, 'rb') as f:
        content = f.read()
    
    # Fix NBSP
    fixed = content.replace(b'\xc2\xa0', b' ')
    
    # Fix Syntax Errors
    fixed = re.sub(b'current_filters.status==', b'current_filters.status == ', fixed)
    fixed = re.sub(b"=='all'", b" == 'all'", fixed)
    fixed = re.sub(b"=='pending'", b" == 'pending'", fixed)
    fixed = re.sub(b"=='partial'", b" == 'partial'", fixed)
    fixed = re.sub(b"=='paid'", b" == 'paid'", fixed)
    fixed = re.sub(b"=='overdue'", b" == 'overdue'", fixed)
    fixed = re.sub(b'current_filters.building==', b'current_filters.building == ', fixed)
    
    with open(target_path, 'wb') as f:
        f.write(fixed)
    print(f"Restored and fixed {target_path}")

    # Also fix guests and electricity from their current state (already fixed in previous attempts? No, I overwrote them?)
    # Wait, I didn't overwrite guests/electricity with "SANITY CHECK". They should be fine if previous scripts ran.
    # But I'll fix them again just in case.
    
    for p in ['rental/templates/manage_guests.html', 'rental/templates/manage_electricity_bills.html']:
        if os.path.exists(p):
            with open(p, 'rb') as f:
                raw = f.read()
            clean = raw.replace(b'\xc2\xa0', b' ')
            # Fix duplicate tags if any (from sed errors?)
            # No, sed likely worked or failed silently.
            # I'll just write clean.
            with open(p, 'wb') as f:
                f.write(clean)
            print(f"Sanitized {p}")

else:
    print("Backup not found!")

