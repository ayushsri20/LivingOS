
import os

file_path = 'rental/templates/manage_payments_v2.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix status filter syntax errors (global replace for known patterns)
content = content.replace("current_filters.status=='all'", "current_filters.status == 'all'")
content = content.replace("current_filters.status=='pending'", "current_filters.status == 'pending'")
content = content.replace("current_filters.status=='partial'", "current_filters.status == 'partial'")
content = content.replace("current_filters.status=='paid'", "current_filters.status == 'paid'")
content = content.replace("current_filters.status=='overdue'", "current_filters.status == 'overdue'")

# Fix building filter split lines
# The pattern is:
#         <option value="{{ building }}" {% if current_filters.building==building %}selected{% endif %}>Building {{
#           building }}</option>

# We want to replace it with:
#         <option value="{{ building }}" {% if current_filters.building == building %}selected{% endif %}>Building {{ building }}</option>

# Note: The split might have different whitespace. Let's try to find the split string and replace it.
split_string = '        <option value="{{ building }}" {% if current_filters.building==building %}selected{% endif %}>Building {{\n          building }}</option>'
fixed_string = '        <option value="{{ building }}" {% if current_filters.building == building %}selected{% endif %}>Building {{ building }}</option>'

if split_string in content:
    content = content.replace(split_string, fixed_string)
    print("Fixed split building tag.")
else:
    print("Split building tag not found exactly as expected. Trying partial match...")
    # Try just replacing the key parts if exact match fails
    content = content.replace("current_filters.building==building", "current_filters.building == building")
    # Fix the split specifically
    content = content.replace("Building {{\n          building }}", "Building {{ building }}")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Finished forcing fixes on manage_payments_v2.html")
