import calendar
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import (TurnoverReport, TurnoverReportSection, DailyReconciliation,
                        ReconciliationBillingEntry)
from app.routes.reconciliation import finance_access_required, FINANCE_ROLES, get_dentists
from app.utils.decorators import manager_required
from app.utils.audit import log_audit

bp = Blueprint('turnover', __name__, url_prefix='/turnover-reports')


def _parse_money(value):
    """Parse a money value, tolerating R, commas, blanks and parentheses."""
    if value is None:
        return Decimal('0')
    cleaned = str(value).replace('R', '').replace(',', '').replace('(', '-').replace(')', '').strip()
    if not cleaned or cleaned == '-':
        return Decimal('0')
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal('0')


def _apply_report_data(report):
    """Rebuild report sections and header fields from the submitted form."""
    try:
        sections_data = json.loads(request.form.get('sections_data', '[]'))
    except ValueError:
        sections_data = []

    # Bulk-delete old sections in one statement: per-row ORM deletes use
    # psycopg executemany, whose prepared statements collide on Supabase's
    # transaction pooler ("prepared statement _pg3_1 already exists").
    if report.id:
        TurnoverReportSection.query.filter_by(report_id=report.id).delete(synchronize_session=False)
        db.session.expire(report, ['sections'])

    report.sections = []

    order = 0
    for section in sections_data if isinstance(sections_data, list) else []:
        name = (section.get('practitioner_name') or '').strip()
        if not name:
            continue

        journals = []
        for j in section.get('journals', []):
            description = (j.get('description') or '').strip()
            amount = _parse_money(j.get('amount'))
            if description or amount:
                journals.append({'description': description, 'amount': float(amount)})

        report.sections.append(TurnoverReportSection(
            practitioner_name=name,
            room=(section.get('room') or '').strip(),
            gross_turnover=_parse_money(section.get('gross_turnover')),
            additional_turnover=_parse_money(section.get('additional_turnover')),
            credit_notes=_parse_money(section.get('credit_notes')),
            kas1_cash=_parse_money(section.get('kas1_cash')),
            kas3_eft=_parse_money(section.get('kas3_eft')),
            kas6_era=_parse_money(section.get('kas6_era')),
            kas7_card=_parse_money(section.get('kas7_card')),
            kas8_linking=_parse_money(section.get('kas8_linking')),
            kas1_corrections=_parse_money(section.get('kas1_corrections')),
            kas3_corrections=_parse_money(section.get('kas3_corrections')),
            kas6_corrections=_parse_money(section.get('kas6_corrections')),
            kas7_corrections=_parse_money(section.get('kas7_corrections')),
            kas8_corrections=_parse_money(section.get('kas8_corrections')),
            journals=journals,
            movement_balance=_parse_money(section.get('movement_balance')),
            sort_order=order,
        ))
        order += 1

    vat_inclusive = request.form.get('vat_inclusive', '').strip()
    vat_exclusive = request.form.get('vat_exclusive', '').strip()
    report.vat_inclusive = _parse_money(vat_inclusive) if vat_inclusive else None
    report.vat_exclusive = _parse_money(vat_exclusive) if vat_exclusive else None
    report.vat_number = request.form.get('vat_number', '').strip()
    report.interpretation = request.form.get('interpretation', '').strip()
    report.final_summary = request.form.get('final_summary', '').strip()
    report.notes = request.form.get('notes', '')


def _report_totals(report):
    """Practice-wide totals across all sections."""
    sections = report.sections
    return {
        'gross_turnover': sum((s.gross_turnover or 0) + (s.additional_turnover or 0) for s in sections),
        'credit_notes': sum((s.credit_notes or 0) for s in sections),
        'net_turnover': sum(s.net_turnover for s in sections),
        'kas1': sum((s.kas1_cash or 0) + (s.kas1_corrections or 0) for s in sections),
        'kas3': sum((s.kas3_eft or 0) + (s.kas3_corrections or 0) for s in sections),
        'kas6': sum((s.kas6_era or 0) + (s.kas6_corrections or 0) for s in sections),
        'kas7': sum((s.kas7_card or 0) + (s.kas7_corrections or 0) for s in sections),
        'kas8': sum((s.kas8_linking or 0) + (s.kas8_corrections or 0) for s in sections),
        'cash_flow': sum(s.cash_flow_total for s in sections),
        'movement_balance': sum((s.movement_balance or 0) for s in sections),
    }


