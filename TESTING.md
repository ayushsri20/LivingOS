# Rental OS — Test System

Complete, repeatable verification: **database → Django backend → REST API →
React frontend → UI states → responsive behaviour → cross-page consistency.**

---

## 1. Quick start

```bash
./scripts/test_all.sh          # everything, one command
```

Or step by step:

```bash
export DJANGO_SETTINGS_MODULE=hotel_project.settings_test

python manage.py check
python manage.py migrate
python manage.py seed_test_data --show      # dry run, prints the plan
python manage.py seed_test_data --reset      # seed the isolated test DB
python manage.py test rental                 # full backend suite

cd frontend
npm install                                 # first time only
npm run build && npm run lint
npm run test:contract                       # needs a running server
```

To browse the seeded app manually:

```bash
export DJANGO_SETTINGS_MODULE=hotel_project.settings_test
python manage.py runserver 8000
# then: cd frontend && npm run dev
# sign in: tester / TesterPass!2026   (test database only)
```

---

## 2. Isolation and production safety

Synthetic data can **never** reach the development or production database.

| Layer | Mechanism |
|---|---|
| Settings | `hotel_project/settings_test.py` sets `ENVIRONMENT = "test"` and points at a **separate** `test_db.sqlite3` |
| `DATABASE_URL` | `settings_test.py` raises at import if set — a deployment DB is never reachable |
| Guard | `rental/testdata/guard.py` re-checks ENVIRONMENT, engine, filename and path before *any* destructive operation |
| Command | `seed_test_data` has **no `--force`**. A bypass switch is how test data eventually reaches production |

Verified refusals:

```console
$ DJANGO_SETTINGS_MODULE=hotel_project.settings python manage.py seed_test_data --reset
CommandError: REFUSED: seed_test_data would run outside the isolated test environment.
  - settings.ENVIRONMENT is '', expected "test".
  - database name '.../db.sqlite3' does not contain "test".

$ DJANGO_SETTINGS_MODULE=hotel_project.settings_test \
  DATABASE_URL='postgresql://…@db.production-host/rentalos' python manage.py seed_test_data
RuntimeError: Refusing to start the Rental OS test environment: DATABASE_URL is set.
```

`manage.py test` additionally gets Django's own throwaway database
(`test_db.testrunner.sqlite3`), destroyed after every run.

---

## 3. The synthetic dataset

```bash
python manage.py seed_test_data            # idempotent
python manage.py seed_test_data --reset    # targeted removal, then recreate
python manage.py seed_test_data --show     # dry run
```

**Version `2026.10-r1`** · reference month **October 2026** · 4 months of history.

| Entity | Count |
|---|---|
| Buildings | 6 (`M1`, `1`, `2`, `3`, `4`, `5`) |
| Rooms | 36 (6 per building) |
| Occupied / vacant | 30 / 6 (one vacant per building) |
| Residents | 30 (`TEST-RES-001` … `TEST-RES-030`) |
| Monthly bills | 120 (30 occupied × 4 months) |
| Electricity bills | 144 (36 × 4 — meters run in vacant rooms too) |
| Payment records | 150 |
| Expenses | 8 |

### Occupancy mix in the reference month

| State | Rooms |
|---|---|
| paid | 13 |
| partial | 7 |
| pending (nothing collected) | 5 |
| overdue | 5 |
| vacant | 6 |


### Scenarios

| Code | Room | What it proves |
|---|---|---|
| EC-001 | A-104 | 35 units → ₹455 |
| EC-002 | B-105 | 0 units → ₹0, reading unchanged |
| EC-003 | D-105 | 500 units → ₹6,500 |
| EC-004 | A-102 | reading below previous → **rejected** (live) |
| EC-005 | A-102 | missing reading → **rejected** (live) |
| EC-006 | A-101 | repeat reading → **no double charge** (live) |
| PAY-001 | A-104 | bill ₹6,655 → paid ₹6,655 → PAID |
| PAY-002 | A-103 | bill ₹7,345 → paid ₹4,000 → PARTIAL, ₹3,345 due |
| PAY-003 | A-106 | bill ₹6,455 → nothing collected → DUE |
| PAY-004 | C-101 | ₹7,250 in three instalments → PAID, 3 records |
| PAY-005 | C-102 | ₹8,000 against ₹7,250 → **overpayment rule** (live) |

### Room numbering

The authoritative inventory is `A-101…F-106` mapped to `M1, 1, 2, 3, 4, 5` by
migration `0017`. Those numbers are preserved untouched. The brief's `M-103`
notation is available as a lookup alias (`spec.room_by_logical_number`), which
resolves `M-103` → `A-103`, `203` → `C-103`.

