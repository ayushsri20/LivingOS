#!/usr/bin/env bash
#
# Bring up the isolated test environment for manual / browser testing.
#
#   ./scripts/test_env.sh              # migrate, seed, then serve on :8000
#   ./scripts/test_env.sh --seed-only  # just rebuild the data
#
# Guarantees, in order:
#   1. the test database file exists and has every migration applied;
#   2. the deterministic synthetic dataset is present (rooms, residents,
#      electricity, bills, payments, history);
#   3. a test operator exists to sign in with;
#   4. the server is started with hotel_project.settings_test.
#
# It only ever touches test_db.sqlite3. `seed_test_data` refuses to run against
# anything else, and db.sqlite3 is never opened for writing here.
#
# Sign in at http://localhost:5173 (React dev server) with:
#     tester / TesterPass!2026
#
set -euo pipefail
cd "$(dirname "$0")/.."

export DJANGO_SETTINGS_MODULE=hotel_project.settings_test
PYTHON="${PYTHON:-python3}"
PORT="${PORT:-8000}"

echo "==> Database under test:"
"$PYTHON" scripts/diagnose_test_env.py | sed -n '1,7p'

echo
echo "==> Applying migrations to test_db.sqlite3"
"$PYTHON" manage.py migrate --noinput | tail -2

echo
echo "==> Seeding the deterministic synthetic dataset"
"$PYTHON" manage.py seed_test_data --reset | sed -n '/dataset version/,$p'

echo
echo "==> Resulting data:"
"$PYTHON" scripts/diagnose_test_env.py | sed -n '/^ROOMS/,$p'

if [ "${1:-}" = "--seed-only" ]; then
    echo
    echo "Seed complete. Start the server with:"
    echo "  DJANGO_SETTINGS_MODULE=hotel_project.settings_test python manage.py runserver $PORT"
    exit 0
fi

echo
echo "==> Starting Django with settings_test on http://127.0.0.1:$PORT"
echo "    Sign in: tester / TesterPass!2026"
echo "    React UI: cd frontend && npm run dev   ->  http://localhost:5173"
exec "$PYTHON" manage.py runserver "$PORT"