def _stafftrack_reference(month, year):
    """StaffTrack's own captured figures for the month, for cross-checking
    against the GoodX numbers being typed in."""
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    rows = db.session.query(
        ReconciliationBillingEntry.provider_name,
        func.coalesce(func.sum(ReconciliationBillingEntry.amount_billed), 0),
        func.coalesce(func.sum(ReconciliationBillingEntry.card_paid), 0),
        func.coalesce(func.sum(ReconciliationBillingEntry.eft_paid), 0),
        func.coalesce(func.sum(ReconciliationBillingEntry.credit_note), 0),
    ).join(
        DailyReconciliation,
        ReconciliationBillingEntry.reconciliation_id == DailyReconciliation.id
    ).filter(
        DailyReconciliation.date >= first_day,
        DailyReconciliation.date <= last_day
    ).group_by(
        ReconciliationBillingEntry.provider_name
    ).order_by(
        ReconciliationBillingEntry.provider_name
    ).all()

    era_total = db.session.query(
        func.coalesce(func.sum(DailyReconciliation.medical_aid_payments), 0)
    ).filter(
        DailyReconciliation.date >= first_day,
        DailyReconciliation.date <= last_day
    ).scalar()

    return {
        'practitioners': [{
            'name': name,
            'billed': float(billed),
            'card': float(card),
            'eft': float(eft),
            'credit_notes': float(credit),
        } for name, billed, card, eft, credit in rows],
        'era_total': float(era_total or 0),
    }


@bp.route('/')
@login_required
@finance_access_required
def index():
    """List all turnover reports."""
    reports = TurnoverReport.query.order_by(
        TurnoverReport.year.desc(), TurnoverReport.month.desc()).all()
    return render_template('turnover/index.html',
                          reports=reports,
                          month_names=calendar.month_name,
                          today=date.today())


@bp.route('/new', methods=['GET', 'POST'])
@login_required
@finance_access_required
def new():
    """Create a turnover report for a month."""
    today = date.today()
    # Default to last month - reports are usually compiled after month end
    default_period = date(today.year, today.month, 1) - timedelta(days=1)
    month = request.args.get('month', default_period.month, type=int)
    year = request.args.get('year', default_period.year, type=int)
    month = min(max(month, 1), 12)

    if request.method == 'POST':
        month = request.form.get('month', month, type=int)
        year = request.form.get('year', year, type=int)

        existing = TurnoverReport.query.filter_by(month=month, year=year).first()
        if existing:
            flash(f'A turnover report for {calendar.month_name[month]} {year} already exists. '
                  f'Redirecting to edit.', 'warning')
            return redirect(url_for('turnover.edit', report_id=existing.id))

        report = TurnoverReport(month=month, year=year, prepared_by=current_user.id)
        _apply_report_data(report)
        db.session.add(report)
        db.session.commit()

        log_audit('Created Turnover Report', 'TurnoverReport', report.id,
                  {'period': f'{month}/{year}'})
        flash(f'Turnover report for {calendar.month_name[month]} {year} saved!', 'success')
        return redirect(url_for('turnover.view', report_id=report.id))

    # Prefill each practitioner's section from the daily sheets (billed, KAS7
    # card, KAS3 EFT, credit notes). KAS6 ERA stays manual: medical aids pay
    # the practice number, so StaffTrack cannot split ERA per practitioner.
    reference = _stafftrack_reference(month, year)
    sections_init = [{
        'practitioner_name': p['name'],
        'gross_turnover': p['billed'] or '',
        'kas7_card': p['card'] or '',
        'kas3_eft': p['eft'] or '',
        'credit_notes': p['credit_notes'] or '',
        'journals': [],
    } for p in reference['practitioners']]

    return render_template('turnover/form.html',
                          report=None,
                          month=month,
                          year=year,
                          sections_init=sections_init,
                          reference=reference,
                          dentists=get_dentists(),
                          month_names=calendar.month_name,
                          is_edit=False)


