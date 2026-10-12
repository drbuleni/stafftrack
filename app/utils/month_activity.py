"""What was captured on the daily sheets for a period: per-practitioner
transactions, and card and EFT payments by bank.

Used by the reconciliation analytics page and by the monthly Turnover &
Cash Flow report, so both show the same figures from the same code. These
are StaffTrack's own captured figures, not the GoodX figures typed into
the report.
"""
import calendar
from collections import defaultdict
from datetime import date

from sqlalchemy import func

from app import db
from app.models import DailyReconciliation, ReconciliationBillingEntry

BANKS = ['FNB', 'Capitec']
# (method, bank) pairs in the order they are shown everywhere
PAYMENT_COLUMNS = [('EFT', 'FNB'), ('EFT', 'Capitec'), ('Card', 'FNB'), ('Card', 'Capitec')]


def practitioner_summary(start, end):
    """Transactions captured, turnover and cash flow per practitioner.

    Turnover is net of credit notes: a credit note reverses an invoice, so
    gross would double-count every corrected claim. A transaction is one
    line on a billing sheet, not one patient.
    """
    rows = db.session.query(
        ReconciliationBillingEntry.provider_name,
        func.count(ReconciliationBillingEntry.id),
        func.coalesce(func.sum(ReconciliationBillingEntry.amount_billed), 0),
        func.coalesce(func.sum(ReconciliationBillingEntry.card_paid), 0),
        func.coalesce(func.sum(ReconciliationBillingEntry.eft_paid), 0),
        func.coalesce(func.sum(ReconciliationBillingEntry.credit_note), 0),
    ).join(
        DailyReconciliation,
        ReconciliationBillingEntry.reconciliation_id == DailyReconciliation.id
    ).filter(
        DailyReconciliation.date >= start,
        DailyReconciliation.date <= end
    ).group_by(
        ReconciliationBillingEntry.provider_name
    ).order_by(
        ReconciliationBillingEntry.provider_name
    ).all()

    stats = [{
        'name': name,
        'transactions': transactions,
        'gross_billed': float(billed),
        'credit_notes': float(credit),
        'billed': float(billed) - float(credit),
        'card': float(card),
        'eft': float(eft),
        'received': float(card) + float(eft),
    } for name, transactions, billed, card, eft, credit in rows]

    keys = ['transactions', 'gross_billed', 'credit_notes', 'billed', 'card', 'eft', 'received']
    totals = {k: sum(p[k] for p in stats) for k in keys}
    return stats, totals


def payments_by_bank(start, end):
    """Every card and EFT payment on the daily sheets, by day and by bank."""
    sheets = DailyReconciliation.query.filter(
        DailyReconciliation.date >= start,
        DailyReconciliation.date <= end
    ).order_by(DailyReconciliation.date).all()

    days = []
    for sheet in sheets:
        totals = defaultdict(float)
        payments = []
        entries = sorted(sheet.billing_entries, key=lambda e: (e.sort_order or 0, e.id))
        for entry in entries:
            for method, amount, bank in (('EFT', entry.eft_paid, entry.eft_bank),
                                         ('Card', entry.card_paid, entry.card_bank)):
                amount = float(amount or 0)
                if amount <= 0:
                    continue
                totals[(method, bank)] += amount
                payments.append({
                    'patient': entry.patient_name or '-',
                    'file_no': entry.file_no or '-',
                    'receipt': entry.receipt_no or '-',
                    'provider': entry.provider_name or '-',
                    'method': method,
                    'bank': bank,
                    'amount': amount,
                })
        days.append({
            'date': sheet.date,
            'captured_by': sheet.preparer.full_name if sheet.preparer else '-',
            'totals': {col: totals[col] for col in PAYMENT_COLUMNS},
            'total': sum(totals.values()),
            'payments': payments,
        })

    month_totals = {col: sum(d['totals'][col] for d in days) for col in PAYMENT_COLUMNS}
    by_bank = {bank: sum(v for (m, b), v in month_totals.items() if b == bank) for bank in BANKS}
    by_method = {m: sum(v for (mm, b), v in month_totals.items() if mm == m)
                 for m in ('EFT', 'Card')}

    # A receipt number belongs to one payment. The same number on two
    # different days usually means a payment was captured twice.
    receipt_days = defaultdict(list)
    for day in days:
        for p in day['payments']:
            if p['receipt'] != '-':
                receipt_days[p['receipt']].append((day['date'], p))
    repeated_receipts = [
        {'receipt': no, 'patient': hits[0][1]['patient'], 'dates': [d for d, _p in hits],
         'amounts': [p['amount'] for _d, p in hits]}
        for no, hits in sorted(receipt_days.items())
        if len({d for d, _p in hits}) > 1
    ]

    return {
        'days': days,
        'totals': month_totals,
        'by_bank': by_bank,
        'by_method': by_method,
        'total': sum(month_totals.values()),
        'payment_count': sum(len(d['payments']) for d in days),
        'repeated_receipts': repeated_receipts,
    }


def month_activity(year, month):
    """Both summaries for a calendar month, for the monthly report."""
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    practitioners, practitioner_totals = practitioner_summary(start, end)
    era_total = db.session.query(
        func.coalesce(func.sum(DailyReconciliation.medical_aid_payments), 0)
    ).filter(DailyReconciliation.date >= start, DailyReconciliation.date <= end).scalar()
    payments = payments_by_bank(start, end)
    return {
        'practitioners': practitioners,
        'practitioner_totals': practitioner_totals,
        'era_total': float(era_total or 0),
        'payments': payments,
        'sheet_count': len(payments['days']),
    }


