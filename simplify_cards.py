#!/usr/bin/env python3
"""
Simplify room cards in manage_payments.html
"""

# Read the file
with open('rental/templates/manage_payments.html', 'r') as f:
    lines = f.readlines()

# Find the section to replace (lines 654-733)
new_section = '''      <!-- Payment Summary (Simplified & User-Friendly) -->
      <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); padding: 1.5rem; border-radius: 0.75rem; margin-bottom: 1.25rem;">
        {% widthratio payment.paid_amount payment.get_total_amount_due 100 as progress_percent %}
        
        <!-- Key Metrics in 3 Columns -->
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; margin-bottom: 1.25rem;">
          <div style="text-align: center;">
            <div style="font-size: 0.7rem; color: var(--text-muted); font-weight: 700; margin-bottom: 0.5rem;">TOTAL DUE</div>
            <div style="font-size: 1.5rem; font-weight: 900; color: var(--primary);">₹{{ payment.get_total_amount_due }}</div>
          </div>
          <div style="text-align: center;">
            <div style="font-size: 0.7rem; color: var(--text-muted); font-weight: 700; margin-bottom: 0.5rem;">PAID</div>
            <div style="font-size: 1.5rem; font-weight: 900; color: #10b981;">₹{{ payment.paid_amount }}</div>
          </div>
          <div style="text-align: center;">
            <div style="font-size: 0.7rem; color: var(--text-muted); font-weight: 700; margin-bottom: 0.5rem;">REMAINING</div>
            <div style="font-size: 1.5rem; font-weight: 900; color: {% if payment.get_total_remaining > 0 %}#ef4444{% else %}#10b981{% endif %};">₹{{ payment.get_total_remaining }}</div>
          </div>
        </div>
        
        <!-- Progress Bar -->
        <div style="background: rgba(255,255,255,0.6); border-radius: 1rem; height: 0.625rem; overflow: hidden; margin-bottom: 0.5rem;">
          <div style="background: linear-gradient(90deg, var(--primary), #10b981); height: 100%; width: {{ progress_percent }}%; transition: width 0.3s ease;"></div>
        </div>
        <div style="text-align: center; font-size: 0.75rem; color: var(--text-muted); font-weight: 700;">
          {{ progress_percent }}% Completed
        </div>
      </div>
    </div>

'''

# Replace lines 653-733 (0-indexed: 652-732)
new_lines = lines[:653] + [new_section] + lines[733:]

# Write back
with open('rental/templates/manage_payments.html', 'w') as f:
    f.writelines(new_lines)

print("✅ Simplified room cards successfully!")
print(f"   Replaced {733-653} lines with simplified version")