@bp.route('/edit/<int:report_id>', methods=['GET', 'POST'])
@login_required
@finance_access_required
def edit(report_id):
    """Edit an existing turnover report."""
    report = TurnoverReport.query.get_or_404(report_id)

    if request.method == 'POST':
        _apply_report_data(report)
        db.session.commit()

        log_audit('Updated Turnover Report', 'TurnoverReport', report.id,
                  {'period': f'{report.month}/{report.year}'})
        flash('Turnover report updated!', 'success')
        return redirect(url_for('turnover.view', report_id=report.id))

    sections_init = [{
        'practitioner_name': s.practitioner_name,
        'room': s.room or '',
        'gross_turnover': float(s.gross_turnover or 0),
        'additional_turnover': float(s.additional_turnover or 0),
        'credit_notes': float(s.credit_notes or 0),
        'kas1_cash': float(s.kas1_cash or 0),
        'kas3_eft': float(s.kas3_eft or 0),
        'kas6_era': float(s.kas6_era or 0),
        'kas7_card': float(s.kas7_card or 0),
        'kas8_linking': float(s.kas8_linking or 0),
        'kas1_corrections': float(s.kas1_corrections or 0),
        'kas3_corrections': float(s.kas3_corrections or 0),
        'kas6_corrections': float(s.kas6_corrections or 0),
        'kas7_corrections': float(s.kas7_corrections or 0),
        'kas8_corrections': float(s.kas8_corrections or 0),
        'journals': s.journals or [],
        'movement_balance': float(s.movement_balance or 0),
    } for s in report.sections]

    return render_template('turnover/form.html',
                          report=report,
                          month=report.month,
                          year=report.year,
                          sections_init=sections_init,
                          reference=_stafftrack_reference(report.month, report.year),
                          dentists=get_dentists(),
                          month_names=calendar.month_name,
                          is_edit=True)


@bp.route('/view/<int:report_id>')
@login_required
@finance_access_required
def view(report_id):
    """View a formatted turnover report."""
    from app.routes.patient_flow import month_totals
    from app.utils.monthly_report import build_document

    report = TurnoverReport.query.get_or_404(report_id)
    totals = _report_totals(report)
    return render_template('turnover/view.html',
                          report=report,
                          totals=totals,
                          document=build_document(report, totals),
                          patient_flow=month_totals(report.year, report.month),
                          month_names=calendar.month_name)


@bp.route('/pdf/<int:report_id>')
@login_required
@finance_access_required
def pdf(report_id):
    """Download the report as a PDF."""
    report = TurnoverReport.query.get_or_404(report_id)
    from app.routes.patient_flow import month_totals
    from app.utils.monthly_report import build_document
    from app.utils.turnover_pdf import build_turnover_pdf

    totals = _report_totals(report)
    buffer = build_turnover_pdf(report, totals,
                                patient_flow=month_totals(report.year, report.month),
                                document=build_document(report, totals))
    filename = f"turnover_report_{report.year}_{report.month:02d}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename,
                     mimetype='application/pdf')


@bp.route('/delete/<int:report_id>', methods=['POST'])
@login_required
@manager_required
def delete(report_id):
    """Delete a turnover report."""
    report = TurnoverReport.query.get_or_404(report_id)
    period = f'{calendar.month_name[report.month]} {report.year}'

    log_audit('Deleted Turnover Report', 'TurnoverReport', report.id, {'period': period})
    # Bulk-delete child rows first (see _apply_report_data)
    TurnoverReportSection.query.filter_by(report_id=report.id).delete(synchronize_session=False)
    db.session.expire(report, ['sections'])
    db.session.delete(report)
    db.session.commit()

    flash(f'Turnover report for {period} deleted.', 'success')
    return redirect(url_for('turnover.index'))