def adjustments_by_reason(start, end):
    """Credit notes and journals on the daily sheets, grouped by reason."""
    def grouped(amount_column, reason_column):
        rows = db.session.query(
            reason_column,
            func.count(ReconciliationBillingEntry.id),
            func.coalesce(func.sum(amount_column), 0),
        ).join(
            DailyReconciliation,
            ReconciliationBillingEntry.reconciliation_id == DailyReconciliation.id
        ).filter(
            DailyReconciliation.date >= start,
            DailyReconciliation.date <= end,
            amount_column > 0
        ).group_by(reason_column).order_by(func.sum(amount_column).desc()).all()
        return [{'reason': reason or 'Not specified', 'count': count, 'amount': float(amount)}
                for reason, count, amount in rows]

    return (grouped(ReconciliationBillingEntry.credit_note,
                    ReconciliationBillingEntry.credit_note_reason),
            grouped(ReconciliationBillingEntry.journal,
                    ReconciliationBillingEntry.journal_reason))


def _period_totals(start, end):
    """The headline figures for a date range, from the daily sheets."""
    sheets = DailyReconciliation.query.filter(
        DailyReconciliation.date >= start, DailyReconciliation.date <= end
    ).order_by(DailyReconciliation.date).all()
    days = [{
        'date': s.date,
        'transactions': s.patients_treated or 0,   # lines captured, see the model
        'turnover': float(s.goodx_production or 0),
        'card': float((s.card_fnb or 0) + (s.card_capitec or 0)),
        'eft': float(s.eft_received or 0),
        'era': float(s.medical_aid_payments or 0),
        'received': float(s.total_money_in or 0),
        'expenses': float(s.refunds_expenses or 0),
        'net': float(s.net_collections or 0),
        'notes': (s.notes or '').strip(),
    } for s in sheets]
    keys = ['transactions', 'turnover', 'card', 'eft', 'era', 'received', 'expenses', 'net']
    totals = {k: sum(d[k] for d in days) for k in keys}
    return days, totals


def month_weeks(year, month):
    """The weeks of a month, each kept inside the month.

    A week runs Monday to Saturday, but one that crosses into the next
    month is cut at the month end, so the weekly reports of a month always
    add up to that month's report. For example, 28 September to 3 October
    becomes September week 5 (28 to 30 September) and October week 1
    (1 to 3 October).

    Each week's date range also takes in its Sunday, so a sheet captured on
    a Sunday is never left out of every report. A month that starts on a
    Sunday folds that day into its first week.
    """
    from datetime import timedelta
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    weeks = []
    start = first
    while start <= last:
        sunday = start + timedelta(days=6 - start.weekday())
        if start.weekday() == 6 and start == first:
            sunday += timedelta(days=7)          # a lone Sunday joins week 1
        end = min(sunday, last)
        shown_start = start + timedelta(days=1) if start.weekday() == 6 else start
        shown_end = end - timedelta(days=1) if end.weekday() == 6 and end > shown_start else end
        working = sum(1 for i in range((shown_end - shown_start).days + 1)
                      if (shown_start + timedelta(days=i)).weekday() < 6)
        weeks.append({'number': len(weeks) + 1, 'start': start, 'end': end,
                      'shown_start': shown_start, 'shown_end': shown_end,
                      'working_days': working, 'year': year, 'month': month})
        start = end + timedelta(days=1)
    return weeks


def week_containing(day):
    """The month-week that `day` falls in."""
    for week in month_weeks(day.year, day.month):
        if week['start'] <= day <= week['end']:
            return week
    raise ValueError(day)


def week_activity(day):
    """Everything on the weekly report for the month-week containing `day`,
    plus the previous week's figures to compare with (which may be in the
    month before, and may be a short week)."""
    from datetime import timedelta
    from app.routes.patient_flow import period_totals

    week = week_containing(day)
    previous_week = week_containing(week['start'] - timedelta(days=1))
    start, end = week['start'], week['end']
    days, totals = _period_totals(start, end)
    _prev_days, previous = _period_totals(previous_week['start'], previous_week['end'])
    practitioners, practitioner_totals = practitioner_summary(start, end)
    credit_by_reason, journal_by_reason = adjustments_by_reason(start, end)

    def change(key):
        now, before = totals[key], previous[key]
        if not before:
            return None
        return (now - before) / before * 100

    captured = {d['date'] for d in days}
    missing = [start + timedelta(days=i) for i in range((end - start).days + 1)
               if (start + timedelta(days=i)).weekday() < 6
               and start + timedelta(days=i) not in captured
               and start + timedelta(days=i) < date.today()]

    def extremes(key):
        if not days:
            return None, None
        return max(days, key=lambda d: d[key]), min(days, key=lambda d: d[key])

    best_turnover, lowest_turnover = extremes('turnover')
    best_received, lowest_received = extremes('received')

    return {
        'start': start,
        'end': end,
        'week': week,
        'month_weeks': month_weeks(week['year'], week['month']),
        'previous_week': previous_week,
        'title': f"{calendar.month_name[week['month']]} {week['year']}, Week {week['number']}",
        'days': days,
        'totals': totals,
        'previous': previous,
        'changes': {k: change(k) for k in ('turnover', 'received', 'transactions')},
        'missing_days': missing,
        'practitioners': practitioners,
        'practitioner_totals': practitioner_totals,
        'payments': payments_by_bank(start, end),
        'credit_by_reason': credit_by_reason,
        'journal_by_reason': journal_by_reason,
        'credit_total': sum(r['amount'] for r in credit_by_reason),
        'journal_total': sum(r['amount'] for r in journal_by_reason),
        'patient_flow': period_totals(start, end),
        'best_turnover': best_turnover,
        'lowest_turnover': lowest_turnover,
        'best_received': best_received,
        'lowest_received': lowest_received,
    }