### Identifiability

Every synthetic row is tagged, so `--reset` finds exactly what it created:

* residents — `id_number` starts with `TEST-RES-`
* bills, payments, expenses — notes/description start with `TEST-DATASET`

E-mail addresses use the RFC 2606 reserved `.invalid` TLD; phone numbers are
non-dialable (`TESTPHONE0001`). No real personal data exists anywhere.

---

## 4. Test suite

130 tests via `python manage.py test rental`.

| # | Category | Module | Count |
|---|---|---|---|
| A | Master data | `tests_master_data.py` | 9 |
| B | Rooms | `tests_rooms.py` | 8 |
| C | Residents | `tests_residents.py` | 8 |
| D | Electricity | `tests_electricity.py` | 10 |
| E | Billing | `tests_billing.py` | 10 |
| F | Payments | `tests_payments.py` | 12 |
| G | Payment history | `tests_payment_history.py` | 6 |
| H | Dashboard | `tests_dashboard.py` | 6 |
| I | Analytics | `tests_analytics.py` | 6 |
| J | Search & filter | `tests_search_filter.py` | 8 |
| K | Error & recovery | `tests_error_recovery.py` | 11 |
| L | Responsive & visual | `tests_visual_responsive.py` | 12 |
| M | Cross-module | `tests_cross_module.py` | 6 |
| — | Pre-existing suite | `tests.py` | 20 |

Plus 16 dependency-free frontend API contract tests
(`frontend/tests/api-contract.test.mjs`, run with `node --test`).

Assertions compare against figures **derived from `rental/testdata/spec.py`**,
never against values read back out of the database — so a seeding bug cannot
make a test pass by agreeing with itself.

---

## 5. Manual visual matrix

No browser automation framework exists in this repository, and the brief says not
to install a large one just to have one. Category L automates what can honestly
be automated (breakpoints, state classes, null-safety of every money field). The
following remains a manual pass.

**Viewports:** 1440 · 1280 · 1024 · 768 · **390** · 360

| Page | Checks at every viewport |
|---|---|
| Dashboard | KPI cards not clipped · distribution legible · building summary · no horizontal scroll |
| Rooms | 6 cards per building · PAID/PARTIAL/DUE/VACANT badges readable · ₹ values not truncated |
| Room drawer | resident, rent, electricity, total, paid, outstanding visible · history scrolls · Collect Payment reachable · closes cleanly |
| Residents | list renders · search · building filter · empty state |
| Payments | status filter · search · history panel · summary follows the selection |
| Electricity | rate shown · per-room readings |
| Analytics | charts not clipped · trend totals · building comparison |

**State matrix** — for each page verify LOADING, SUCCESS, EMPTY, ERROR:

| State | How to trigger |
|---|---|
| LOADING | throttle the network in devtools |
| SUCCESS | normal load |
| EMPTY | Rooms → search `XYZ-NOT-FOUND` |
| ERROR | stop the server, then press Retry |
| PAID | room A-104 (M-104) |
| PARTIAL | room A-103 (M-103) |
| UNPAID | room A-106 (M-106) |
| OVERDUE | ledger view → room B-103 (see finding FIN-002) |
| VACANT | room A-105 (M-105) |

No screen may show a blank area, `undefined`, `null`, `NaN`, a broken chart,
clipped text, a raw API error or an endless spinner.

---

## 6. PAY-005 — the overpayment rule

The brief asked for this rule to be determined and stated, not silently chosen.

**Implemented behaviour:** `api_collect_payment` accepts an amount greater than
the bill. It adds the full amount to `paid_amount`, marks the room `paid`, and
clamps the reported outstanding at zero via `max(0, total - collected)`. The
excess is retained as an implicit credit against that room-month. There is no
credit-balance field, so the surplus is not separately reported or carried
forward.

Pinned by `test_f9_pay005_overpayment_behaviour_is_explicit_and_documented`.
Nothing anywhere produces a negative outstanding.

---

## 7. Moving to real data

1. Production starts with the **existing authoritative 36 rooms**, unchanged.
2. Real residents are entered manually or imported through a controlled process.
3. Real agreed rents, meter readings, bills and payments follow.
4. Dashboards and analytics derive from real database records.
5. The synthetic dataset stays in `test_db.sqlite3` and is never imported.

There is no migration path *from* test data *to* production, and none is
intended.

Rents span **₹5,500–₹7,800** across 20 distinct values, so no test can assume a
universal rent. Meter readings form a continuous month-to-month chain; monthly
consumption sits at 20–100 units with three deliberate outliers.
