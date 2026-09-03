"""Fixed-format PDF for the monthly Turnover & Cash Flow report."""
import calendar
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, PageBreak)

ACCENT = colors.HexColor('#1F5F4E')
LIGHT = colors.HexColor('#EAF2EE')
GRID = colors.HexColor('#E2E7E4')
DARK = colors.HexColor('#16211E')

PURPOSE_TEXT = ("This report provides a summary of the monthly billing performance for each "
                "practitioner, including turnover, credit notes, cash flow, journal adjustments "
                "and the final movement balance for the reporting period.")

TURNOVER_NOTE = ("Turnover represents the total value of invoices billed during the month. "
                 "Credit notes reduce the original invoices due to billing corrections, cancelled "
                 "treatment or other approved adjustments, decreasing gross turnover to net turnover.")

JOURNALS_NOTE = ("General journal entries are accounting adjustments (e.g. billing corrections, "
                 "bad debt transfers, doctor's discounts and write-offs). They do not represent "
                 "cash received or additional income.")

KAS8_NOTE = ("KAS8 linking deposits represent previously received payments, mainly from medical "
             "aids, that were linked to the correct patient accounts during reconciliation. They "
             "do not represent additional cash received and are not added to cash flow totals.")

MOVEMENT_NOTE = ("The movement balance is a GoodX system reconciliation control total reflecting "
                 "the net transactional movement for the period. It should not be interpreted as "
                 "the practice's profit or cash held in the bank.")

KAS_LABELS = [
    ('kas1_cash', 'KAS1 Cash Payment Control Deposits'),
    ('kas3_eft', 'KAS3 EFT Deposits'),
    ('kas6_era', 'KAS6 Electronic Remittance Advice (ERA) Deposits'),
    ('kas7_card', 'KAS7 Card Payment Control Deposits'),
    ('kas8_linking', 'KAS8 Linking Deposits (not added to cash flow)'),
    ('kas1_corrections', 'KAS1 Deposit Corrections'),
    ('kas3_corrections', 'KAS3 EFT Deposit Corrections'),
    ('kas6_corrections', 'KAS6 ERA Deposit Corrections'),
    ('kas7_corrections', 'KAS7 Card Deposit Corrections'),
    ('kas8_corrections', 'KAS8 Linking Deposit Corrections'),
]


def money(value):
    value = float(value or 0)
    if value < 0:
        return f"(R{abs(value):,.2f})"
    return f"R{value:,.2f}"


