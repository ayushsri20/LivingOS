# Automatic Monthly Rent Generation Setup

This document explains how the automatic monthly rent generation system works and how to set it up.

## Overview

The hotel rental system now automatically generates monthly rent payments in two ways:

1. **On Guest Check-in**: When a new guest checks in, a monthly payment is automatically created for the current month
2. **Monthly Cron Job**: On the 1st of each month, rent payments are generated for all active guests

---

## 1. Automatic Payment on Check-in

### How it Works
When a guest is created or activated in the system, the `Guest.save()` method automatically:
- Creates a `MonthlyPayment` record for the current month
- Sets the rent amount to the room's price
- Sets status as 'pending'
- Links the payment to both the guest and the room

### Code Location
`rental/models.py` - `Guest.save()` method (lines 209-251)

### No Setup Required
This feature works automatically - no configuration needed!

---

## 2. Monthly Cron Job for Rent Generation

### Management Command
**Command:** `python manage.py generate_monthly_rent`

**Purpose:** Generate monthly rent payments for all active guests

**Options:**
- `--month YYYY-MM-DD`: Generate payments for a specific month (defaults to current month)

**Example Usage:**
```bash
# Generate payments for current month
python manage.py generate_monthly_rent

# Generate payments for March 2026
python manage.py generate_monthly_rent --month 2026-03-01
```

### Setting Up Cron Job

#### For Linux/Mac (using crontab)

1. Open crontab editor:
```bash
crontab -e
```

2. Add this line to run on 1st of every month at 12:01 AM:
```cron
1 0 1 * * cd /Users/ayush/hotel_rental/hotel_project && /usr/bin/python3 manage.py generate_monthly_rent >> /var/log/hotel_rent_generation.log 2>&1
```

3. Save and exit

**Explanation:**
- `1 0 1 * *`: Run at 00:01 on day 1 of every month
- `cd /Users/ayush/hotel_rental/hotel_project`: Navigate to project directory
- `/usr/bin/python3 manage.py generate_monthly_rent`: Run the command
- `>> /var/log/hotel_rent_generation.log 2>&1`: Log output to file

#### For Production (Railway/Heroku)

Use a scheduler add-on:

**Railway:**
- Use Railway Cron (if available) or external service like cron-job.org
- Set up to hit an endpoint that triggers the command

**Heroku:**
```bash
heroku addons:create scheduler:standard
heroku addons:open scheduler
```
Then add the command: `python manage.py generate_monthly_rent`
Set to run monthly on the 1st at midnight

#### Alternative: Django-Crontab Package

1. Install:
```bash
pip install django-crontab
```

2. Add to `settings.py`:
```python
INSTALLED_APPS = [
    ...
    'django_crontab',
]

CRONJOBS = [
    ('1 0 1 * *', 'django.core.management.call_command', ['generate_monthly_rent']),
]
```

3. Add cron jobs:
```bash
python manage.py crontab add
```

---

## How Electricity Bills Add to Total Rent

### Current Implementation

The `MonthlyPayment` model has methods that automatically calculate total amount including electricity:

**Methods:**
- `get_electricity_amount()`: Fetches electricity bill for the same room and month
- `get_total_amount_due()`: Returns rent + electricity
- `get_total_remaining()`: Returns total due - paid amount

**Code Location:** `rental/models.py` - `MonthlyPayment` class (lines 241-259)

### Usage in Templates/Views

When displaying payment information, use:
```python
monthly_payment.get_total_amount_due()  # Rent + Electricity
monthly_payment.get_total_remaining()   # Total - Paid
```

### Automatic Calculation
The electricity bill is automatically included when:
1. Viewing payment details
2. Calculating outstanding balance
3. Generating payment reports

**Note:** Electricity bills are generated manually by the user through the dashboard form. Once generated, they automatically add to the total rent for that month.

---

## Verification

### Test the System

1. **Test Auto-generation on Check-in:**
```bash
python manage.py shell
```
```python
from rental.models import Guest, Room
from datetime import datetime

# Create a test guest
room = Room.objects.first()
guest = Guest.objects.create(
    first_name="Test",
    last_name="User",
    room=room,
    check_in_date=datetime.now().date(),
    is_active=True
)

# Check if payment was created
from rental.models import MonthlyPayment
payment = MonthlyPayment.objects.filter(guest=guest).first()
print(f"Payment created: {payment}")
```

2. **Test Monthly Generation:**
```bash
python manage.py generate_monthly_rent --month 2026-04-01
```

3. **Verify Electricity Integration:**
```bash
python manage.py shell
```
```python
from rental.models import MonthlyPayment

payment = MonthlyPayment.objects.first()
print(f"Rent: ₹{payment.rent_amount}")
print(f"Electricity: ₹{payment.get_electricity_amount()}")
print(f"Total Due: ₹{payment.get_total_amount_due()}")
```

---

## Troubleshooting

### Payments Not Being Created

1. Check if guest has:
   - `is_active = True`
   - `room` assigned
   - `check_in_date` set

2. Check if payment already exists for that room/month

3. Check Django logs for errors

### Cron Job Not Running

1. Verify cron service is running:
```bash
sudo service cron status  # Linux
```

2. Check cron logs:
```bash
grep CRON /var/log/syslog  # Linux
```

3. Test command manually first

---

## Summary

✅ **Automatic on Check-in**: Works immediately, no setup needed
✅ **Monthly Cron Job**: Requires one-time cron setup
✅ **Electricity Integration**: Automatic calculation in MonthlyPayment model
✅ **Tested**: Command successfully generated 40 payments for March 2026
