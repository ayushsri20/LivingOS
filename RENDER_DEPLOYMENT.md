# Render Deployment Checklist & Troubleshooting

## Pre-Deployment (Local Machine)

- [x] All safety scripts created and tested locally
- [x] `render.yaml` updated with correct gunicorn command and env vars
- [x] `build.sh` executable and valid
- [x] `requirements.txt` includes `gunicorn`, `psycopg[binary]`, `whitenoise`, `django-storages`, `boto3`
- [x] `hotel_project/wsgi.py` exists and is correct
- [x] `hotel_project/settings.py` reads `DATABASE_URL`, `SECRET_KEY`, `DEBUG` from environment
- [x] Code committed and pushed to GitHub main branch

## Render Dashboard Setup

### 1. Create PostgreSQL Database Service
1. Go to https://dashboard.render.com
2. Click "New +" → "PostgreSQL"
3. Name: `panesar-pg-db`
4. Plan: Free (or paid)
5. Create database
6. Note the connection string (auto-populated in render.yaml)

### 2. Create Web Service
1. Click "New +" → "Web Service"
2. Connect GitHub account (authorize if needed)
3. Select repository: `ayushsri20/Hotel_rental`
4. Select branch: `main`
5. Name: `panesar-pg`
6. Runtime: `Python`
7. Build command: `bash ./build.sh`
8. Start command: `gunicorn hotel_project.wsgi:application --workers 4 --worker-class sync --bind 0.0.0.0:10000 --timeout 60 --access-logfile - --error-logfile -`
9. Plan: Free (or paid)
10. Click "Create Web Service"

### 3. Environment Variables (auto-populated from render.yaml)
Verify in Dashboard → Service → Environment:
- `DATABASE_URL` = (auto from DB service)
- `SECRET_KEY` = (auto-generated)
- `DEBUG` = `false`
- `ALLOWED_HOSTS` = `*.onrender.com,panesar-pg.onrender.com`
- `DJANGO_SETTINGS_MODULE` = `hotel_project.settings`
- `PYTHONUNBUFFERED` = `1`
- `PORT` = `10000`

If using S3 for media, add:
- `AWS_S3_BUCKET_NAME` = `your-bucket`
- `AWS_ACCESS_KEY_ID` = `AKIA...`
- `AWS_SECRET_ACCESS_KEY` = `your-secret`
- `AWS_REGION` = `us-east-1`

### 4. Deploy
1. Render auto-deploys on push to main
2. Or manually trigger: Dashboard → Service → Manual Deploy → Deploy Latest Commit

## Monitoring Deployment

### Check Build & Startup Logs
1. Dashboard → Service Name (panesar-pg) → Logs
2. Look for these messages in order:
   ```
   === Installing dependencies ===
   pip install --upgrade pip
   pip install -r requirements.txt
   Successfully installed...
   
   === Collecting static files ===
   1 static file copied to...
   
   === Running database migrations ===
   Operations to perform...
   Running migrations...
   
   === Build completed successfully ===
   
   [INFO] Starting gunicorn...
   [INFO] Listening at: 0.0.0.0:10000...
   ```

3. Check the public URL: `https://panesar-pg.onrender.com`

## Troubleshooting

### Error: `ModuleNotFoundError: No module named 'app'`
**Fix**: Ensure `startCommand` in `render.yaml` is correct:
```yaml
startCommand: "gunicorn hotel_project.wsgi:application --workers 4 --bind 0.0.0.0:10000"
```
Then redeploy.

### Error: `FAILED to compile requirements.txt`
**Cause**: Incompatible package versions (e.g., `psycopg2-binary` on Python 3.13)
**Fix**: Ensure requirements.txt has:
```
psycopg[binary]>=3.0.0
urllib3>=2.0
```
Not `psycopg2-binary` (old, incompatible with Python 3.13).

Push the fix and redeploy.

### Error: `django.db.utils.OperationalError: could not translate host name`
**Cause**: `DATABASE_URL` not set or Postgres connection failed
**Fix**: 
1. Verify `DATABASE_URL` is set in Render Environment
2. Check Postgres service is running (Dashboard → Database → Status)
3. Verify credentials match
4. Redeploy

### Error: `DisallowedHost at / ... Invalid HTTP_HOST header`
**Cause**: `ALLOWED_HOSTS` doesn't include Render domain
**Fix**: In `render.yaml` or Render dashboard, set:
```
ALLOWED_HOSTS = *.onrender.com,panesar-pg.onrender.com
```
Redeploy.

### Error: `ModuleNotFoundError: No module named 'django'`
**Cause**: `pip install -r requirements.txt` failed during build
**Fix**:
1. Check requirements.txt for syntax errors
2. Check `build.sh` runs `pip install -r requirements.txt`
3. Manually redeploy: Dashboard → Service → Manual Deploy

### Error: `Static files not found (404 for /static/...)`
**Cause**: `collectstatic` failed or `STATIC_ROOT` not configured
**Fix**:
1. Ensure `build.sh` includes: `python manage.py collectstatic --no-input`
2. Verify `hotel_project/settings.py` has:
   ```python
   STATIC_ROOT = BASE_DIR / 'staticfiles'
   STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
   ```
3. Redeploy

### Error: `Media upload fails (403 Permission Denied)`
**Cause**: S3 not configured or credentials wrong
**Fix**: 
1. Ensure AWS env vars are set in Render dashboard
2. Verify IAM user has `s3:PutObject` and `s3:GetObject` permissions
3. Or fall back to local media (not recommended for production)

## Health Checks & Monitoring

### Test Deployment
```bash
# Replace with your Render domain
curl https://panesar-pg.onrender.com/admin/
curl https://panesar-pg.onrender.com/
```

### Verify Data Integrity (on Render via shell)
1. Dashboard → Service → Shell
2. Run:
```bash
python manage.py shell
from rental.models import Room, MonthlyPayment
print(f"Rooms: {Room.objects.count()}")
print(f"Payments: {MonthlyPayment.objects.count()}")
exit()
```

### View Database
1. Dashboard → Database (panesar-pg-db) → Connect
2. Use psql or pgAdmin to connect and inspect tables

## Backup & Restore

### Render PostgreSQL Backups
- Render automatically backs up Postgres daily
- Backups retained for 14 days (free) or 30+ days (pro)
- To restore: Dashboard → Database → Backups → Restore

### Manual Backup (on Render shell)
```bash
python manage.py dumpdata --natural-foreign --natural-primary --exclude auth.permission --exclude contenttypes > backup_$(date +%F).json
```

### Media Backup (if using S3)
```bash
aws s3 sync s3://your-bucket/media/ media_backup/ --region us-east-1
```

## Post-Deployment Safety

- [x] Verify app loads at HTTPS
- [x] Check admin login works
- [x] Test room edit (agreed_rent field)
- [x] Create test payment
- [x] Monitor logs for errors (24+ hours)
- [x] Enable Sentry (optional): Set `SENTRY_DSN` env var
- [x] Keep SQLite backup (`backups/sqlite_data.json`) for 30 days minimum
- [x] Test restore from Postgres backup

## Need Help?

**Check Render Logs First:**
Dashboard → Service → Logs (bottom of page)

**Common Issues & Fixes:**
- Push a new commit to trigger rebuild
- Check environment variables are exact matches (case-sensitive)
- Verify Postgres service is "Available" (green status)
- Try Manual Redeploy: Dashboard → Service → Manual Deploy

**For Persistent Issues:**
- Run local diagnostic: `./scripts/render_diagnostic.sh`
- Check Django: `python manage.py check`
- Test migrations locally: `env -u DATABASE_URL python manage.py migrate --check`
