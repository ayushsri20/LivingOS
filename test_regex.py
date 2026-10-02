
import re

text = """<option value="{{ building }}" {% if current_filters.building == building %}selected{% endif %}>Building {{
          building }}</option>"""

print(f"Original: {repr(text)}")

fixed = re.sub(r'\{\{\s*\n\s*', '{{ ', text)

print(f"Fixed:    {repr(fixed)}")

if "Building {{ building }}" in fixed:
    print("SUCCESS")
else:
    print("FAILURE")
