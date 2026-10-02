
import os
import re

# Paths
base_dir = '/Users/ayush/hotel_rental/hotel_project'
os.chdir(base_dir)

backup_path = "rental/templates/manage_payments.html.backup"
target_path = "rental/templates/manage_payments.html"

# Restore manage_payments.html
if os.path.exists(backup_path):
    print(f"Reading backup from {backup_path}")
    with open(backup_path, 'rb') as f:
        content = f.read()
    
    # Fix NBSP
    fixed = content.replace(b'\xc2\xa0', b' ')
    
    # Fix Syntax Errors explicitly in manage_payments.html
    # Ensure spaces around == in filter tags
    # This regex handles existing spaces or no spaces
    # It replaces `==` with ` == ` and then reduces multiple spaces to one if needed (simplified logic here)
    
    # Crude but effective: replace specific known failure patterns
    # e.g. `status=='all'` -> `status == 'all'`
    
    # Pattern: status=='all' or status=='pending' etc
    for val in [b"'all'", b"'pending'", b"'partial'", b"'paid'", b"'overdue'"]:
        pattern = b"status==" + val
        replacement = b"status == " + val
        fixed = fixed.replace(pattern, replacement)
    
    # Pattern: building==building
    fixed = fixed.replace(b"building==building", b"building == building")

    with open(target_path, 'wb') as f:
        f.write(fixed)
    print(f"Restored and fixed {target_path}")
else:
    print(f"Backup {backup_path} not found. Using existing file if available.")
    # If backup missing, try to fix existing file
    if os.path.exists(target_path):
        with open(target_path, 'rb') as f:
            fixed = f.read().replace(b'\xc2\xa0', b' ')
        # Fix syntax
        for val in [b"'all'", b"'pending'", b"'partial'", b"'paid'", b"'overdue'"]:
            pattern = b"status==" + val
            replacement = b"status == " + val
            fixed = fixed.replace(pattern, replacement)
        fixed = fixed.replace(b"building==building", b"building == building")
        
        with open(target_path, 'wb') as f:
            f.write(fixed)
        print(f"Fixed existing {target_path}")

# Sanitize other templates
others = ['rental/templates/manage_guests.html', 'rental/templates/manage_electricity_bills.html']
for p in others:
    if os.path.exists(p):
        with open(p, 'rb') as f:
            raw = f.read()
        clean = raw.replace(b'\xc2\xa0', b' ')
        
        # Check for split tags in manage_guests.html/electricity
        # If specific byte sequences found (split across lines in raw bytes), join them.
        # This is hard without regex on multiline bytes.
        
        # But earlier I used `cat` to write the content which had joined lines.
        # So unless `cat` wrote weird chars, it should be fine.
        # The 'Raw template tags' issue might be due to NBSP making `{% if ... %}` invalid.
        
        with open(p, 'wb') as f:
            f.write(clean)
        print(f"Sanitized {p}")
