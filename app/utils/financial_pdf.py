"""PDF of a Financial Report: a week, month, quarter or financial year.

Part 1 is everything from the daily sheets. Part 2 is the GoodX month-end
figures: for a month, the full monthly report pages (shared with the
monthly report PDF); for a quarter or year, the months added together.
"""
from datetime import date
from io import BytesIO

from flask import current_app
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
                                KeepTogether, PageBreak, CondPageBreak)

from app.utils.leave_report import _NumberedCanvas
from app.utils.turnover_pdf import (ACCENT, DARK, GRID, PAYMENT_COLUMNS, _grid,
                                    _practice_logo, _text, build_turnover_pdf, money)

TURNOVER_COLOUR = colors.HexColor('#3C6FC4')
INCOME_COLOUR = colors.HexColor('#138A68')
WARN_BG = colors.HexColor('#FBF1E4')
WARN_INK = colors.HexColor('#845812')


def _change(pct, label):
    if pct is None:
        return 'nothing to compare with'
    if abs(pct) < 0.5:
        return f'about the same as {label}'
    return f"{'up' if pct > 0 else 'down'} {abs(pct):.0f}% on {label}"


def _chart(points, width):
    """Turnover and income side by side, per day or per month."""
    height = 55 * mm
    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 34, 18
    chart.width, chart.height = width - 40, height - 40
    chart.data = [[p['turnover'] for p in points], [p['received'] for p in points]]
    chart.categoryAxis.categoryNames = [p['label'] for p in points]
    chart.categoryAxis.labels.fontName = 'Helvetica'
    chart.categoryAxis.labels.fontSize = 6.5 if len(points) > 14 else 7
    chart.categoryAxis.labels.angle = 45 if len(points) > 14 else 0
    chart.categoryAxis.labels.dy = -6 if len(points) > 14 else 0
    chart.categoryAxis.strokeColor = GRID
    chart.categoryAxis.visibleTicks = False
    peak = max([max(p['turnover'], p['received']) for p in points] + [1])
    step = 10 ** (len(str(int(peak))) - 1)
    step = step if peak / step > 3 else step / 2
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = (int(peak // step) + 1) * step
    chart.valueAxis.valueStep = step
    chart.valueAxis.labels.fontName = 'Helvetica'
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labelTextFormat = lambda v: f'R{v / 1000:,.0f}k' if v else '0'
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.gridStrokeColor = GRID
    chart.valueAxis.strokeColor = colors.white
    chart.valueAxis.visibleTicks = False
    chart.bars[0].fillColor = TURNOVER_COLOUR
    chart.bars[1].fillColor = INCOME_COLOUR
    for i in (0, 1):
        chart.bars[i].strokeColor = colors.white
        chart.bars[i].strokeWidth = 0.6
    chart.groupSpacing = 4
    drawing.add(chart)
    legend = Legend()
    legend.x, legend.y = 34, height - 4
    legend.alignment = 'right'
    legend.columnMaximum = 1
    legend.deltax = 70
    legend.dx = legend.dy = 7
    legend.fontName = 'Helvetica'
    legend.fontSize = 7.5
    legend.strokeColor = None
    legend.colorNamePairs = [(TURNOVER_COLOUR, 'Turnover'), (INCOME_COLOUR, 'Income')]
    drawing.add(legend)
    return drawing


def build_financial_pdf(r, generated_by=''):
    practice = current_app.config['PRACTICE_NAME']
    p = r['period']
    many = p['kind'] in ('quarterly', 'yearly')
    period_word = {'weekly': 'week', 'monthly': 'month', 'quarterly': 'quarter',
                   'yearly': 'year'}[p['kind']]
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=16*mm, bottomMargin=20*mm,
                            leftMargin=18*mm, rightMargin=18*mm,
                            title=f"Financial Report {p['title']}", author=practice)
    width = A4[0] - 36*mm
    ss = getSampleStyleSheet()
    title = ParagraphStyle('FTitle', parent=ss['Heading1'], fontSize=18, leading=22,
                           textColor=ACCENT, spaceAfter=2)
    subtitle = ParagraphStyle('FSub', parent=ss['Normal'], fontSize=11, leading=14,
                              textColor=DARK, spaceAfter=1)
    meta = ParagraphStyle('FMeta', parent=ss['Normal'], fontSize=8.5, leading=11,
                          textColor=colors.HexColor('#5D6E69'))
    section = ParagraphStyle('FSection', parent=ss['Heading2'], fontSize=13,
                             textColor=DARK, spaceBefore=12, spaceAfter=4)
    part = ParagraphStyle('FPart', parent=ss['Heading1'], fontSize=15, textColor=ACCENT,
                          spaceBefore=4, spaceAfter=6)
    sub = ParagraphStyle('FSubSection', parent=ss['Heading3'], fontName='Helvetica-Bold',
                         fontSize=10, textColor=ACCENT, spaceBefore=8, spaceAfter=2)
    body = ParagraphStyle('FBody', parent=ss['Normal'], fontSize=9, leading=12.5,
                          textColor=colors.HexColor('#3A4843'), spaceAfter=4)
    note = ParagraphStyle('FNote', parent=ss['Normal'], fontSize=7.5, leading=10,
                          textColor=colors.HexColor('#5D6E69'), spaceAfter=3)
    cell = ParagraphStyle('FCell', parent=ss['Normal'], fontSize=7.5, leading=9.5,
                          textColor=DARK)

    def callout(text):
        from reportlab.platypus import Table, TableStyle
        box = Table([[Paragraph(text, body)]], colWidths=[width])
        box.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), WARN_BG),
                                 ('LINEBEFORE', (0, 0), (0, -1), 2.5, WARN_INK),
                                 ('LEFTPADDING', (0, 0), (-1, -1), 9),
                                 ('TOPPADDING', (0, 0), (-1, -1), 6),
                                 ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        return box

    t = r['totals']
    gx = r['goodx']
    el = []

    # Letterhead
    logo = _practice_logo()
    if logo is not None:
        el += [logo, Spacer(1, 6)]
    el.append(Paragraph(_text(practice), title))
    el.append(Paragraph(f"{p['kind_label']} Financial Report: <b>{_text(p['title'])}</b>", subtitle))
    span = p['span'] + (' (to date)' if p['is_current'] else '')
    if p['kind'] == 'weekly' and p['week']['working_days'] < 6:
        span += f" ({p['week']['working_days']} working days)"
    el.append(Paragraph(_text(span), subtitle))
    generated = f"Generated on {date.today().strftime('%d/%m/%Y')}"
    if generated_by:
        generated += f' by {_text(generated_by)}'
    el.append(Paragraph(generated, meta))
    el += [Spacer(1, 5), HRFlowable(width='100%', thickness=1, color=ACCENT), Spacer(1, 6)]

    if p['kind'] == 'weekly':
        el.append(Paragraph('Everything in this report comes from the daily sheets captured on '
                            'StaffTrack. GoodX figures are captured once a month, so they appear '
                            'on the monthly, quarterly and yearly reports.', note))
    elif gx['outstanding']:
        months = ', '.join(m['label'] for m in gx['outstanding'])
        el.append(callout(f'<b>GoodX figures are outstanding</b> for {months}. Everything from '
                          f'the daily sheets is included; the GoodX sections cover only the '
                          f'months already captured.'))
        el.append(Spacer(1, 4))

    if not r['days']:
        el.append(Paragraph('No daily sheets have been captured for this period yet.', body))
    else:
        el.append(Paragraph('Part 1: From the Daily Sheets', part))

        # 1. Key figures
        prev = f"last {period_word}"
        rows = [['', f'This {period_word}', f"Compared with {r['previous_period']['title']}"],
                ['Income (card, EFT and ERA)', money(t['received']), _change(r['changes']['received'], prev)],
                ['Expenses', money(t['expenses']), _change(r['changes']['expenses'], prev)],
                ['Net cash flow (income less expenses)', money(t['net']), _change(r['changes']['net'], prev)],
                ['Turnover (net of credit notes)', money(t['turnover']), _change(r['changes']['turnover'], prev)],
                ['Transactions captured', str(t['transactions']), _change(r['changes']['transactions'], prev)]]
        el.append(Paragraph('1. Key Figures', section))
        el.append(_grid(rows, [66*mm, 36*mm, 72*mm], right=(1,), size=8.5))
        el.append(Paragraph(f"From {len(r['days'])} daily sheets. Daily-sheet figures may differ "
                            f"slightly from GoodX; see the reconciliation section.", note))

        points = ([{'label': m['label'], 'turnover': m['turnover'], 'received': m['received']}
                   for m in r['by_month']] if many else
                  [{'label': d['date'].strftime('%d/%m'), 'turnover': d['turnover'],
                    'received': d['received']} for d in r['days']])
        el.append(KeepTogether([Paragraph(f"Turnover and Income {'by Month' if many else 'by Day'}", sub),
                                _chart(points, width)]))

        # 2. Transaction summary
        pt = r['practitioner_totals']
        rows = [['Practitioner', 'Transactions', 'Credit notes', 'Turnover (net)',
                 'KAS7 Card', 'KAS3 EFT', 'Cash flow']]
        for x in r['practitioners']:
            rows.append([Paragraph(_text(x['name']), cell), str(x['transactions']),
                         money(-x['credit_notes']) if x['credit_notes'] else '-',
                         money(x['billed']), money(x['card']), money(x['eft']), money(x['received'])])
        rows.append(['Total', str(pt['transactions']),
                     money(-pt['credit_notes']) if pt['credit_notes'] else '-',
                     money(pt['billed']), money(pt['card']), money(pt['eft']), money(pt['received'])])
        el.append(KeepTogether([
            Paragraph('2. Transaction Summary', section),
            _grid(rows, [40*mm, 20*mm, 22*mm, 26*mm, 22*mm, 22*mm, 22*mm], right=range(1, 7),
                  bold_last=True),
            Paragraph(f"KAS6 ERA for the period: {money(t['era'])}. Medical aids pay the practice "
                      f"number, so ERA can't be split per practitioner. A transaction is one line "
                      f"on a daily sheet, not one patient.", note)]))

        # 3. Daily or monthly collections
        head = ['Month' if many else 'Day', 'Trans.', 'Turnover', 'Card', 'EFT', 'ERA',
                'Income', 'Expenses', 'Net']
        rows = [head]
        source = r['by_month'] if many else r['days']
        for d in source:
            rows.append([d['label'] if many else d['date'].strftime('%a %d/%m'),
                         str(d['transactions']), money(d['turnover']), money(d['card']),
                         money(d['eft']), money(d['era']), money(d['received']),
                         money(d['expenses']) if d['expenses'] else '-', money(d['net'])])
        rows.append(['Total', str(t['transactions']), money(t['turnover']), money(t['card']),
                     money(t['eft']), money(t['era']), money(t['received']), money(t['expenses']),
                     money(t['net'])])
        el.append(CondPageBreak(60*mm))
        el.append(Paragraph(f"3. {'Month by Month' if many else 'Daily Collections'}", section))
        el.append(_grid(rows, [20*mm, 12*mm, 22*mm, 20*mm, 19*mm, 21*mm, 22*mm, 18*mm, 20*mm],
                        right=range(1, 9), bold_last=True, size=7))
        noted = [d for d in r['days'] if d['notes']] if not many else []
        if noted:
            el.append(Paragraph('Notes on the daily sheets: ' + '; '.join(
                f"{d['date'].strftime('%a %d/%m')}: {_text(d['notes'])}" for d in noted) + '.', note))

        # 4. Best and lowest
        rows = [['', 'Turnover', 'Income'],
                ['Best day', f"{r['best_turnover']['date'].strftime('%a %d/%m/%Y')}  {money(r['best_turnover']['turnover'])}",
                 f"{r['best_received']['date'].strftime('%a %d/%m/%Y')}  {money(r['best_received']['received'])}"],
                ['Lowest day', f"{r['lowest_turnover']['date'].strftime('%a %d/%m/%Y')}  {money(r['lowest_turnover']['turnover'])}",
                 f"{r['lowest_received']['date'].strftime('%a %d/%m/%Y')}  {money(r['lowest_received']['received'])}"]]
        el.append(KeepTogether([Paragraph('4. Best and Lowest Days', section),
                                _grid(rows, [40*mm, 67*mm, 67*mm], right=(1, 2), size=8.5)]))

        # 5. Payments by bank
        pay = r['payments']
        rows = [['Month' if many else 'Day', 'EFT FNB', 'EFT Capitec', 'Card FNB', 'Card Capitec', 'Total']]
        if many:
            for m in r['by_month']:
                rows.append([m['label'], *[money(m['banks'][c]) if m['banks'][c] else '-' for c in PAYMENT_COLUMNS],
                             money(m['bank_total']) if m['bank_total'] else '-'])
        else:
            for day in pay['days']:
                rows.append([day['date'].strftime('%a %d/%m/%Y'),
                             *[money(day['totals'][c]) if day['totals'][c] else '-' for c in PAYMENT_COLUMNS],
                             money(day['total']) if day['total'] else '-'])
        rows.append(['Total', *[money(pay['totals'][c]) for c in PAYMENT_COLUMNS], money(pay['total'])])
        block = [Paragraph('5. Payments by Bank', section),
                 _grid(rows, [32*mm, 28*mm, 28*mm, 28*mm, 28*mm, 30*mm], right=range(1, 6), bold_last=True)]
        for x in pay['repeated_receipts']:
            dates = ' and '.join(d.strftime('%d/%m/%Y') for d in x['dates'])
            block.append(Paragraph(f"Receipt {_text(x['receipt'])} ({_text(x['patient'])}) is captured "
                                   f"on {dates}. If it was only paid once, it was captured twice.", note))
        el.append(CondPageBreak(50*mm))
        el += block

        # 6. Credit notes and journals
        def reasons(heading, rows_in, total, explain):
            if not rows_in:
                return [Paragraph(heading, sub), Paragraph('None in this period.', body)]
            out = [['Reason', 'Count', 'Amount']]
            out += [[_text(x['reason']), str(x['count']), money(x['amount'])] for x in rows_in]
            out.append(['Total', str(sum(x['count'] for x in rows_in)), money(total)])
            return [Paragraph(heading, sub), _grid(out, [104*mm, 30*mm, 40*mm], right=(1, 2), bold_last=True),
                    Paragraph(explain, note)]
        el.append(KeepTogether([Paragraph('6. Credit Notes and Journals', section)] +
                               reasons('Credit notes', r['credit_by_reason'], r['credit_total'],
                                       'Credit notes reverse an invoice, so they reduce turnover.')))
        el.append(KeepTogether(reasons('General journals', r['journal_by_reason'], r['journal_total'],
                                       'Journals write off a balance. They are not income, and they '
                                       'do not reduce turnover.')))

        # 7. Patient flow
        pf = r['patient_flow']
        if pf['days_recorded']:
            rows = [['', 'Count'], ['Patients treated', str(pf['treated'])], ['Walk-ins', str(pf['walk_ins'])],
                    ['No-shows', f"{pf['no_shows']}  ({pf['no_show_rate']:.0f}% of booked)"],
                    ['Cancellations', str(pf['cancellations'])], ['Reschedules', str(pf['reschedules'])]]
            el.append(KeepTogether([Paragraph('7. Patient Flow', section),
                                    _grid(rows, [118*mm, 56*mm], right=(1,), size=8.5)]))

        # 8. Income and expenses
        rows = [['Income', 'Amount']] + [[k, money(v)] for k, v in r['payment_breakdown'].items()]
        rows.append(['Total income', money(t['received'])])
        rows2 = [['Net cash flow', 'Amount'], ['Income', money(t['received'])],
                 ['Less: expenses', money(-t['expenses'])], ['Net cash flow', money(t['net'])]]
        el.append(KeepTogether([Paragraph('8. Income and Expenses', section),
                                _grid(rows, [118*mm, 56*mm], right=(1,), bold_last=True, size=8.5),
                                Spacer(1, 6),
                                _grid(rows2, [118*mm, 56*mm], right=(1,), bold_last=True, size=8.5)]))

    # 9. Reconciliation
    rc = r['reconciliation']
    if rc:
        rows = [['Practitioner', '', 'Daily sheets', 'GoodX', 'Difference']]
        for row in rc['rows']:
            for i, line in enumerate(row['lines']):
                diff = line['difference']
                rows.append([Paragraph(_text(row['name']), cell) if i == 0 else '', line['label'],
                             money(line['stafftrack']), money(line['goodx']),
                             'Matches' if abs(diff) < 0.01 else money(diff)])
        era = rc['era']
        rows.append(['Practice', 'ERA (KAS6)', money(era['stafftrack']), money(era['goodx']),
                     'Matches' if abs(era['difference']) < 0.01 else money(era['difference'])])
        el.append(CondPageBreak(70*mm))
        el.append(Paragraph('9. Reconciliation: Daily Sheets against GoodX', section))
        el.append(Paragraph(f"Over the months with GoodX figures: {', '.join(rc['months'])}. "
                            f"Difference is GoodX less the daily sheets; GoodX card and EFT include "
                            f"their corrections.", body))
        el.append(_grid(rows, [38*mm, 46*mm, 30*mm, 30*mm, 30*mm], right=(2, 3, 4), size=7.5))

    # Part 2: GoodX
    if r['single_month']:
        sm = r['single_month']
        el.append(PageBreak())
        el.append(Paragraph('Part 2: GoodX Month-End Report', part))
        el += build_turnover_pdf(sm['report'], sm['totals'], document=sm['document'],
                                 elements_only=True)
    elif gx['any'] and many:
        gt = gx['totals']
        rows = [['Practitioner', 'Net turnover', 'KAS3 EFT', 'KAS6 ERA', 'KAS7 Card',
                 'Cash flow', 'Journals', 'Movement']]
        for g in gx['rows']:
            rows.append([Paragraph(_text(g['name']), cell), money(g['net']), money(g['kas3']),
                         money(g['kas6']), money(g['kas7']), money(g['cash_flow']),
                         money(g['journals']), money(g['movement'])])
        rows.append(['Total', money(gt['net']), money(gt['kas3']), money(gt['kas6']), money(gt['kas7']),
                     money(gt['cash_flow']), money(gt['journals']), money(gt['movement'])])
        el.append(CondPageBreak(80*mm))
        el.append(Paragraph('Part 2: GoodX Month-End Figures', part))
        captured = ', '.join(m['label'] for m in gx['captured'])
        el.append(Paragraph(f"Added up for the {len(gx['captured'])} month(s) captured: {captured}. "
                            f"Gross turnover {money(gt['gross'])} less credit notes "
                            f"{money(gt['credit_notes'])} gives net turnover {money(gt['net'])}.", body))
        el.append(_grid(rows, [34*mm, 22*mm, 20*mm, 22*mm, 20*mm, 22*mm, 16*mm, 18*mm],
                        right=range(1, 8), bold_last=True, size=7))
        el.append(Paragraph('KAS8 linking re-allocates money already received, so it is not in cash '
                            'flow. Movement is a GoodX control total, not profit or cash in the bank.', note))

    # Appendix: every payment (weeks and months)
    if r['days'] and r['show_every_payment'] and r['payments']['payment_count']:
        el.append(PageBreak())
        el.append(Paragraph('Appendix: Every Card and EFT Payment', section))
        widths = [44*mm, 17*mm, 17*mm, 36*mm, 12*mm, 17*mm, 31*mm]
        for day in r['payments']['days']:
            if not day['payments']:
                continue
            rows = [['Patient', 'File no.', 'Receipt', 'Practitioner', 'Type', 'Bank', 'Amount']]
            for x in day['payments']:
                rows.append([Paragraph(_text(x['patient']), cell), _text(x['file_no']), _text(x['receipt']),
                             Paragraph(_text(x['provider']), cell), x['method'], x['bank'], money(x['amount'])])
            rows.append(['Day total', '', '', '', '', '', money(day['total'])])
            heading = Paragraph(f"{day['date'].strftime('%A %d/%m/%Y')} <font size=8 color='#5D6E69'>"
                                f"&nbsp;captured by {_text(day['captured_by'])}</font>", sub)
            table = _grid(rows, widths, right=(6,), bold_last=True, size=7.5)
            if len(rows) <= 14:
                el.append(KeepTogether([heading, table]))
            else:
                el += [CondPageBreak(40*mm), heading, table]

    footer = f"{practice}  ·  {p['kind_label']} Financial Report, {p['title']}"

    class _Canvas(_NumberedCanvas):
        footer_left = footer

    doc.build(el, canvasmaker=_Canvas)
    buffer.seek(0)
    return buffer
