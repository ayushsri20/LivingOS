# Production Management Guide

## 1. Database Synchronization
Since we performed a "Hard Reset" locally to fix data corruption, your Production Database (on Railway/Render) might still have "Ghost Data".

**If you see incorrect data on the live website, follow these steps:**

### Option A: Soft Reset (Try this first)
Run this command in your Railway/Render Shell or via SSH:
```bash
python manage.py shell < scripts/reset_data.py
```
*(Note: You need to upload `scripts/reset_data.py` first, or copy-paste it into the shell)*.

### Option B: Hard Reset (Nuclear Option)
If you are using SQLite on Production (default), you can delete the database file to start fresh:
```bash
rm db.sqlite3
python manage.py migrate
python setup_full.py
```
**WARNING:** This deletes ALL production data.

## 2. Verification Scripts
We have included verified test scripts in the repository. You can run these on production to verify system health:

- `python verify_deep.py` : Checks Login, Guest Creation, and Checkout.
- `python verify_lifecycle.py` : Checks the full "Entry -> Stats -> Checkout" cycle.
- `python verify_reassignment.py` : Checks long-term tenancy and room reassignment.

## 3. Common Issues
- **CSRF Verification Failed**: This means `ALLOWED_HOSTS` or `CSRF_TRUSTED_ORIGINS` in `settings.py` needs your domain.
- **Static Files Not Loading**: Run `python manage.py collectstatic`.
