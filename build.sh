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
python manage.py migrate --noinput

echo "=== WSGI Verification ==="
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings'); from hotel_project.wsgi import application; print('✓ WSGI application loaded successfully')"

echo "=== Build completed successfully ==="
