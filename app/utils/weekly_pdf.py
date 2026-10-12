"""PDF of the weekly report: the week's figures from the daily sheets."""
from datetime import date
from io import BytesIO

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
                                KeepTogether, PageBreak, CondPageBreak)

from app.utils.leave_report import _NumberedCanvas
from app.utils.turnover_pdf import (ACCENT, DARK, PAYMENT_COLUMNS, _grid, _practice_logo,
                                    _text, money)


def _change(pct):
    if pct is None:
        return 'no figures last week'
    word = 'up' if pct >= 0 else 'down'
    return f'{word} {abs(pct):.0f}% on last week'


def build_weekly_pdf(week, generated_by=''):
    practice = current_app.config['PRACTICE_NAME']
    buffer = BytesIO()
    label = f"{week['start'].strftime('%d/%m/%Y')} to {week['end'].strftime('%d/%m/%Y')}"
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=16*mm, bottomMargin=20*mm,
                            leftMargin=18*mm, rightMargin=18*mm,
                            title=f'Weekly Report {label}', author=practice)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('WTitle', parent=styles['Heading1'], fontSize=18, leading=22,
                           textColor=ACCENT, spaceAfter=2)
    subtitle = ParagraphStyle('WSub', parent=styles['Normal'], fontSize=11, leading=14,
                              textColor=DARK, spaceAfter=1)
    meta = ParagraphStyle('WMeta', parent=styles['Normal'], fontSize=8.5, leading=11,
                          textColor=colors.HexColor('#5D6E69'))
    section = ParagraphStyle('WSection', parent=styles['Heading2'], fontSize=13,
                             textColor=DARK, spaceBefore=12, spaceAfter=4)
    sub = ParagraphStyle('WSubSection', parent=styles['Heading3'], fontName='Helvetica-Bold',
                         fontSize=10, textColor=ACCENT, spaceBefore=8, spaceAfter=2)
    body = ParagraphStyle('WBody', parent=styles['Normal'], fontSize=9, leading=12.5,
                          textColor=colors.HexColor('#3A4843'), spaceAfter=4)
    note = ParagraphStyle('WNote', parent=styles['Normal'], fontSize=7.5, leading=10,
                          textColor=colors.HexColor('#5D6E69'), spaceAfter=3)
    cell = ParagraphStyle('WCell', parent=styles['Normal'], fontSize=7.5, leading=9.5,
                          textColor=DARK)

    t = week['totals']
    el = []

    # Letterhead
    logo = _practice_logo()
    if logo is not None:
        el += [logo, Spacer(1, 6)]
    el.append(Paragraph(_text(practice), title))
    el.append(Paragraph('Weekly Report', subtitle))
    el.append(Paragraph(f"Week: <b>{week['start'].strftime('%A %d/%m/%Y')} to "
                        f"{week['end'].strftime('%A %d/%m/%Y')}</b>", subtitle))
    generated = f"Generated on {date.today().strftime('%d/%m/%Y')}"
    if generated_by:
        generated += f' by {_text(generated_by)}'
    el.append(Paragraph(generated, meta))
    el += [Spacer(1, 5), HRFlowable(width='100%', thickness=1, color=ACCENT), Spacer(1, 5)]

    if not week['days']:
        el.append(Paragraph('No daily sheets have been captured for this week yet.', body))
        doc.build(el)
        buffer.seek(0)
        return buffer

    # 1. The week at a glance
    el.append(Paragraph('1. The Week at a Glance', section))
    glance = [['', 'This week', 'Compared with last week'],
              ['Turnover (net of credit notes)', money(t['turnover']),
               _change(week['changes']['turnover'])],
              ['Money received (card, EFT and ERA)', money(t['received']),
               _change(week['changes']['received'])],
              ['Transactions captured', str(t['transactions']),
               _change(week['changes']['transactions'])],
              ['Expenses', money(t['expenses']), ''],
              ['Money in less expenses', money(t['net']), '']]
    el.append(_grid(glance, [70*mm, 40*mm, 64*mm], right=(1,), size=8.5))
    intro = (f"Built from the {len(week['days'])} daily sheets captured on StaffTrack this "
             f"week. The figures may differ slightly from GoodX until the month-end report.")
    if week['missing_days']:
        missing = ', '.join(d.strftime('%A %d/%m') for d in week['missing_days'])
        intro += (f' No sheet was captured for {missing}. If that was not a public holiday, '
                  f'the week is incomplete.')
    el.append(Paragraph(intro, note))

    # 2. Transaction summary
    pt = week['practitioner_totals']
    rows = [['Practitioner', 'Transactions', 'Credit notes', 'Turnover (net)',
             'KAS7 Card', 'KAS3 EFT', 'Cash flow']]
    for p in week['practitioners']:
        rows.append([Paragraph(_text(p['name']), cell), str(p['transactions']),
                     money(-p['credit_notes']) if p['credit_notes'] else '-',
                     money(p['billed']), money(p['card']), money(p['eft']), money(p['received'])])
    rows.append(['Total', str(pt['transactions']),
                 money(-pt['credit_notes']) if pt['credit_notes'] else '-',
                 money(pt['billed']), money(pt['card']), money(pt['eft']), money(pt['received'])])
    el.append(KeepTogether([
        Paragraph('2. Transaction Summary', section),
        _grid(rows, [40*mm, 20*mm, 22*mm, 26*mm, 22*mm, 22*mm, 22*mm],
              right=range(1, 7), bold_last=True),
        Paragraph(f"KAS6 ERA payments this week: {money(t['era'])}. Medical aids pay the "
                  f"practice number, so ERA can't be split per practitioner. A transaction is "
                  f"one line on a daily sheet, not one patient.", note),
    ]))

    # 3. Day by day
    rows = [['Day', 'Trans.', 'Turnover', 'Card', 'EFT', 'ERA', 'Received', 'Expenses']]
    for d in week['days']:
        rows.append([d['date'].strftime('%a %d/%m'), str(d['transactions']), money(d['turnover']),
                     money(d['card']), money(d['eft']), money(d['era']), money(d['received']),
                     money(d['expenses']) if d['expenses'] else '-'])
    rows.append(['Total', str(t['transactions']), money(t['turnover']), money(t['card']),
                 money(t['eft']), money(t['era']), money(t['received']), money(t['expenses'])])
    block = [Paragraph('3. Day by Day', section),
             _grid(rows, [22*mm, 14*mm, 25*mm, 22*mm, 22*mm, 23*mm, 25*mm, 21*mm],
                   right=range(1, 8), bold_last=True, size=7.5)]
    noted = [d for d in week['days'] if d['notes']]
    if noted:
        block.append(Paragraph('Notes on the daily sheets: ' + '; '.join(
            f"{d['date'].strftime('%a %d/%m')}: {_text(d['notes'])}" for d in noted) + '.', note))
    el.append(KeepTogether(block))

    # 4. Best and lowest
    rows = [['', 'Turnover', 'Money received'],
            ['Best day',
             f"{week['best_turnover']['date'].strftime('%a %d/%m')}  "
             f"{money(week['best_turnover']['turnover'])}",
             f"{week['best_received']['date'].strftime('%a %d/%m')}  "
             f"{money(week['best_received']['received'])}"],
            ['Lowest day',
             f"{week['lowest_turnover']['date'].strftime('%a %d/%m')}  "
             f"{money(week['lowest_turnover']['turnover'])}",
             f"{week['lowest_received']['date'].strftime('%a %d/%m')}  "
             f"{money(week['lowest_received']['received'])}"]]
    el.append(KeepTogether([
        Paragraph('4. Best and Lowest Days', section),
        _grid(rows, [44*mm, 65*mm, 65*mm], right=(1, 2), size=8.5),
        Paragraph('Ranked separately: the busiest day for work billed is often not the day '
                  'the most money came in.', note),
    ]))

    # 5. Payments by bank
    pay = week['payments']
    rows = [['Day', 'EFT FNB', 'EFT Capitec', 'Card FNB', 'Card Capitec', 'Day total']]
    for day in pay['days']:
        rows.append([day['date'].strftime('%a %d/%m/%Y'),
                     *[money(day['totals'][c]) if day['totals'][c] else '-' for c in PAYMENT_COLUMNS],
                     money(day['total']) if day['total'] else '-'])
    rows.append(['Total', *[money(pay['totals'][c]) for c in PAYMENT_COLUMNS], money(pay['total'])])
    block = [Paragraph('5. Payments by Bank', section),
             Paragraph(f"{pay['payment_count']} card and EFT payments, by the bank chosen on the "
                       f"daily sheet.", body),
             _grid(rows, [32*mm, 28*mm, 28*mm, 28*mm, 28*mm, 30*mm], right=range(1, 6),
                   bold_last=True)]
    for r in pay['repeated_receipts']:
        dates = ' and '.join(d.strftime('%d/%m/%Y') for d in r['dates'])
        block.append(Paragraph(f"Receipt {_text(r['receipt'])} ({_text(r['patient'])}) is "
                               f"captured on {dates}. If it was only paid once, it was captured "
                               f"twice.", note))
    el.append(KeepTogether(block))

    # 6. Credit notes and journals
    def reasons(title_text, rows_in, total, explain):
        if not rows_in:
            return [Paragraph(title_text, sub), Paragraph('None this week.', body)]
        rows_out = [['Reason', 'Count', 'Amount']]
        rows_out += [[_text(r['reason']), str(r['count']), money(r['amount'])] for r in rows_in]
        rows_out.append(['Total', str(sum(r['count'] for r in rows_in)), money(total)])
        return [Paragraph(title_text, sub),
                _grid(rows_out, [104*mm, 30*mm, 40*mm], right=(1, 2), bold_last=True),
                Paragraph(explain, note)]

    el.append(KeepTogether(
        [Paragraph('6. Credit Notes and Journals', section)] +
        reasons('Credit notes', week['credit_by_reason'], week['credit_total'],
                'Credit notes reverse an invoice, so they reduce turnover.')))
    el.append(KeepTogether(reasons(
        'General journals', week['journal_by_reason'], week['journal_total'],
        'Journals write off a balance. They are not income, and they do not reduce turnover.')))

    # 7. Patient flow
    pf = week['patient_flow']
    if pf['days_recorded']:
        rows = [['', 'Count'],
                ['Patients treated', str(pf['treated'])],
                ['Walk-ins', str(pf['walk_ins'])],
                ['No-shows', f"{pf['no_shows']}  ({pf['no_show_rate']:.0f}% of booked)"],
                ['Cancellations', str(pf['cancellations'])],
                ['Reschedules', str(pf['reschedules'])]]
        el.append(KeepTogether([Paragraph('7. Patient Flow', section),
                                _grid(rows, [118*mm, 56*mm], right=(1,), size=8.5)]))

    # Appendix: every payment
    if pay['payment_count']:
        day_head = ParagraphStyle('WDayHead', parent=sub)
        el.append(PageBreak())
        el.append(Paragraph('Appendix: Every Card and EFT Payment', section))
        widths = [44*mm, 17*mm, 17*mm, 36*mm, 12*mm, 17*mm, 31*mm]
        for day in pay['days']:
            if not day['payments']:
                continue
            rows = [['Patient', 'File no.', 'Receipt', 'Practitioner', 'Type', 'Bank', 'Amount']]
            for p in day['payments']:
                rows.append([Paragraph(_text(p['patient']), cell), _text(p['file_no']),
                             _text(p['receipt']), Paragraph(_text(p['provider']), cell),
                             p['method'], p['bank'], money(p['amount'])])
            rows.append(['Day total', '', '', '', '', '', money(day['total'])])
            heading = Paragraph(f"{day['date'].strftime('%A %d/%m/%Y')} <font size=8 "
                                f"color='#5D6E69'>&nbsp;captured by {_text(day['captured_by'])}"
                                f"</font>", day_head)
            table = _grid(rows, widths, right=(6,), bold_last=True, size=7.5)
            if len(rows) <= 14:
                el.append(KeepTogether([heading, table]))
            else:
                el += [CondPageBreak(40*mm), heading, table]

    footer = f'{practice}  ·  Weekly Report {label}'

    class _Canvas(_NumberedCanvas):
        footer_left = footer

    doc.build(el, canvasmaker=_Canvas)
    buffer.seek(0)
    return buffer
