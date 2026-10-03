"""
Read-only reporting API for expenses and financial summaries.

Every figure here is aggregated by Django from the existing tables
(Room/Building, MonthlyPayment, ElectricityBill, MaintenanceExpense). Nothing in
this module writes to the database, adds a field, or invents a value that the
schema cannot support — concepts with no backing column (settlement/transfer,
previous-due carry-forward) are deliberately absent rather than faked.

Building identity always comes from Room.building (and the MaintenanceExpense
building_name string as recorded). Names are compared exactly: 'M1' and '1' are
different buildings and are never normalised, coerced or substring-matched.
"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    Building,
    ElectricityBill,
    MaintenanceExpense,
    MonthlyPayment,
)

# Reported as unavailable rather than invented: no column backs either concept.
UNAVAILABLE_FIELDS = [
    {'field': 'Settlement', 'reason': 'No settlement or bank-transfer record is stored.'},
    {'field': 'Previous due', 'reason': 'No carry-forward field is stored.'},
]


def _zero():
    return Decimal('0.00')


def _parse_month(raw):
    """Parse a YYYY-MM-DD (or YYYY-MM) value into a first-of-month date."""
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ('%Y-%m-%d', '%Y-%m', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return date(parsed.year, parsed.month, 1)
    return None


def _money(value):
    return float(Decimal(str(value or 0)).quantize(Decimal('0.01')))


def _authoritative_building_names():
    """Building names exactly as the database stores them (no normalisation)."""
    return list(Building.objects.order_by('id').values_list('name', flat=True))


def _expense_queryset(month=None, building=None):
    """MaintenanceExpense queryset, optionally scoped to a month and/or building."""
    queryset = MaintenanceExpense.objects.all()
    if month is not None:
        queryset = queryset.filter(date__year=month.year, date__month=month.month)
    if building:
        # Exact match only — a partial match would merge 'M1' with '1'.
        queryset = queryset.filter(building_name=building)
    return queryset


def _serialize_expense(expense):
    return {
        'id': expense.id,
        'building': expense.building_name,
        'category': expense.category,
        'category_display': expense.get_category_display(),
        'amount': float(expense.amount),
        'date': expense.date.strftime('%Y-%m-%d'),
        'date_display': expense.date.strftime('%d %b %Y'),
        'description': expense.description or '',
        'is_paid': bool(expense.is_paid),
        'created_at': expense.created_at.strftime('%Y-%m-%d %H:%M'),
    }
@login_required(login_url='login')
@require_http_methods(['GET'])
def expenses_api(request):
    """List expenses with optional month/building filters plus totals."""
    raw_month = request.GET.get('month')
    raw_building = request.GET.get('building')

    month = _parse_month(raw_month)
    if raw_month and month is None:
        return JsonResponse(
            {'success': False, 'message': 'Invalid month. Use YYYY-MM-DD.'},
            status=400,
        )

    building = raw_building.strip() if raw_building and raw_building.strip() else None

    rows = [_serialize_expense(e) for e in _expense_queryset(month, building).order_by('-date', '-id')]

    total = _zero()
    paid_total = _zero()
    pending_total = _zero()
    by_category = defaultdict(lambda: _zero())
    for row in rows:
        amount = Decimal(str(row['amount']))
        total += amount
        if row['is_paid']:
            paid_total += amount
            by_category[row['category']] += amount
        else:
            pending_total += amount

    return JsonResponse({
        'success': True,
        'expenses': rows,
        'count': len(rows),
        'totals': {
            'total': _money(total),
            'paid': _money(paid_total),
            'pending': _money(pending_total),
        },
        'paid_by_category': [
            {'category': key, 'amount': _money(value)}
            for key, value in sorted(by_category.items())
        ],
        'filters': {
            'month': month.strftime('%Y-%m-%d') if month else None,
            'building': building,
        },
        'available_buildings': _authoritative_building_names(),
    })


def _period_income(month):
    """Per-building income for one month, plus portfolio totals."""
    rent_rows = (
        MonthlyPayment.objects.filter(month=month)
        .values('room__building__name')
        .annotate(expected=Sum('rent_amount'), collected=Sum('paid_amount'))
    )
    electricity_rows = (
        ElectricityBill.objects.filter(month=month)
        .values('room__building__name')
        .annotate(amount=Sum('bill_amount'))
    )

    expected_by_building = defaultdict(lambda: _zero())
    collected_by_building = defaultdict(lambda: _zero())
    electricity_by_building = defaultdict(lambda: _zero())

    for row in rent_rows:
        expected_by_building[row['room__building__name']] += Decimal(str(row['expected'] or 0))
        collected_by_building[row['room__building__name']] += Decimal(str(row['collected'] or 0))
    for row in electricity_rows:
        electricity_by_building[row['room__building__name']] += Decimal(str(row['amount'] or 0))

    def line(name):
        expected = expected_by_building[name]
        electricity = electricity_by_building[name]
        return {
            'building': name,
            'expected_rent': _money(expected),
            'electricity': _money(electricity),
            'gross_expected': _money(expected + electricity),
            'collected': _money(collected_by_building[name]),
        }

    names = _authoritative_building_names()
    lines = [line(name) for name in names]
    # A building name present in the data but missing from the Building table is
    # still reported rather than silently dropped.
    extra = (set(expected_by_building) | set(electricity_by_building)) - set(names)
    lines.extend(line(name) for name in sorted(extra))

    totals = {
        key: _money(sum((Decimal(str(l[key])) for l in lines), _zero()))
        for key in ('expected_rent', 'electricity', 'gross_expected', 'collected')
    }
    return lines, totals


def _expense_summary(month, building=None):
    """Paid / pending expense totals and paid-by-category for a month."""
    paid_total = _zero()
    pending_total = _zero()
    by_category = defaultdict(lambda: _zero())

    for expense in _expense_queryset(month, building):
        if expense.is_paid:
            paid_total += Decimal(str(expense.amount))
            by_category[expense.category] += Decimal(str(expense.amount))
        else:
            pending_total += Decimal(str(expense.amount))

    categories = dict(MaintenanceExpense.EXPENSE_CATEGORIES)
    return {
        'paid_total': _money(paid_total),
        'pending_total': _money(pending_total),
        'paid_by_category': [
            {
                'category': key,
                'category_display': categories.get(key, key.title()),
                'amount': _money(value),
            }
            for key, value in sorted(by_category.items())
        ],
    }


@login_required(login_url='login')
@require_http_methods(['GET'])
def monthly_report_api(request):
    """Building-wise income, paid deductions and net operating collection."""
    raw_month = request.GET.get('month')
    today = timezone.now().date()

    if raw_month:
        month = _parse_month(raw_month)
        if month is None:
            return JsonResponse(
                {'success': False, 'message': 'Invalid month. Use YYYY-MM-DD.'},
                status=400,
            )
    else:
        month = date(today.year, today.month, 1)

    raw_building = request.GET.get('building')
    building = raw_building.strip() if raw_building and raw_building.strip() else None

    lines, totals = _period_income(month)
    expenses = _expense_summary(month, building=building)

    # Net operating collection = money actually collected - expenses already paid.
    # Pending (unpaid) expenses are reported separately and never reduce the net.
    net = Decimal(str(totals['collected'])) - Decimal(str(expenses['paid_total']))

    return JsonResponse({
        'success': True,
        'period': {
            'month': month.strftime('%Y-%m-%d'),
            'label': month.strftime('%B %Y'),
            'is_current_month': month == date(today.year, today.month, 1),
        },
        'building_filter': building,
        'available_buildings': _authoritative_building_names(),
        'income': lines,
        'gross_expected': totals['gross_expected'],
        'gross_collected': totals['collected'],
        'expected_rent': totals['expected_rent'],
        'electricity': totals['electricity'],
        'expenses': expenses,
        'net_operating_collection': _money(net),
        'unavailable': UNAVAILABLE_FIELDS,
    })


@login_required(login_url='login')
@require_http_methods(['GET'])
def yearly_report_api(request):
    """Month-by-month gross collection, paid expenses and net, plus yearly totals."""
    raw_year = request.GET.get('year')
    today = timezone.now().date()

    if raw_year:
        try:
            year = int(str(raw_year).strip())
        except ValueError:
            return JsonResponse(
                {'success': False, 'message': 'Invalid year. Use YYYY.'},
                status=400,
            )
        if year < 1900 or year > 9999:
            return JsonResponse(
                {'success': False, 'message': 'Invalid year. Use YYYY.'},
                status=400,
            )
    else:
        year = today.year

    months = []
    gross_total = _zero()
    expected_total = _zero()
    paid_expense_total = _zero()
    pending_total = _zero()
    net_total = _zero()

    for month_number in range(1, 13):
        month = date(year, month_number, 1)

        _, totals = _period_income(month)
        expenses = _expense_summary(month)

        gross = Decimal(str(totals['collected']))
        paid_expenses = Decimal(str(expenses['paid_total']))
        pending = Decimal(str(expenses['pending_total']))
        net = gross - paid_expenses

        has_data = (
            MonthlyPayment.objects.filter(month=month).exists()
            or ElectricityBill.objects.filter(month=month).exists()
            or MaintenanceExpense.objects.filter(
                date__year=year, date__month=month_number
            ).exists()
        )

        months.append({
            'month': month.strftime('%Y-%m-%d'),
            'label': month.strftime('%B %Y'),
            'has_data': has_data,
            'gross_expected': totals['gross_expected'],
            'gross_collection': _money(gross),
            'paid_expenses': _money(paid_expenses),
            'pending_expenses': _money(pending),
            'net_operating_collection': _money(net),
        })

        expected_total += Decimal(str(totals['gross_expected']))
        gross_total += gross
        paid_expense_total += paid_expenses
        pending_total += pending
        net_total += net

    return JsonResponse({
        'success': True,
        'period': {'year': year, 'label': str(year)},
        'months': months,
        'totals': {
            'gross_expected': _money(expected_total),
            'gross_collection': _money(gross_total),
            'paid_expenses': _money(paid_expense_total),
            'pending_expenses': _money(pending_total),
            'net_operating_collection': _money(net_total),
        },
        'available_buildings': _authoritative_building_names(),
        'unavailable': UNAVAILABLE_FIELDS,
    })
