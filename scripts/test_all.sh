#!/usr/bin/env bash
#
# One-command verification for the Rental OS application.
#
#   ./scripts/test_all.sh
#
# Runs, in order:
#   1. Django system check
#   2. Test-database migration + synthetic seed (isolated DB only)
#   3. Seed determinism check (two --reset runs must match)
#   4. The full backend test suite
#   5. Frontend build and lint
#   6. Frontend API contract tests against a live server
#
# Nothing here writes to db.sqlite3. The seed and the API tests both refuse to
# run unless the test settings module is active.
#
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

export DJANGO_SETTINGS_MODULE=hotel_project.settings_test
export PYTHONDONTWRITEBYTECODE=1

PYTHON="${PYTHON:-python3}"
SERVER_PORT="${SERVER_PORT:-8011}"
SERVER_PID=""

section() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }
cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

section "1/6  Django system check"
"$PYTHON" manage.py check

section "2/6  Test database + synthetic seed"
"$PYTHON" manage.py migrate --noinput >/dev/null
"$PYTHON" manage.py seed_test_data --reset | sed -n '1,40p'

section "3/6  Seed determinism"
"$PYTHON" scripts/verify_seed_determinism.py

section "4/6  Backend test suite"
"$PYTHON" manage.py test rental --verbosity 1

section "5/6  Frontend build + lint"
if [ -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm run build)
  (cd "$ROOT/frontend" && npm run lint)
else
  echo "SKIPPED: frontend/node_modules is missing (run 'npm install' in frontend/)"
fi

section "6/6  Frontend API contract tests"
if [ -d "$ROOT/frontend/node_modules" ]; then
  "$PYTHON" manage.py runserver "$SERVER_PORT" --noreload >/tmp/rental-test-server.log 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:${SERVER_PORT}/health/" >/dev/null 2>&1; then break; fi
    sleep 0.25
  done
  (cd "$ROOT/frontend" && RENTAL_API_BASE="http://127.0.0.1:${SERVER_PORT}" npm run test:contract)
else
  echo "SKIPPED: frontend/node_modules is missing"
fi

section "Done"
echo "Full report: TEST_REPORT.md"
