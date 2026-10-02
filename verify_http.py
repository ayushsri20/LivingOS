import requests
import re

try:
    response = requests.get('http://127.0.0.1:8003/manage-guests/')
    content = response.text
    
    # Look for the badge: <span class="badge bg-primary">5 Active Residents</span>
    # Or similar structure.
    # Let's just regex for "Active Residents"
    match = re.search(r'(\d+)\s+Active Residents', content)
    if match:
        print(f"VERIFIED COUNT: {match.group(1)}")
    else:
        print("COULD NOT FIND COUNT. Snippet:")
        print(content[:500]) # First 500 chars
        # Search for "Residents" generally
        print("Residents matches:", re.findall(r'.{20}Residents.{20}', content))

except Exception as e:
    print(f"Error: {e}")
