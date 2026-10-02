# Panesar PG - Deployment Guide

## Overview
This Django application is configured for deployment on **Render** (recommended) or other PaaS platforms like Heroku.

---

## Quick Deploy to Render

### Option 1: Blueprint Deploy (Recommended)
1. Push your code to GitHub/GitLab
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click **New** → **Blueprint**
4. Connect your repository
5. Render will auto-detect `render.yaml` and set everything up

### Option 2: Manual Deploy
1. Create a new **Web Service** on Render
2. Connect your GitHub repository
3. Configure:
   - **Runtime**: Python 3
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn hotel_project.wsgi:application`

---

## Environment Variables

Set these in your Render dashboard under **Environment**:

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | Auto-generate in Render |
| `DEBUG` | Debug mode | `False` |
| `ALLOWED_HOSTS` | Your domain | `panesar-pg.onrender.com` |
| `DATABASE_URL` | PostgreSQL URL | Auto-set if using Render DB |

### Generate a Secret Key
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Database Setup

### Using Render PostgreSQL (Recommended)
1. In Render, create a new **PostgreSQL** database
2. Copy the **Internal Database URL**
3. Set it as `DATABASE_URL` environment variable
4. Migrations run automatically via `build.sh`

### Creating Admin User
After deployment, run in Render Shell:
```bash
python manage.py createsuperuser
```

---

## Files Structure

```
hotel_project/
├── build.sh              # Build script for Render
├── Procfile              # Process definitions
├── render.yaml           # Render Blueprint config
├── runtime.txt           # Python version
├── requirements.txt      # Python dependencies
├── .env.example          # Environment template
├── .gitignore            # Git ignore rules
├── manage.py
├── hotel_project/        # Django settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── rental/               # Main application
├── staticfiles/          # Collected static files
└── media/                # Uploaded files
```

---

## Pre-Deployment Checklist

- [x] `DEBUG=False` in production
- [x] Secure `SECRET_KEY` generated
- [x] `ALLOWED_HOSTS` configured
- [x] HTTPS security settings enabled
- [x] CSRF trusted origins configured
- [x] WhiteNoise for static files
- [x] Database configured (PostgreSQL for production)
- [x] Static files collected
- [x] All tests passing

---

## Running Locally

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set DEBUG=True in .env for local development
echo "DEBUG=True" >> .env

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic

# Run server
python manage.py runserver
```

---

## Troubleshooting

### Static files not loading
```bash
python manage.py collectstatic --clear --noinput
```

### Database issues
```bash
python manage.py migrate --run-syncdb
```

### Check for deployment issues
```bash
python manage.py check --deploy
```

---

## Security Notes

1. **Never commit `.env`** - It's in `.gitignore`
2. **Generate unique SECRET_KEY** for each environment
3. **Use PostgreSQL** in production (not SQLite)
4. **Enable HTTPS** - Render provides free SSL
5. **Keep dependencies updated** - Check for security patches
6. **Backups & restore**

### Backing up the database

- For Postgres (recommended): use `pg_dump` and store backups off-instance. Example command (run on host or CI):

```bash
# Expects DATABASE_URL environment variable
BACKUP_DIR=~/db_backups
mkdir -p "$BACKUP_DIR"
pg_dump "$DATABASE_URL" -Fc -f "$BACKUP_DIR/pg_backup_$(date +%Y%m%dT%H%M%S).dump"
```

- For SQLite (development only): copy the file to a backup location.

```bash
cp db.sqlite3 ~/db_backups/db.sqlite3.$(date +%Y%m%dT%H%M%S)
```

I included a helper script at `scripts/backup_db.sh` in the repo that will attempt a safe backup based on `DATABASE_URL` (Postgres/SQLite).

### Restoring

- Postgres restore (custom format):

```bash
pg_restore -d postgres://user:pass@host:5432/dbname /path/to/pg_backup.dump
```

- SQLite restore: copy the file back to `db.sqlite3`.

### Scheduling backups

- Use your platform's managed backups (Render DB backups) when available.
- Otherwise add a cronjob or CI job that runs `scripts/backup_db.sh` and uploads artifacts to secure storage (S3). Example cron (daily at 02:00):

```cron
0 2 * * * /path/to/project/scripts/backup_db.sh >> /var/log/db_backup.log 2>&1
```

### Test your backups

- Regularly restore backups into a staging environment to validate integrity and restore procedures.

---

## Support

For issues, check:
- Django docs: https://docs.djangoproject.com
- Render docs: https://render.com/docs
- WhiteNoise: https://whitenoise.readthedocs.io