def _practice_logo(max_w=42 * mm, max_h=16 * mm):
    """The practice logo for the letterhead, if a usable file is present.

    The accountant prints this, so it should carry the practice's identity
    rather than ours. Returns None when no logo is configured, and also when
    the file is too pale to read on white - a white-on-white logo would
    otherwise render as an invisible gap.
    """
    import os
    from flask import current_app
    from reportlab.platypus import Image as RLImage

    candidates = [
        os.path.join(current_app.root_path, 'static', 'images', 'practice-logo.png'),
        os.path.join(current_app.root_path, '..', 'smilez dental surgery logo.png'),
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as im:
                grey = im.convert('L')
                # If nothing in the image is darker than near-white it cannot
                # be seen on a white page; skip it rather than print a blank.
                if grey.getextrema()[0] > 210:
                    continue
                width, height = im.size
            scale = min(max_w / width, max_h / height)
            return RLImage(path, width=width * scale, height=height * scale)
        except Exception:
            continue
    return None


def build_turnover_pdf(report, totals, patient_flow=None, document=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            topMargin=18*mm, bottomMargin=18*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title2', parent=styles['Heading1'], fontSize=18,
                                 textColor=ACCENT, spaceAfter=2)
    subtitle_style = ParagraphStyle('Subtitle2', parent=styles['Normal'], fontSize=11,
                                    textColor=DARK, spaceAfter=2)
    section_style = ParagraphStyle('Section2', parent=styles['Heading2'], fontSize=13,
                                   textColor=DARK, spaceBefore=14, spaceAfter=4)
    sub_style = ParagraphStyle('Sub2', parent=styles['Heading3'], fontSize=10.5,
                               textColor=ACCENT, spaceBefore=8, spaceAfter=2)
    body_style = ParagraphStyle('Body2', parent=styles['Normal'], fontSize=9,
                                textColor=colors.HexColor('#4A5A55'), spaceAfter=4)
    note_style = ParagraphStyle('Note2', parent=styles['Normal'], fontSize=8,
                                textColor=colors.grey, spaceAfter=4)

    def money_table(rows, bold_rows=()):
        """Two-column label/amount table."""
        table = Table(rows, colWidths=[118*mm, 56*mm])
        style = [
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, -2), 0.4, GRID),
        ]
        for r in bold_rows:
            style.append(('FONTNAME', (0, r), (-1, r), 'Helvetica-Bold'))
            style.append(('BACKGROUND', (0, r), (-1, r), LIGHT))
        table.setStyle(TableStyle(style))
        return table

    elements = []

    # Header
    period = f"{calendar.month_name[report.month]} {report.year}"
    logo = _practice_logo()
    if logo is not None:
        elements.append(logo)
        elements.append(Spacer(1, 6))
    elements.append(Paragraph('Smilez Dental Surgery', title_style))
    elements.append(Paragraph('Monthly Turnover &amp; Cash Flow Report', subtitle_style))
    elements.append(Paragraph(f"Reporting Period: <b>{period}</b>", subtitle_style))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width='100%', thickness=1, color=ACCENT))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph('<b>Purpose of the Report</b>', body_style))
    elements.append(Paragraph(PURPOSE_TEXT, body_style))

    # Per practitioner
    for i, section in enumerate(report.sections, start=1):
        heading = f"{i}. {section.practitioner_name}"
        if section.room:
            heading += f" ({section.room})"
        elements.append(Paragraph(heading, section_style))

        # Turnover
        elements.append(Paragraph('Turnover', sub_style))
        turnover_rows = [['Gross Turnover (Patient Invoices)', money(section.gross_turnover)]]
        if section.additional_turnover:
            turnover_rows.append(['Additional Turnover', money(section.additional_turnover)])
        turnover_rows.append(['Credit Notes', money(-(section.credit_notes or 0))])
        turnover_rows.append(['Net Turnover', money(section.net_turnover)])
        elements.append(money_table(turnover_rows, bold_rows=(len(turnover_rows) - 1,)))

        # Cash flow
        elements.append(Paragraph('Cash Flow', sub_style))
        cash_rows = []
        for attr, label in KAS_LABELS:
            value = getattr(section, attr) or 0
            if value:
                cash_rows.append([label, money(value)])
        cash_rows.append(['Total Cash Flow (KAS1 + KAS3 + KAS6 + KAS7 incl. corrections)',
                          money(section.cash_flow_total)])
        elements.append(money_table(cash_rows, bold_rows=(len(cash_rows) - 1,)))

        # Journals
        if section.journals:
            elements.append(Paragraph('General Journal Adjustments', sub_style))
            journal_rows = [[j.get('description') or '-', money(j.get('amount'))]
                            for j in section.journals]
            journal_rows.append(['Total Journals', money(section.journals_total)])
            elements.append(money_table(journal_rows, bold_rows=(len(journal_rows) - 1,)))
            elements.append(Paragraph(JOURNALS_NOTE, note_style))

        # Movement balance
        elements.append(Spacer(1, 4))
        elements.append(money_table([['Movement Balance', money(section.movement_balance)]],
                                    bold_rows=(0,)))

    # Overall summary
    elements.append(Paragraph('Overall Practice Summary', section_style))
    summary_rows = [
        ['Total Gross Turnover', money(totals['gross_turnover'])],
        ['Total Credit Notes', money(-(totals['credit_notes'] or 0))],
        ['Total Net Turnover', money(totals['net_turnover'])],
        ['Total KAS1 Cash (incl. corrections)', money(totals['kas1'])],
        ['Total KAS3 EFT (incl. corrections)', money(totals['kas3'])],
        ['Total KAS6 ERA (incl. corrections)', money(totals['kas6'])],
        ['Total KAS7 Card (incl. corrections)', money(totals['kas7'])],
        ['Total KAS8 Linking (not added to cash flow)', money(totals['kas8'])],
        ['Total Cash Flow', money(totals['cash_flow'])],
        ['Consolidated Movement Balance', money(totals['movement_balance'])],
    ]
    elements.append(money_table(summary_rows, bold_rows=(2, 8, 9)))

    # The monthly report document: the narrative the accountant reads.
    # Same fixed structure every month, built from the figures above.
    if document:
        def figure_table(block, label):
            rows = [[name, money(amount)] for name, amount in block['rows']]
            if not rows:
                rows = [['None recorded', money(0)]]
            rows.append([f'Total {label}', money(block['total'])])
            return money_table(rows, bold_rows=(len(rows) - 1,))

        elements.append(PageBreak())
        elements.append(Paragraph(f"{document['period']} Financial Report", title_style))
        elements.append(Paragraph(document['practice_name'], subtitle_style))
        elements.append(Paragraph('Combined Practitioner Analysis', subtitle_style))
        elements.append(Paragraph(
            'Practitioners: ' + ', '.join(document['practitioners']), body_style))
        elements.append(HRFlowable(width='100%', thickness=1, color=ACCENT))

        elements.append(Paragraph('1. Turnover Generated', section_style))
        elements.append(Paragraph(
            f"Turnover represents total services billed during {document['period']} "
            f"before adjustments and collections.", note_style))
        elements.append(figure_table(document['turnover'], 'Turnover'))
        if document['additional_turnover']['any']:
            elements.append(figure_table(document['additional_turnover'], 'Additional Turnover'))

        elements.append(Paragraph('2. Credit Notes Processed', section_style))
        elements.append(Paragraph(
            'Credit notes reduce turnover and are issued for reversals, cancellations, '
            'or corrections.', note_style))
        elements.append(figure_table(document['credit_notes'], 'Credit Notes'))

        elements.append(Paragraph('3. Net Turnover after Credit Notes', section_style))
        elements.append(figure_table(document['net_turnover'], 'Net Turnover'))

        elements.append(Paragraph('4. Cash Flow Analysis', section_style))
        elements.append(Paragraph(
            'Cash flow represents actual money received through deposits and medical aid '
            'remittances.', note_style))
        for i, line in enumerate(document['cash_flow'], start=1):
            elements.append(Paragraph(f"4.{i} {line['label']}", sub_style))
            if line['deposits']['any']:
                elements.append(figure_table(line['deposits'], 'Deposits'))
            if line['corrections']['any']:
                elements.append(figure_table(line['corrections'], 'Corrections'))
        if document['linking']['any']:
            elements.append(Paragraph('Linking Deposits (KAS8)', sub_style))
            elements.append(figure_table(document['linking'], 'Linking'))
            elements.append(Paragraph(KAS8_NOTE, note_style))

        elements.append(Paragraph('5. Journal Entries', section_style))
        if document['journal_entries']:
            elements.append(Paragraph(
                'Journals represent accounting adjustments including bad debts, '
                'write-offs, and corrections.', note_style))
            journal_rows = [[f"{j['description']} - {j['practitioner']}", money(j['amount'])]
                            for j in document['journal_entries']]
            journal_rows.append(['Total Journals', money(document['journal_total'])])
            elements.append(money_table(journal_rows, bold_rows=(len(journal_rows) - 1,)))
        else:
            elements.append(Paragraph(
                'No journal entries were recorded for this period.', note_style))

        elements.append(Paragraph('6. VAT Summary', section_style))
        if document['vat_inclusive'] is not None or document['vat_exclusive'] is not None:
            vat_rows = []
            if document['vat_number']:
                vat_rows.append(['VAT Number', document['vat_number']])
            if document['vat_inclusive'] is not None:
                vat_rows.append(['VAT Inclusive', money(document['vat_inclusive'])])
            if document['vat_exclusive'] is not None:
                vat_rows.append(['VAT Exclusive', money(document['vat_exclusive'])])
            elements.append(money_table(vat_rows))
            if document['vat_equal']:
                elements.append(Paragraph(
                    'Equal VAT inclusive and exclusive values indicate VAT exempt services, '
                    'or non-VAT affecting transactions within the system.', note_style))
        else:
            elements.append(Paragraph(
                'No VAT summary was captured for this period.', note_style))

        elements.append(Paragraph('7. Interpretation of Financial Activity', section_style))
        elements.append(Paragraph(document['interpretation'].replace('\n', '<br/>'), body_style))

        elements.append(Paragraph('8. Accounting Notes', section_style))
        for note in document['accounting_notes']:
            elements.append(Paragraph(f'&bull; {note}', note_style))

        elements.append(Paragraph('9. Movement Summary - System Control Total', section_style))
        elements.append(money_table(
            [['Final Control Total', money(document['movement_total'])]], bold_rows=(0,)))
        elements.append(Paragraph(
            'The movement summary represents the net result of all transactions processed '
            'in the system, including ' + ', '.join(document['movement_includes']) + '.',
            note_style))
        elements.append(Paragraph(
            f"This amount is <b>not</b> {document['movement_is_not']}. "
            f"It is {document['movement_is']}.", note_style))

        elements.append(Paragraph('10. Final Summary', section_style))
        elements.append(Paragraph(document['final_summary'].replace('\n', '<br/>'), body_style))

        elements.append(Paragraph('11. Grand Summary', section_style))
        grand = [['Practitioner', 'Adjusted Turnover', 'Cash Flow', 'Journals', 'Movement']]
        for r in document['grand_rows']:
            grand.append([r['name'], money(r['adjusted_turnover']), money(r['cash_flow']),
                          money(r['journals']), money(r['movement'])])
        gt = document['grand_total']
        grand.append(['GRAND TOTAL', money(gt['adjusted_turnover']), money(gt['cash_flow']),
                      money(gt['journals']), money(gt['movement'])])

        grand_table = Table(grand, colWidths=[44 * mm, 33 * mm, 33 * mm, 31 * mm, 33 * mm])
        grand_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 0), (-1, 0), LIGHT),
            ('BACKGROUND', (0, -1), (-1, -1), LIGHT),
            ('GRID', (0, 0), (-1, -1), 0.4, GRID),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(grand_table)

    # Patient flow for the month
    if patient_flow and patient_flow.get('days_recorded'):
        elements.append(Paragraph('Patient Flow', section_style))
        flow_rows = [
            ['Patients treated', f"{patient_flow['treated']}"],
            ['Walk-ins (treated without a booking)',
             f"{patient_flow['walk_ins']}  ({patient_flow['walk_in_share']:.0f}% of treated)"],
            ['No-shows (booked but did not arrive)',
             f"{patient_flow['no_shows']}  ({patient_flow['no_show_rate']:.0f}% of booked)"],
            ['Days recorded', f"{patient_flow['days_recorded']}"],
        ]
        elements.append(money_table(flow_rows))

    # Optional VAT summary
    if report.vat_inclusive is not None or report.vat_exclusive is not None:
        elements.append(Paragraph('VAT Summary', sub_style))
        vat_rows = []
        if report.vat_inclusive is not None:
            vat_rows.append(['VAT Inclusive', money(report.vat_inclusive)])
        if report.vat_exclusive is not None:
            vat_rows.append(['VAT Exclusive', money(report.vat_exclusive)])
        elements.append(money_table(vat_rows))

    # Standard notes
    elements.append(Paragraph('Notes', sub_style))
    elements.append(Paragraph(TURNOVER_NOTE, note_style))
    elements.append(Paragraph(KAS8_NOTE, note_style))
    elements.append(Paragraph(MOVEMENT_NOTE, note_style))

    if report.notes:
        elements.append(Paragraph('Additional Notes', sub_style))
        elements.append(Paragraph(report.notes.replace('\n', '<br/>'), body_style))

    # Sign-off
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width='100%', thickness=0.5, color=GRID))
    elements.append(Spacer(1, 6))
    preparer = report.preparer.full_name if report.preparer else '-'
    elements.append(Paragraph(f"Compiled by: <b>{preparer}</b>", body_style))
    elements.append(Paragraph(f"Smilez Dental Surgery &bull; Source: GoodX Practice Management System", note_style))
    elements.append(Paragraph(f"Generated by StaffTrack on {report.updated_at.strftime('%d/%m/%Y') if report.updated_at else ''}", note_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer
