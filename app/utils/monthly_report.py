"""Assembles the monthly financial report document.

Sinah wrote this narrative document by hand each month to explain the GoodX
figures to the accountant, and the format drifted - January and February were
detailed, May through July each looked different. Dr Buleni asked for one
fixed template.

Everything here is derived from figures already captured on the turnover
report, so nothing is retyped. Only the two interpretation paragraphs are
written by hand, and even those are pre-drafted from the numbers.

Section numbering follows the January 2026 report, which Dr Buleni chose as
the house format, with the grand summary table from July added at the end.
"""
import calendar

# Standard accounting notes. These were identical in every month's report,
# so they are boilerplate rather than something to retype.
ACCOUNTING_NOTES = [
    'Credit notes correctly reduce turnover and ensure accurate billing adjustments.',
    'Journals represent accounting corrections, write-offs, and reallocations.',
    "Doctors' discount/write-off journals reduce collectible revenue and should be "
    'properly authorised.',
    'The use of journals should not replace credit notes for invoice reversals.',
]

MOVEMENT_INCLUDES = [
    'turnover entries',
    'cash flow transactions',
    'credit notes',
    'journals',
    'corrections and write-offs',
]

MOVEMENT_IS_NOT = 'profit, money still to be collected, or turnover alone'
MOVEMENT_IS = ('a net movement balance used to confirm that all financial transactions '
               'in the system balance correctly for the reporting period')

# Cash flow lines, in the order the report presents them. KAS8 is carried but
# never counted: it re-allocates money already received.
CASH_LINES = [
    ('kas1_cash', 'kas1_corrections', 'Cash Payment Control Deposits (KAS1)'),
    ('kas3_eft', 'kas3_corrections', 'EFT Deposits (KAS3)'),
    ('kas6_era', 'kas6_corrections', 'Electronic Remittance Advice Deposits (KAS6)'),
    ('kas7_card', 'kas7_corrections', 'Card Payment Control Deposits (KAS7)'),
]


def _money(value):
    return f'R{float(value or 0):,.2f}'


def _rows(sections, attr):
    """Per-practitioner rows for one figure, dropping practitioners with nothing."""
    rows = [(s.practitioner_name, float(getattr(s, attr) or 0)) for s in sections]
    rows = [r for r in rows if r[1]]
    return {
        'rows': rows,
        'total': sum(r[1] for r in rows),
        'any': bool(rows),
    }


def _default_interpretation(report, totals):
    """A first draft of the narrative, written from the figures themselves."""
    period = f'{calendar.month_name[report.month]} {report.year}'
    gross = totals['gross_turnover']
    credit = totals['credit_notes']
    net = totals['net_turnover']
    cash = totals['cash_flow']

    largest = max(
        (('EFT deposits (KAS3)', totals['kas3']),
         ('electronic remittance advice deposits (KAS6)', totals['kas6']),
         ('card payment control deposits (KAS7)', totals['kas7']),
         ('cash deposits (KAS1)', totals['kas1'])),
        key=lambda pair: pair[1])

    text = (f'{period} reflected total turnover of {_money(gross)} before adjustments. '
            f'After credit notes of {_money(credit)}, the practice retained a net '
            f'turnover position of {_money(net)}.')
    if cash:
        text += (f' Cash flow of {_money(cash)} was received during the period')
        if largest[1]:
            text += f', with {largest[0]} the largest single source'
        text += '.'
    return text


def _default_final_summary(report, totals):
    period = f'{calendar.month_name[report.month]} {report.year}'
    return (f'{period} shows turnover generation of {_money(totals["net_turnover"])} net of '
            f'credit notes, with cash flow movement across all practitioners. Adjustments '
            f'through credit notes, journals and write-offs were processed in line with '
            f'standard practice accounting procedures. The movement summary confirms system '
            f'balance integrity for the period with a net control total of '
            f'{_money(totals["movement_balance"])}.')


def build_document(report, totals):
    """Everything the monthly report document needs, for screen and PDF alike."""
    sections = list(report.sections)
    period = f'{calendar.month_name[report.month]} {report.year}'

    # 4. Cash flow: deposits and corrections, per practitioner, per cashbook
    cash_flow = []
    for deposit_attr, correction_attr, label in CASH_LINES:
        deposits = _rows(sections, deposit_attr)
        corrections = _rows(sections, correction_attr)
        if deposits['any'] or corrections['any']:
            cash_flow.append({
                'label': label,
                'deposits': deposits,
                'corrections': corrections,
            })

    linking = _rows(sections, 'kas8_linking')

    # 5. Journals, listed individually with the practitioner they belong to
    journal_entries = []
    for section in sections:
        for entry in (section.journals or []):
            journal_entries.append({
                'description': entry.get('description') or 'Journal',
                'practitioner': section.practitioner_name,
                'amount': float(entry.get('amount') or 0),
            })

    # Grand summary, the table Dr Buleni liked from the July report
    grand_rows = [{
        'name': s.practitioner_name,
        'adjusted_turnover': float(s.net_turnover or 0),
        'cash_flow': float(s.cash_flow_total or 0),
        'journals': float(s.journals_total or 0),
        'movement': float(s.movement_balance or 0),
    } for s in sections]

    grand_total = {
        'adjusted_turnover': sum(r['adjusted_turnover'] for r in grand_rows),
        'cash_flow': sum(r['cash_flow'] for r in grand_rows),
        'journals': sum(r['journals'] for r in grand_rows),
        'movement': sum(r['movement'] for r in grand_rows),
    }

    return {
        'period': period,
        'practice_name': 'Smilez Dental Surgery',
        'practitioners': [s.practitioner_name for s in sections],
        'turnover': _rows(sections, 'gross_turnover'),
        'additional_turnover': _rows(sections, 'additional_turnover'),
        'credit_notes': _rows(sections, 'credit_notes'),
        'net_turnover': {
            'rows': [(s.practitioner_name, float(s.net_turnover or 0)) for s in sections],
            'total': totals['net_turnover'],
            'any': bool(sections),
        },
        'cash_flow': cash_flow,
        'linking': linking,
        'journal_entries': journal_entries,
        'journal_total': sum(j['amount'] for j in journal_entries),
        'vat_number': report.vat_number or '',
        'vat_inclusive': report.vat_inclusive,
        'vat_exclusive': report.vat_exclusive,
        'vat_equal': (report.vat_inclusive is not None
                      and report.vat_exclusive is not None
                      and report.vat_inclusive == report.vat_exclusive),
        'interpretation': (report.interpretation or '').strip()
                          or _default_interpretation(report, totals),
        'accounting_notes': ACCOUNTING_NOTES,
        'movement_total': totals['movement_balance'],
        'movement_includes': MOVEMENT_INCLUDES,
        'movement_is_not': MOVEMENT_IS_NOT,
        'movement_is': MOVEMENT_IS,
        'final_summary': (report.final_summary or '').strip()
                         or _default_final_summary(report, totals),
        'grand_rows': grand_rows,
        'grand_total': grand_total,
        'totals': totals,
    }


def default_narratives(report, totals):
    """Pre-fill the two written sections so the form is never a blank page."""
    return {
        'interpretation': _default_interpretation(report, totals),
        'final_summary': _default_final_summary(report, totals),
    }
