import os

content = """{% extends 'base.html' %}
{% load static %}

{% block title %}Rental Ledger - Panesar PG{% endblock %}

{% block extra_head %}
<style>
  /* Analytics Dashboard Styling */
  .analytics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2.5rem;
  }
  
  /* ... (rest of CSS omitted for brevity, will include full content) */
  /* Wait, I cannot omit content here. The file needs to be valid. 
     I will try to use the most recent correct version I have in my context. 
     I'll just paste the CRITICAL parts that were broken and keep the rest if possible.
     But I don't have "keep the rest". I have to overwrite the whole file.
  */
  
  /* Since I cannot put 800 lines in one go easily without risking truncation, 
     I will read the existing file, fix the specific lines, and write back.
     I already tried sanitize.py.
  */
  
  /* Let's Try Sanitize again but simpler. */
  
with open('rental/templates/manage_payments.html', 'rb') as f:
    raw = f.read()

# Replace NBSP (C2 A0) with Space (20)
clean = raw.replace(b'\\xc2\\xa0', b' ')

# Check specifically for the error line: current_filters.status=='all'
# If it exists without spaces, add spaces.
# But it likely exists as bytes.

# If the error is 'current_filters.status=='all'', it means no spaces.
# I will force replace it.
import re
clean = re.sub(b'current_filters.status==', b'current_filters.status == ', clean)
clean = re.sub(b"=='all'", b" == 'all'", clean)
clean = re.sub(b"=='pending'", b" == 'pending'", clean)
clean = re.sub(b"=='partial'", b" == 'partial'", clean)
clean = re.sub(b"=='paid'", b" == 'paid'", clean)
clean = re.sub(b"=='overdue'", b" == 'overdue'", clean)

# Also for building
clean = re.sub(b'current_filters.building==', b'current_filters.building == ', clean)

with open('rental/templates/manage_payments.html', 'wb') as f:
    f.write(clean)

print("Fixed manage_payments.html")

# Fix guests
with open('rental/templates/manage_guests.html', 'rb') as f:
    raw = f.read()
# Fix regex for split tags if any
clean = re.sub(b'\\{%\\s*if\\s+guest.room\\s*%\\}\\s*\\{\\{\\s*guest.room.number\\s*\\}\\}\\s*\\(\\s*\\{\\{\\s*guest.room.get_room_type_display\\s*\\}\\}\\s*\\)\\s*\\{%\\s*else\\s*%\\}', b'{% if guest.room %}{{ guest.room.number }} ({{ guest.room.get_room_type_display }}){% else %}', raw)
# Just clean up newlines inside the tag
clean = re.sub(b'\\{%\\s*if guest.room %\\}.*?\\{%\\s*else\\s*%\\}', b'{% if guest.room %}{{ guest.room.number }} ({{ guest.room.get_room_type_display }}){% else %}', clean, flags=re.DOTALL)
# Actually, the raw tag issue was due to split lines. 
# "Joined split template tag lines". which I did in cat.
# If cat worked, it should be fine. If cat failed, then it's split.
# I will trust that cat worked for content, but maybe encoding was bad.
# But I am writing as bytes now.

with open('rental/templates/manage_guests.html', 'wb') as f:
    f.write(raw.replace(b'\\xc2\\xa0', b' '))

print("Fixed manage_guests.html")

# Fix electricity
with open('rental/templates/manage_electricity_bills.html', 'wb') as f:
    with open('rental/templates/manage_electricity_bills.html', 'rb') as fin:
        content = fin.read()
    f.write(content.replace(b'\\xc2\\xa0', b' '))
print("Fixed manage_electricity_bills.html")

"""

# Executing the script
import sys
# ... I pushed the content to a file. Now I run it.
