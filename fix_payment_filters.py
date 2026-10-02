
import os

file_path = 'rental/templates/manage_payments_v2.html'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if 'value="{{ building }}"' in line:
        # Reconstruct the line cleanly
        indent = "        " # 8 spaces
        new_lines.append(f'{indent}<option value="{{{{ building }}}}" {{% if current_filters.building == building %}}selected{{% endif %}}>{{{{ building }}}}</option>\n')
    else:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Fixed manage_payments_v2.html via python script")
