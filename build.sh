#!/usr/bin/env bash
# Build script for Railway/Render deployment

set -o errexit  # Exit on error

echo "=== Build Environment ==="
echo "Python version: $(python --version)"
echo "Current directory: $(pwd)"

# Verify requirements.txt exists
if [ ! -f "requirements.txt" ]; then
  echo "ERROR: requirements.txt not found in $(pwd)" >&2
  ls -la
  exit 1
fi

echo "=== Installing dependencies ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== System Check ==="
python manage.py check

echo "=== Collecting static files ==="
# Ensure STATIC_ROOT directory exists
mkdir -p staticfiles
python manage.py collectstatic --noinput --clear

echo "=== Verifying static files ==="
ls -la staticfiles/
if [ -d "staticfiles/rental" ]; then
  ls -la staticfiles/rental/
fi

echo "=== Running database migrations ==="
# Migrations are NOT run automatically on build. Against a production database
# this must be a deliberate step, so it is opt-in:
#   RUN_MIGRATIONS=true ./build.sh
# or run `python manage.py migrate` separately from the Render shell.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    python manage.py migrate --noinput
else
    echo "Skipped (set RUN_MIGRATIONS=true to apply migrations during build)"
fi

echo "=== Ensuring production superuser ==="
# Idempotent. Skips cleanly when DJANGO_SUPERUSER_* are not set (local builds
# and CI), creates the user on the first production deploy, and is a no-op on
# every deploy after that. Render Free provides no Shell or Pre-Deploy command,
# so this build step is the only place it can run. A conflicting non-superuser
# account fails the build rather than being modified.
python manage.py ensure_superuser

echo "=== WSGI Verification ==="
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings'); from hotel_project.wsgi import application; print('✓ WSGI application loaded successfully')"

echo "=== Build completed successfully ==="
