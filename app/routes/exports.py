"""Export routes for PDF and Excel downloads."""
from flask import Blueprint, send_file, request, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from app import db
from app.models import Receipt, User, KPIScore, PerformanceEvent, Task, Warning, LeaveRequest
from app.utils.decorators import manager_required
from app.utils.exports import (
    create_excel_report, create_pdf_report,
    format_currency, format_date, format_datetime
)

bp = Blueprint('exports', __name__, url_prefix='/exports')


# ============================================
# Receipt Exports
# ============================================

@bp.route('/receipts/excel')
@login_required
def receipts_excel():
    """Export receipts to Excel."""
    # Get date filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Receipt.query

    if start_date:
        query = query.filter(Receipt.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(Receipt.date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    # Staff can only export their own receipts
    if current_user.role not in ['Practice Manager', 'Super Admin']:
        query = query.filter_by(created_by=current_user.id)

    receipts = query.order_by(Receipt.date.desc()).all()

    headers = ['Receipt #', 'Date', 'Amount', 'Payment Method', 'Description', 'Created By']
    data = []
    for r in receipts:
        creator = User.query.get(r.created_by)
        data.append([
            r.receipt_number,
            format_date(r.date),
            format_currency(r.amount),
            r.payment_method,
            r.description or '-',
            creator.full_name if creator else '-'
        ])

    # Calculate totals
    total = sum(float(r.amount) for r in receipts)
    cash_total = sum(float(r.amount) for r in receipts if r.payment_method == 'Cash')
    card_total = sum(float(r.amount) for r in receipts if r.payment_method == 'Card')
    eft_total = sum(float(r.amount) for r in receipts if r.payment_method == 'EFT')

    data.append(['', '', '', '', '', ''])
    data.append(['TOTALS', '', format_currency(total), '', '', ''])
    data.append(['Cash', '', format_currency(cash_total), '', '', ''])
    data.append(['Card', '', format_currency(card_total), '', '', ''])
    data.append(['EFT', '', format_currency(eft_total), '', '', ''])

    title = 'Receipts Report'
    if start_date and end_date:
        title += f' ({start_date} to {end_date})'

    buffer = create_excel_report(title, headers, data, 'receipts')

    filename = f"receipts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/receipts/pdf')
@login_required
def receipts_pdf():
    """Export receipts to PDF."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Receipt.query

    if start_date:
        query = query.filter(Receipt.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(Receipt.date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    if current_user.role not in ['Practice Manager', 'Super Admin']:
        query = query.filter_by(created_by=current_user.id)

    receipts = query.order_by(Receipt.date.desc()).all()

    headers = ['Receipt #', 'Date', 'Amount', 'Method', 'Description']
    data = []
    for r in receipts:
        data.append([
            r.receipt_number,
            format_date(r.date),
            format_currency(r.amount),
            r.payment_method,
            (r.description or '-')[:30]
        ])

    total = sum(float(r.amount) for r in receipts)
    data.append(['', '', '', '', ''])
    data.append(['TOTAL', '', format_currency(total), '', ''])

    title = 'Receipts Report'
    if start_date and end_date:
        title += f' ({start_date} to {end_date})'

    buffer = create_pdf_report(title, headers, data, 'receipts', 'landscape')

    filename = f"receipts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# ============================================
# KPI Exports
# ============================================

@bp.route('/kpi/excel')
@login_required
@manager_required
def kpi_excel():
    """Export KPI scores to Excel."""
    staff_id = request.args.get('staff_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = KPIScore.query

    if staff_id:
        query = query.filter_by(staff_id=staff_id)
    if start_date:
        query = query.filter(KPIScore.week_start_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(KPIScore.week_start_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    scores = query.order_by(KPIScore.week_start_date.desc(), KPIScore.staff_id).all()

    headers = ['Staff Member', 'Week Starting', 'KPI Category', 'Score', 'Scored By', 'Notes']
    data = []
    for s in scores:
        staff = User.query.get(s.staff_id)
        scorer = User.query.get(s.scored_by)
        data.append([
            staff.full_name if staff else '-',
            format_date(s.week_start_date),
            s.kpi_category,
            'Met' if s.score == 1 else 'Not Met',
            scorer.full_name if scorer else '-',
            s.notes or '-'
        ])

    title = 'KPI Scores Report'
    buffer = create_excel_report(title, headers, data, 'kpi_scores')

    filename = f"kpi_scores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/kpi/pdf')
@login_required
@manager_required
def kpi_pdf():
    """Export KPI scores to PDF."""
    staff_id = request.args.get('staff_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = KPIScore.query

    if staff_id:
        query = query.filter_by(staff_id=staff_id)
    if start_date:
        query = query.filter(KPIScore.week_start_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(KPIScore.week_start_date <= datetime.strptime(end_date, '%Y-%m-%d').date())

    scores = query.order_by(KPIScore.week_start_date.desc(), KPIScore.staff_id).all()

    headers = ['Staff', 'Week', 'Category', 'Score', 'Notes']
    data = []
    for s in scores:
        staff = User.query.get(s.staff_id)
        data.append([
            staff.full_name if staff else '-',
            format_date(s.week_start_date),
            s.kpi_category[:20],
            'Met' if s.score == 1 else 'Not Met',
            (s.notes or '-')[:25]
        ])

    title = 'KPI Scores Report'
    buffer = create_pdf_report(title, headers, data, 'kpi_scores', 'landscape')

    filename = f"kpi_scores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# ============================================
# Performance Exports
# ============================================

@bp.route('/performance/excel')
@login_required
@manager_required
def performance_excel():
    """Export performance history to Excel."""
    staff_id = request.args.get('staff_id', type=int)

    query = PerformanceEvent.query

    if staff_id:
        query = query.filter_by(staff_id=staff_id)

    events = query.order_by(PerformanceEvent.created_at.desc()).limit(500).all()

    headers = ['Staff Member', 'Event Type', 'Description', 'Date', 'Recorded By']
    data = []
    for e in events:
        staff = User.query.get(e.staff_id)
        creator = User.query.get(e.created_by)
        data.append([
            staff.full_name if staff else '-',
            e.event_type,
            e.event_description[:50] if e.event_description else '-',
            format_datetime(e.created_at),
            creator.full_name if creator else '-'
        ])

    title = 'Performance History Report'
    if staff_id:
        staff = User.query.get(staff_id)
        if staff:
            title = f'Performance History - {staff.full_name}'

    buffer = create_excel_report(title, headers, data, 'performance')

    filename = f"performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/performance/pdf')
@login_required
@manager_required
def performance_pdf():
    """Export performance history to PDF."""
    staff_id = request.args.get('staff_id', type=int)

    query = PerformanceEvent.query

    if staff_id:
        query = query.filter_by(staff_id=staff_id)

    events = query.order_by(PerformanceEvent.created_at.desc()).limit(100).all()

    headers = ['Staff', 'Type', 'Description', 'Date']
    data = []
    for e in events:
        staff = User.query.get(e.staff_id)
        data.append([
            staff.full_name if staff else '-',
            e.event_type,
            (e.event_description or '-')[:40],
            format_datetime(e.created_at)
        ])

    title = 'Performance History'
    if staff_id:
        staff = User.query.get(staff_id)
        if staff:
            title = f'Performance - {staff.full_name}'

    buffer = create_pdf_report(title, headers, data, 'performance', 'landscape')

    filename = f"performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# ============================================
# Staff Report (Summary)
# ============================================

@bp.route('/staff/<int:staff_id>/report/pdf')
@login_required
@manager_required
def staff_report_pdf(staff_id):
    """Generate a comprehensive staff report PDF."""
    staff = User.query.get_or_404(staff_id)

    # Gather all data for this staff member
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from io import BytesIO

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#16a34a'))
    elements.append(Paragraph(f"Staff Report: {staff.full_name}", title_style))
    elements.append(Paragraph(f"Role: {staff.role} | Status: {staff.status}", styles['Normal']))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}", styles['Italic']))
    elements.append(Spacer(1, 20))

    # KPI Summary
    elements.append(Paragraph("KPI Performance (Last 30 Days)", styles['Heading2']))
    kpi_scores = KPIScore.query.filter(
        KPIScore.staff_id == staff_id,
        KPIScore.week_start_date >= date.today() - timedelta(days=30)
    ).all()

    if kpi_scores:
        total_scores = len(kpi_scores)
        met_scores = sum(1 for s in kpi_scores if s.score == 1)
        percentage = (met_scores / total_scores * 100) if total_scores > 0 else 0
        elements.append(Paragraph(f"Total KPIs: {total_scores} | Met: {met_scores} | Score: {percentage:.0f}%", styles['Normal']))
    else:
        elements.append(Paragraph("No KPI scores recorded in the last 30 days.", styles['Normal']))
    elements.append(Spacer(1, 15))

    # Task Summary
    elements.append(Paragraph("Task Summary", styles['Heading2']))
    tasks = Task.query.filter_by(assigned_to=staff_id).all()
    completed = sum(1 for t in tasks if t.status == 'Done')
    in_progress = sum(1 for t in tasks if t.status == 'In Progress')
    todo = sum(1 for t in tasks if t.status == 'To Do')
    elements.append(Paragraph(f"Total: {len(tasks)} | Completed: {completed} | In Progress: {in_progress} | To Do: {todo}", styles['Normal']))
    elements.append(Spacer(1, 15))

    # Warnings
    elements.append(Paragraph("Warnings", styles['Heading2']))
    warnings = Warning.query.filter_by(staff_id=staff_id).order_by(Warning.issued_at.desc()).limit(5).all()
    if warnings:
        warning_data = [['Date', 'Type', 'Reason']]
        for w in warnings:
            warning_data.append([
                format_date(w.issued_at),
                w.warning_type,
                (w.reason or '-')[:40]
            ])
        warning_table = Table(warning_data, colWidths=[60, 80, 200])
        warning_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fee2e2')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(warning_table)
    else:
        elements.append(Paragraph("No warnings on record.", styles['Normal']))
    elements.append(Spacer(1, 15))

    # Leave History
    elements.append(Paragraph("Leave History", styles['Heading2']))
    leave_requests = LeaveRequest.query.filter_by(staff_id=staff_id).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    if leave_requests:
        leave_data = [['Type', 'Dates', 'Status']]
        for lr in leave_requests:
            leave_data.append([
                lr.leave_type,
                f"{format_date(lr.start_date)} - {format_date(lr.end_date)}",
                lr.status
            ])
        leave_table = Table(leave_data, colWidths=[80, 150, 80])
        leave_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0f2fe')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(leave_table)
    else:
        elements.append(Paragraph("No leave requests on record.", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)

    filename = f"staff_report_{staff.full_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# ============================================
# Daily Cash Summary Export
# ============================================

@bp.route('/daily-cash/pdf')
@login_required
def daily_cash_pdf():
    """Export daily cash summary to PDF."""
    report_date = request.args.get('date')
    if report_date:
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()
    else:
        report_date = date.today()

    receipts = Receipt.query.filter_by(date=report_date).all()

    cash_total = sum(float(r.amount) for r in receipts if r.payment_method == 'Cash')
    card_total = sum(float(r.amount) for r in receipts if r.payment_method == 'Card')
    eft_total = sum(float(r.amount) for r in receipts if r.payment_method == 'EFT')
    grand_total = cash_total + card_total + eft_total

    headers = ['Receipt #', 'Amount', 'Method', 'Description', 'Created By']
    data = []
    for r in receipts:
        creator = User.query.get(r.created_by)
        data.append([
            r.receipt_number,
            format_currency(r.amount),
            r.payment_method,
            (r.description or '-')[:25],
            creator.full_name if creator else '-'
        ])

    data.append(['', '', '', '', ''])
    data.append(['SUMMARY', '', '', '', ''])
    data.append(['Cash Total', format_currency(cash_total), '', '', ''])
    data.append(['Card Total', format_currency(card_total), '', '', ''])
    data.append(['EFT Total', format_currency(eft_total), '', '', ''])
    data.append(['GRAND TOTAL', format_currency(grand_total), '', '', ''])

    title = f'Daily Cash Summary - {format_date(report_date)}'
    buffer = create_pdf_report(title, headers, data, 'daily_cash')

    filename = f"daily_cash_{report_date.strftime('%Y%m%d')}.pdf"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )
