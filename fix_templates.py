
import re
import os

def fix_payments():
    with open('rental/templates/manage_payments.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix: ensure spaces around == in django templates
    # Regex lookbehind/ahead might be complex, simple replacement for specific known bad patterns is safer
    # Known bad patterns:
    # current_filters.status=='all'
    # current_filters.status=='pending'
    # ...
    # current_filters.building==building
    
    # Strategy: Replace "=='" with " == '" and "==" with " == " inside {% if %} logic
    # But be careful not to break JS
    
    # Specific known bad lines from previous grep
    # <option value="all" {% if current_filters.status=='all' %}selected{% endif %}>
    
    fixed = content.replace("current_filters.status=='all'", "current_filters.status == 'all'")
    fixed = fixed.replace("current_filters.status=='pending'", "current_filters.status == 'pending'")
    fixed = fixed.replace("current_filters.status=='partial'", "current_filters.status == 'partial'")
    fixed = fixed.replace("current_filters.status=='paid'", "current_filters.status == 'paid'")
    fixed = fixed.replace("current_filters.status=='overdue'", "current_filters.status == 'overdue'")
    
    # Also building
    fixed = fixed.replace("current_filters.building==building", "current_filters.building == building")
    
    # Fix split tags in payments too!
    fixed = re.sub(r'\{\{\s*\n\s*', '{{ ', fixed)
    fixed = re.sub(r'\{%\s*\n\s*', '{% ', fixed)
    fixed = fixed.replace('\u00A0', ' ')
    
    with open('rental/templates/manage_payments_v2.html', 'w', encoding='utf-8') as f:
        f.write(fixed)
    print("Fixed manage_payments_v2.html")

def fix_guests():
    with open('rental/templates/manage_guests.html', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Fix split tags
    # Pattern: 
    # {% if guest.room %}{{ guest.room.number }} ({{ guest.room.get_room_type_display }}){%\
    #       else %}—{% endif %}
    
    # We will use regex to join split tags
    # Looking for {%\s*\n\s*
    
    fixed = re.sub(r'\{%\s*\n\s*', '{% ', content)
    fixed = re.sub(r'\{\{\s*\n\s*', '{{ ', fixed)
    
    # Also remove any non-breaking spaces that might be causing issues
    fixed = fixed.replace('\u00A0', ' ')
    
    with open('rental/templates/manage_guests_v2.html', 'w', encoding='utf-8') as f:
        f.write(fixed)
    print("Fixed manage_guests_v2.html")

def fix_bills():
    with open('rental/templates/manage_electricity_bills.html', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Fix split tags
    # {{ data.latest_reading|floatformat:0 }} might be split
    
    fixed = re.sub(r'\{\{\s*\n\s*', '{{ ', content)
    fixed = re.sub(r'\{%\s*\n\s*', '{% ', fixed)
     # Also remove any non-breaking spaces
    fixed = fixed.replace('\u00A0', ' ')

    with open('rental/templates/manage_electricity_bills_v2.html', 'w', encoding='utf-8') as f:
        f.write(fixed)
    print("Fixed manage_electricity_bills_v2.html")

if __name__ == "__main__":
    fix_payments()
    fix_guests()
    fix_bills()
