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
