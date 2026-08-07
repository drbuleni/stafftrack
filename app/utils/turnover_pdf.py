"""Fixed-format PDF for the monthly Turnover & Cash Flow report."""
import calendar
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)

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


def build_turnover_pdf(report, totals):
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
