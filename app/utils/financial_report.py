"""Financial Reports: the reconciliation analytics and the turnover report
combined, for a week, month, quarter or financial year.

Two sources sit side by side:
- the daily sheets captured on StaffTrack, always available, and
- the month-end GoodX figures Sinah captures, available for whole months
  once they've been entered.

Where both exist for the same months, the reconciliation section compares
them practitioner by practitioner.
"""
import calendar
import re
from collections import defaultdict
from datetime import date

from app.models import DailyReconciliation, TurnoverReport
from app.utils.financial_periods import resolve
from app.utils.month_activity import (_period_totals, adjustments_by_reason, era_payments,
                                      payments_by_bank, practitioner_summary,
                                      PAYMENT_COLUMNS)

DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']


def _change(now, before):
    if not before:
        return None
    return (now - before) / before * 100


def _name_key(name):
    """Match a practitioner's name across the daily sheets and GoodX,
    ignoring titles, dots, spacing and case."""
    name = (name or '').lower().replace('.', ' ')
    name = re.sub(r'\b(dr|prof|mr|mrs|ms)\b', ' ', name)
    return ' '.join(name.split())


def _goodx_section_figures(section):
    f = lambda attr: float(getattr(section, attr) or 0)  # noqa: E731
    return {
        'gross': f('gross_turnover') + f('additional_turnover'),
        'credit_notes': f('credit_notes'),
        'net': float(section.net_turnover),
        'kas1': f('kas1_cash') + f('kas1_corrections'),
        'kas3': f('kas3_eft') + f('kas3_corrections'),
        'kas6': f('kas6_era') + f('kas6_corrections'),
        'kas7': f('kas7_card') + f('kas7_corrections'),
        'kas8': f('kas8_linking') + f('kas8_corrections'),
        'cash_flow': float(section.cash_flow_total),
        'journals': float(section.journals_total),
        'movement': f('movement_balance'),
    }


GOODX_KEYS = ['gross', 'credit_notes', 'net', 'kas1', 'kas3', 'kas6', 'kas7', 'kas8',
              'cash_flow', 'journals', 'movement']


def _goodx(period):
    """The month-end GoodX figures captured for the period's months."""
    reports = {(r.year, r.month): r for r in TurnoverReport.query.filter(
        TurnoverReport.year.in_({y for y, _m in period['months']})).all()}
    months = []
    by_name = {}
    for y, m in period['months']:
        report = reports.get((y, m))
        months.append({'year': y, 'month': m, 'label': f'{calendar.month_name[m]} {y}',
                       'report': report, 'captured': report is not None,
                       'future': date(y, m, 1) > date.today()})
        if not report:
            continue
        for section in report.sections:
            key = _name_key(section.practitioner_name)
            row = by_name.setdefault(key, {'name': section.practitioner_name,
                                           **{k: 0.0 for k in GOODX_KEYS}})
            for k, v in _goodx_section_figures(section).items():
                row[k] += v
    rows = sorted(by_name.values(), key=lambda r: r['name'])
    captured = [m for m in months if m['captured']]
    outstanding = [m for m in months if not m['captured'] and not m['future']]
    return {
        'months': months,
        'captured': captured,
        'outstanding': outstanding,
        'rows': rows,
        'totals': {k: sum(r[k] for r in rows) for k in GOODX_KEYS},
        'any': bool(captured),
    }


def _reconciliation(goodx):
    """StaffTrack's daily-sheet figures against GoodX, over the months that
    have GoodX figures, so both sides cover exactly the same days."""
    if not goodx['captured']:
        return None
    staff = defaultdict(lambda: {'name': '', 'billed': 0.0, 'card': 0.0, 'eft': 0.0})
    era = 0.0
    for m in goodx['captured']:
        start = date(m['year'], m['month'], 1)
        end = date(m['year'], m['month'], calendar.monthrange(m['year'], m['month'])[1])
        stats, _totals = practitioner_summary(start, end)
        for p in stats:
            row = staff[_name_key(p['name'])]
            row['name'] = row['name'] or p['name']
            for k in ('billed', 'card', 'eft'):
                row[k] += p[k]
        _days, totals = _period_totals(start, end)
        era += totals['era']

    goodx_by_key = {_name_key(r['name']): r for r in goodx['rows']}
    rows = []
    for key in sorted(set(staff) | set(goodx_by_key)):
        s, g = staff.get(key), goodx_by_key.get(key)
        name = (g or s)['name']
        lines = []
        for label, s_key, g_key in (('Turnover (net of credit notes)', 'billed', 'net'),
                                    ('Card (KAS7)', 'card', 'kas7'),
                                    ('EFT (KAS3)', 'eft', 'kas3')):
            sv = s[s_key] if s else 0.0
            gv = g[g_key] if g else 0.0
            lines.append({'label': label, 'stafftrack': sv, 'goodx': gv, 'difference': gv - sv})
        rows.append({'name': name, 'lines': lines, 'in_stafftrack': s is not None,
                     'in_goodx': g is not None})
    era_goodx = goodx['totals']['kas6']
    return {
        'rows': rows,
        'era': {'stafftrack': era, 'goodx': era_goodx, 'difference': era_goodx - era},
        'months': [m['label'] for m in goodx['captured']],
    }


def build_report(kind, day):
    period = resolve(kind, day)
    start, end = period['start'], period['end']

    days, totals = _period_totals(start, end)
    previous_period = resolve(kind, period['prev_day'])
    _prev_days, previous = _period_totals(previous_period['start'], previous_period['end'])
    practitioners, practitioner_totals = practitioner_summary(start, end)
    payments = payments_by_bank(start, end)
    credit_by_reason, journal_by_reason = adjustments_by_reason(start, end)

    from app.routes.patient_flow import period_totals
    patient_flow = period_totals(start, end)

    # Month by month, for quarters and years
    by_month = []
    if kind in ('quarterly', 'yearly'):
        groups = defaultdict(list)
        for d in days:
            groups[(d['date'].year, d['date'].month)].append(d)
        bank_groups = defaultdict(lambda: defaultdict(float))
        for pd in payments['days']:
            for col, v in pd['totals'].items():
                bank_groups[(pd['date'].year, pd['date'].month)][col] += v
        for y, m in period['months']:
            ds = groups.get((y, m), [])
            row = {'year': y, 'month': m, 'label': f'{calendar.month_abbr[m]} {y}',
                   'sheets': len(ds)}
            for k in ('transactions', 'turnover', 'card', 'eft', 'era', 'received',
                      'expenses', 'net'):
                row[k] = sum(d[k] for d in ds)
            row['banks'] = {col: bank_groups[(y, m)][col] for col in PAYMENT_COLUMNS}
            row['bank_total'] = sum(row['banks'].values())
            by_month.append(row)

    def extremes(key):
        if not days:
            return None, None
        return max(days, key=lambda d: d[key]), min(days, key=lambda d: d[key])

    best_turnover, lowest_turnover = extremes('turnover')
    best_received, lowest_received = extremes('received')

    # Day-of-week pattern (the analytics chart and table)
    dow = {name: {'count': 0, 'received': 0.0, 'transactions': 0} for name in DAYS_OF_WEEK}
    for d in days:
        if d['date'].weekday() < 6:
            row = dow[DAYS_OF_WEEK[d['date'].weekday()]]
            row['count'] += 1
            row['received'] += d['received']
            row['transactions'] += d['transactions']
    for row in dow.values():
        row['avg_received'] = row['received'] / row['count'] if row['count'] else 0
        row['avg_transactions'] = row['transactions'] / row['count'] if row['count'] else 0

    payment_breakdown = {f'{m} ({b})': payments['totals'][(m, b)] for m, b in PAYMENT_COLUMNS}
    payment_breakdown['ERA'] = totals['era']

    goodx = _goodx(period)
    single_month = None
    if kind == 'monthly' and goodx['captured']:
        from app.routes.turnover import _report_totals
        from app.utils.monthly_report import build_document
        report = goodx['captured'][0]['report']
        report_totals = _report_totals(report)
        single_month = {'report': report, 'totals': report_totals,
                        'document': build_document(report, report_totals)}

    first_sheet = DailyReconciliation.query.order_by(DailyReconciliation.date).first()

    return {
        'period': period,
        'previous_period': previous_period,
        'days': days,
        'totals': totals,
        'previous': previous,
        'changes': {k: _change(totals[k], previous[k])
                    for k in ('received', 'expenses', 'net', 'turnover', 'transactions')},
        'practitioners': practitioners,
        'practitioner_totals': practitioner_totals,
        'payments': payments,
        'era': era_payments(start, end),
        'payment_breakdown': payment_breakdown,
        'credit_by_reason': credit_by_reason,
        'journal_by_reason': journal_by_reason,
        'credit_total': sum(r['amount'] for r in credit_by_reason),
        'journal_total': sum(r['amount'] for r in journal_by_reason),
        'patient_flow': patient_flow,
        'by_month': by_month,
        'best_turnover': best_turnover, 'lowest_turnover': lowest_turnover,
        'best_received': best_received, 'lowest_received': lowest_received,
        'day_of_week': dow,
        'chart_days': [{'label': d['date'].strftime('%d/%m'), 'turnover': d['turnover'],
                        'received': d['received'], 'net': d['net'],
                        'transactions': d['transactions']} for d in days],
        'goodx': goodx,
        'single_month': single_month,
        'reconciliation': _reconciliation(goodx) if kind != 'weekly' else None,
        'show_every_payment': kind in ('weekly', 'monthly'),
        'earliest': first_sheet.date if first_sheet else date.today(),
    }
