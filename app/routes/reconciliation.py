from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (StringField, IntegerField, DecimalField, TextAreaField,
                     DateField, SelectMultipleField, SubmitField, SelectField)
from wtforms.validators import DataRequired, Optional, NumberRange
from wtforms.widgets import ListWidget, CheckboxInput
from app import db
from app.models import (DailyReconciliation, ReconciliationBillingEntry,
                        ReconciliationEraPayment, User)
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
import json

bp = Blueprint('reconciliation', __name__, url_prefix='/reconciliation')

# Roles allowed to see practice financials (reconciliation, turnover reports).
# Dentists, dental assistants and cleaners are deliberately excluded.
FINANCE_ROLES = ['Receptionist', 'Billing', 'Practice Manager', 'Super Admin']


def finance_access_required(f):
    """Restrict a view to roles that may see practice financials."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in FINANCE_ROLES:
            flash('You do not have permission to view this page.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function

# Retail items sold at the practice
RETAIL_ITEMS = [
    'Toothbrushes (adult)',
    'Baby toothbrushes',
    'Mouthwash',
    'Dental wax',
    'Ortho kit',
    'Clinpro toothpaste',
    'Tongue scraper',
    'Other'
]

DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# Reasons a credit note can be issued (per Sinah / GoodX workflow)
CREDIT_NOTE_REASONS = [
    'Wrong patient',
    'Wrong practitioner',
    'Incorrect dependent code',
    'Wrong date of service',
    'Corrections',
]

# Journal types as they appear in GoodX. A journal removes a balance for an
# accounting reason - it is not income, profit or billing. Same six types the
# turnover report already uses, so the two stay in step.
JOURNAL_REASONS = [
    'Bad Debt',
    'Braces Adjustment',
    'Discount',
    'Doctor Discount / Write-off',
    'Duplicate Receipt Adjustment',
    'Settlement Discount',
]

# The practice runs two speedpoints and two bank accounts. Card and EFT
# money must be split per bank because each reconciles against its own
# bank statement.
BANKS = ['FNB', 'Capitec']
DEFAULT_BANK = 'FNB'


def _clean_bank(value):
    """Normalise a submitted bank choice, defaulting to FNB."""
    value = (value or '').strip()
    for bank in BANKS:
        if value.lower() == bank.lower():
            return bank
    return DEFAULT_BANK


def get_dentists():
    """Get all users who can be dentists on duty (Dentist, Practice Manager, Super Admin).

    The shared 'admin' account is excluded: it belongs to Dr. Thembeka Buleni,
    who already appears under her personal account - listing both created
    duplicate practitioners on billing sheets and analytics."""
    return User.query.filter(
        User.status == 'Active',
        User.role.in_(['Dentist', 'Practice Manager', 'Super Admin']),
        User.username != 'admin'
    ).order_by(User.full_name).all()


def get_all_active_staff():
    """Get all active staff members."""
    return User.query.filter_by(status='Active').order_by(User.full_name).all()


def _parse_money(value):
    """Parse a money value from the billing sheet, tolerating R, commas and blanks."""
    if value is None:
        return Decimal('0')
    cleaned = str(value).replace('R', '').replace(',', '').strip()
    if not cleaned:
        return Decimal('0')
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal('0')


def _apply_sheet_data(rec):
    """Rebuild billing entries and ERA payments from the submitted form JSON,
    then map the sheet totals onto the reconciliation money fields."""
    try:
        billing_data = json.loads(request.form.get('billing_data', '[]'))
    except ValueError:
        billing_data = []
    try:
        era_data = json.loads(request.form.get('era_data', '[]'))
    except ValueError:
        era_data = []

    # Replace all existing line items. Old rows are removed with single bulk
    # DELETE statements on purpose: per-row ORM deletes go through psycopg's
    # executemany, whose prepared statements collide on Supabase's transaction
    # pooler ("prepared statement _pg3_1 already exists").
    if rec.id:
        ReconciliationBillingEntry.query.filter_by(reconciliation_id=rec.id).delete(synchronize_session=False)
        ReconciliationEraPayment.query.filter_by(reconciliation_id=rec.id).delete(synchronize_session=False)
        db.session.expire(rec, ['billing_entries', 'era_payments'])

    rec.billing_entries = []
    rec.era_payments = []

    total_billed = Decimal('0')
    total_credit = Decimal('0')
    total_journal = Decimal('0')
    total_card = {'FNB': Decimal('0'), 'Capitec': Decimal('0')}
    total_eft = {'FNB': Decimal('0'), 'Capitec': Decimal('0')}
    total_era = Decimal('0')
    patient_count = 0

    order = 0
    for sheet in billing_data if isinstance(billing_data, list) else []:
        provider_name = (sheet.get('provider_name') or '').strip()
        if not provider_name:
            continue
        try:
            provider_id = int(sheet.get('provider_id')) if sheet.get('provider_id') else None
        except (TypeError, ValueError):
            provider_id = None

        for entry in sheet.get('entries', []):
            computer_no = (entry.get('computer_no') or '').strip()
            file_no = (entry.get('file_no') or '').strip()
            patient_name = (entry.get('patient_name') or '').strip()
            medical_aid = (entry.get('medical_aid') or '').strip()
            receipt_no = (entry.get('receipt_no') or '').strip()
            amount_billed = _parse_money(entry.get('amount_billed'))
            card_paid = _parse_money(entry.get('card_paid'))
            eft_paid = _parse_money(entry.get('eft_paid'))
            card_bank = _clean_bank(entry.get('card_bank'))
            eft_bank = _clean_bank(entry.get('eft_bank'))
            credit_note = _parse_money(entry.get('credit_note'))
            credit_note_reason = (entry.get('credit_note_reason') or '').strip()
            if not credit_note:
                credit_note_reason = ''
            journal = _parse_money(entry.get('journal'))
            journal_reason = (entry.get('journal_reason') or '').strip()
            if not journal:
                journal_reason = ''

            # Skip completely empty rows
            if not any([computer_no, file_no, patient_name, medical_aid, receipt_no,
                        amount_billed, card_paid, eft_paid, credit_note, journal]):
                continue

            rec.billing_entries.append(ReconciliationBillingEntry(
                provider_id=provider_id,
                provider_name=provider_name,
                computer_no=computer_no,
                file_no=file_no,
                patient_name=patient_name,
                medical_aid=medical_aid,
                amount_billed=amount_billed,
                card_paid=card_paid,
                card_bank=card_bank,
                eft_paid=eft_paid,
                eft_bank=eft_bank,
                credit_note=credit_note,
                credit_note_reason=credit_note_reason,
                journal=journal,
                journal_reason=journal_reason,
                receipt_no=receipt_no,
                sort_order=order
            ))
            order += 1
            patient_count += 1
            total_billed += amount_billed
            total_credit += credit_note
            total_journal += journal
            total_card[card_bank] += card_paid
            total_eft[eft_bank] += eft_paid

    order = 0
    for payment in era_data if isinstance(era_data, list) else []:
        batch_number = (payment.get('batch_number') or '').strip()
        medical_aid_name = (payment.get('medical_aid_name') or '').strip()
        amount_paid = _parse_money(payment.get('amount_paid'))
        payment_date = None
        if payment.get('payment_date'):
            try:
                payment_date = date.fromisoformat(payment['payment_date'])
            except ValueError:
                payment_date = None

        if not any([batch_number, medical_aid_name, amount_paid, payment_date]):
            continue

        rec.era_payments.append(ReconciliationEraPayment(
            batch_number=batch_number,
            medical_aid_name=medical_aid_name,
            payment_date=payment_date,
            amount_paid=amount_paid,
            sort_order=order
        ))
        order += 1
        total_era += amount_paid

    # Map sheet totals onto the money fields so history and analytics keep
    # working. Card and EFT are split per bank: each reconciles against its
    # own bank statement.
    rec.card_fnb = total_card['FNB']              # KAS7 Card, FNB speedpoint
    rec.card_capitec = total_card['Capitec']      # KAS7 Card, Capitec speedpoint
    rec.eft_fnb = total_eft['FNB']                # KAS3 EFT into FNB
    rec.eft_capitec = total_eft['Capitec']        # KAS3 EFT into Capitec
    rec.eft_received = total_eft['FNB'] + total_eft['Capitec']
    rec.medical_aid_payments = total_era      # KAS6 ERA's
    rec.medical_aid_balance_payments = Decimal('0')
    rec.other_payments = Decimal('0')
    # Total billed is NET of credit notes. A credit note reverses an invoice
    # in GoodX - the original claim and its reversal must cancel out, leaving
    # only the corrected claim. Reporting the gross figure double-counted
    # every corrected invoice.
    # Journals are deliberately NOT deducted here. A credit note reverses an
    # invoice, so it reduces turnover; a journal writes off an outstanding
    # balance for an accounting reason and is not a turnover reduction. GoodX
    # treats them the same way, and so does our monthly turnover report, where
    # net turnover is gross less credit notes only. Deducting journals here
    # would put the daily sheet out of step with both.
    rec.goodx_production = total_billed - total_credit
    rec.patients_treated = patient_count

    rec.calculate_totals()


def _sheet_display_data(rec):
    """Group billing entries by provider and compute totals for display."""
    providers = []
    by_provider = {}
    for entry in rec.billing_entries:
        if entry.provider_name not in by_provider:
            by_provider[entry.provider_name] = {
                'provider_name': entry.provider_name,
                'provider_id': entry.provider_id,
                'entries': [],
                'total_billed': Decimal('0'),
                'total_card': Decimal('0'),
                'total_eft': Decimal('0'),
                'total_credit': Decimal('0'),
                'total_journal': Decimal('0'),
                'net_billed': Decimal('0'),
            }
            providers.append(by_provider[entry.provider_name])
        group = by_provider[entry.provider_name]
        group['entries'].append(entry)
        group['total_billed'] += entry.amount_billed or 0
        group['total_card'] += entry.card_paid or 0
        group['total_eft'] += entry.eft_paid or 0
        group['total_credit'] += entry.credit_note or 0
        group['total_journal'] += entry.journal or 0
        # What the practitioner actually billed once reversals cancel out
        group['net_billed'] = group['total_billed'] - group['total_credit']

    # Split by bank for the daily summary: each reconciles against its own
    # bank statement.
    by_bank = {
        'card_fnb': Decimal('0'), 'card_capitec': Decimal('0'),
        'eft_fnb': Decimal('0'), 'eft_capitec': Decimal('0'),
    }
    for entry in rec.billing_entries:
        card_key = 'card_capitec' if (entry.card_bank == 'Capitec') else 'card_fnb'
        eft_key = 'eft_capitec' if (entry.eft_bank == 'Capitec') else 'eft_fnb'
        by_bank[card_key] += entry.card_paid or 0
        by_bank[eft_key] += entry.eft_paid or 0

    era_total = sum((p.amount_paid or 0 for p in rec.era_payments), Decimal('0'))

    return {
        'providers': providers,
        'era_total': era_total,
        'total_billed': sum((p['total_billed'] for p in providers), Decimal('0')),
        'total_card': sum((p['total_card'] for p in providers), Decimal('0')),
        'total_eft': sum((p['total_eft'] for p in providers), Decimal('0')),
        'total_credit': sum((p['total_credit'] for p in providers), Decimal('0')),
        'net_billed': sum((p['net_billed'] for p in providers), Decimal('0')),
        'total_journal': sum((p['total_journal'] for p in providers), Decimal('0')),
        'banks': by_bank,
    }


@bp.route('/')
@login_required
@finance_access_required
def index():
    """View reconciliation history."""
    # Get filter parameters
    month = request.args.get('month', date.today().month, type=int)
    year = request.args.get('year', date.today().year, type=int)

    # Get first and last day of month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # Get reconciliations for the month
    reconciliations = DailyReconciliation.query.filter(
        DailyReconciliation.date >= first_day,
        DailyReconciliation.date <= last_day
    ).order_by(DailyReconciliation.date.desc()).all()

    # Calculate monthly totals
    monthly_totals = {
        'total_billed': sum(r.goodx_production or 0 for r in reconciliations),
        'total_money_in': sum(r.total_money_in or 0 for r in reconciliations),
        'net_collections': sum(r.net_collections or 0 for r in reconciliations),
        'patients_treated': sum(r.patients_treated or 0 for r in reconciliations),
    }

    # Navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    import calendar
    month_name = calendar.month_name[month]

    return render_template('reconciliation/index.html',
                          reconciliations=reconciliations,
                          monthly_totals=monthly_totals,
                          month=month,
                          year=year,
                          month_name=month_name,
                          prev_month=prev_month,
                          prev_year=prev_year,
                          next_month=next_month,
                          next_year=next_year,
                          today=date.today())


@bp.route('/new', methods=['GET', 'POST'])
@bp.route('/new/<selected_date>', methods=['GET', 'POST'])
@login_required
@finance_access_required
def new(selected_date=None):
    """Create a new daily reconciliation sheet."""
    # Only receptionist, practice manager, or super admin can create
    if current_user.role not in ['Receptionist', 'Billing', 'Practice Manager', 'Super Admin']:
        flash('You do not have permission to create reconciliation sheets.', 'danger')
        return redirect(url_for('reconciliation.index'))

    # Default to today if no date provided
    if selected_date:
        try:
            rec_date = date.fromisoformat(selected_date)
        except ValueError:
            rec_date = date.today()
    else:
        rec_date = date.today()

    # Check if reconciliation already exists for this date
    existing = DailyReconciliation.query.filter_by(date=rec_date).first()
    if existing:
        flash(f'A reconciliation sheet already exists for {rec_date}. Redirecting to edit.', 'info')
        return redirect(url_for('reconciliation.edit', rec_id=existing.id))

    dentists = get_dentists()

    if request.method == 'POST':
        # Get the date from form
        form_date = request.form.get('date')
        if form_date:
            rec_date = date.fromisoformat(form_date)

        # Check again after form submission
        existing = DailyReconciliation.query.filter_by(date=rec_date).first()
        if existing:
            flash(f'A reconciliation sheet already exists for {rec_date}.', 'warning')
            return redirect(url_for('reconciliation.edit', rec_id=existing.id))

        rec = DailyReconciliation(
            date=rec_date,
            day_of_week=DAYS_OF_WEEK[rec_date.weekday()],
            prepared_by=current_user.id,
            prepared_at=datetime.utcnow(),
            notes=request.form.get('notes', ''),
            status='Submitted'
        )

        _apply_sheet_data(rec)

        db.session.add(rec)
        db.session.commit()

        log_audit('Created Daily Reconciliation', 'DailyReconciliation', rec.id, {
            'date': rec.date.isoformat(),
            'net_collections': float(rec.net_collections)
        })

        flash(f'Daily reconciliation for {rec.date} saved successfully!', 'success')
        return redirect(url_for('reconciliation.view', rec_id=rec.id))

    return render_template('reconciliation/form.html',
                          rec=None,
                          rec_date=rec_date,
                          dentists=dentists,
                          days_of_week=DAYS_OF_WEEK,
                          billing_init=[],
                          era_init=[],
                          credit_note_reasons=CREDIT_NOTE_REASONS,
                          journal_reasons=JOURNAL_REASONS,
                          banks=BANKS,
                          is_edit=False)


@bp.route('/edit/<int:rec_id>', methods=['GET', 'POST'])
@login_required
@finance_access_required
def edit(rec_id):
    """Edit an existing reconciliation sheet."""
    rec = DailyReconciliation.query.get_or_404(rec_id)

    # Check permissions
    if current_user.role not in ['Receptionist', 'Billing', 'Practice Manager', 'Super Admin']:
        flash('You do not have permission to edit reconciliation sheets.', 'danger')
        return redirect(url_for('reconciliation.index'))

    # Don't allow editing checked sheets unless manager
    if rec.status == 'Checked' and current_user.role not in ['Practice Manager', 'Super Admin']:
        flash('This sheet has been checked and cannot be edited.', 'warning')
        return redirect(url_for('reconciliation.view', rec_id=rec.id))

    dentists = get_dentists()

    if request.method == 'POST':
        # Allow correcting a sheet that was saved under the wrong date
        old_date = rec.date
        form_date = request.form.get('date')
        if form_date:
            try:
                new_date = date.fromisoformat(form_date)
            except ValueError:
                new_date = rec.date
            if new_date != rec.date:
                clash = DailyReconciliation.query.filter(
                    DailyReconciliation.date == new_date,
                    DailyReconciliation.id != rec.id
                ).first()
                if clash:
                    flash(f"A reconciliation sheet already exists for {new_date.strftime('%d/%m/%Y')}, "
                          f"so the date was kept as {rec.date.strftime('%d/%m/%Y')}. "
                          f"Everything else was saved.", 'warning')
                else:
                    rec.date = new_date
                    rec.day_of_week = DAYS_OF_WEEK[new_date.weekday()]

        rec.notes = request.form.get('notes', '')

        _apply_sheet_data(rec)

        db.session.commit()

        audit_details = {'date': rec.date.isoformat()}
        if rec.date != old_date:
            audit_details['date_changed_from'] = old_date.isoformat()
        log_audit('Updated Daily Reconciliation', 'DailyReconciliation', rec.id, audit_details)

        if rec.date != old_date:
            flash(f"Reconciliation sheet updated and moved from {old_date.strftime('%d/%m/%Y')} "
                  f"to {rec.date.strftime('%d/%m/%Y')}.", 'success')
        else:
            flash('Reconciliation sheet updated!', 'success')
        return redirect(url_for('reconciliation.view', rec_id=rec.id))

    # Serialize existing line items so the form can rebuild the sheets
    display = _sheet_display_data(rec)
    billing_init = [{
        'provider_id': group['provider_id'],
        'provider_name': group['provider_name'],
        'entries': [{
            'computer_no': e.computer_no or '',
            'file_no': e.file_no or '',
            'patient_name': e.patient_name or '',
            'medical_aid': e.medical_aid or '',
            'amount_billed': float(e.amount_billed or 0),
            'card_paid': float(e.card_paid or 0),
            'card_bank': e.card_bank or 'FNB',
            'eft_paid': float(e.eft_paid or 0),
            'eft_bank': e.eft_bank or 'FNB',
            'credit_note': float(e.credit_note or 0),
            'credit_note_reason': e.credit_note_reason or '',
            'journal': float(e.journal or 0),
            'journal_reason': e.journal_reason or '',
            'receipt_no': e.receipt_no or '',
        } for e in group['entries']]
    } for group in display['providers']]

    era_init = [{
        'batch_number': p.batch_number or '',
        'medical_aid_name': p.medical_aid_name or '',
        'payment_date': p.payment_date.isoformat() if p.payment_date else '',
        'amount_paid': float(p.amount_paid or 0),
    } for p in rec.era_payments]

    return render_template('reconciliation/form.html',
                          rec=rec,
                          rec_date=rec.date,
                          dentists=dentists,
                          days_of_week=DAYS_OF_WEEK,
                          billing_init=billing_init,
                          era_init=era_init,
                          credit_note_reasons=CREDIT_NOTE_REASONS,
                          journal_reasons=JOURNAL_REASONS,
                          banks=BANKS,
                          is_edit=True)


@bp.route('/view/<int:rec_id>')
@login_required
@finance_access_required
def view(rec_id):
    """View a reconciliation sheet."""
    rec = DailyReconciliation.query.get_or_404(rec_id)

    sheet = _sheet_display_data(rec)

    return render_template('reconciliation/view.html',
                          rec=rec,
                          sheet=sheet)


@bp.route('/check/<int:rec_id>', methods=['POST'])
@login_required
@manager_required
def check(rec_id):
    """Mark a reconciliation sheet as checked."""
    rec = DailyReconciliation.query.get_or_404(rec_id)

    rec.checked_by = current_user.id
    rec.checked_at = datetime.utcnow()
    rec.status = 'Checked'

    db.session.commit()

    log_audit('Checked Daily Reconciliation', 'DailyReconciliation', rec.id, {
        'date': rec.date.isoformat()
    })

    flash('Reconciliation sheet marked as checked.', 'success')
    return redirect(url_for('reconciliation.view', rec_id=rec.id))


@bp.route('/delete/<int:rec_id>', methods=['POST'])
@login_required
@manager_required
def delete(rec_id):
    """Delete a reconciliation sheet."""
    rec = DailyReconciliation.query.get_or_404(rec_id)
    rec_date = rec.date

    log_audit('Deleted Daily Reconciliation', 'DailyReconciliation', rec.id, {
        'date': rec.date.isoformat()
    })

    # Bulk-delete child rows first to avoid executemany prepared-statement
    # collisions on the connection pooler (see _apply_sheet_data)
    ReconciliationBillingEntry.query.filter_by(reconciliation_id=rec.id).delete(synchronize_session=False)
    ReconciliationEraPayment.query.filter_by(reconciliation_id=rec.id).delete(synchronize_session=False)
    db.session.expire(rec, ['billing_entries', 'era_payments'])

    db.session.delete(rec)
    db.session.commit()

    flash(f'Reconciliation sheet for {rec_date} deleted.', 'success')
    return redirect(url_for('reconciliation.index'))


@bp.route('/today')
@login_required
@finance_access_required
def today():
    """Redirect to today's reconciliation (create or edit)."""
    today_date = date.today()
    existing = DailyReconciliation.query.filter_by(date=today_date).first()

    if existing:
        return redirect(url_for('reconciliation.edit', rec_id=existing.id))
    else:
        return redirect(url_for('reconciliation.new'))


@bp.route('/analytics')
@login_required
@finance_access_required
def analytics():
    """View analytics and statistics for reconciliation data."""
    import calendar
    from sqlalchemy import func, extract

    # Get date range from parameters
    period = request.args.get('period', 'month')  # week, month, quarter, year
    today_date = date.today()

    if period == 'week':
        start_date = today_date - timedelta(days=today_date.weekday())
        end_date = today_date
        period_label = f"This Week ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')})"
    elif period == 'month':
        start_date = date(today_date.year, today_date.month, 1)
        end_date = today_date
        period_label = calendar.month_name[today_date.month] + f" {today_date.year}"
    elif period == 'quarter':
        quarter = (today_date.month - 1) // 3
        start_date = date(today_date.year, quarter * 3 + 1, 1)
        end_date = today_date
        quarter_names = ['Q1', 'Q2', 'Q3', 'Q4']
        period_label = f"{quarter_names[quarter]} {today_date.year}"
    elif period == 'year':
        start_date = date(today_date.year, 1, 1)
        end_date = today_date
        period_label = f"Year {today_date.year}"
    else:
        # Custom date range
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')
        try:
            start_date = date.fromisoformat(start_str) if start_str else date(today_date.year, today_date.month, 1)
            end_date = date.fromisoformat(end_str) if end_str else today_date
        except ValueError:
            start_date = date(today_date.year, today_date.month, 1)
            end_date = today_date
        period_label = f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"

    # Get all reconciliations in the period
    reconciliations = DailyReconciliation.query.filter(
        DailyReconciliation.date >= start_date,
        DailyReconciliation.date <= end_date
    ).order_by(DailyReconciliation.date).all()

    # Calculate summary statistics
    total_days = len(reconciliations)

    summary = {
        'total_money_in': sum(float(r.total_money_in or 0) for r in reconciliations),
        'net_collections': sum(float(r.net_collections or 0) for r in reconciliations),
        'goodx_production': sum(float(r.goodx_production or 0) for r in reconciliations),
        'goodx_collections': sum(float(r.goodx_collections or 0) for r in reconciliations),
        'patients_treated': sum(r.patients_treated or 0 for r in reconciliations),
        'no_shows': sum(r.no_shows or 0 for r in reconciliations),
        'cancelled': sum(r.cancelled or 0 for r in reconciliations),
        'rescheduled': sum(r.rescheduled or 0 for r in reconciliations),
        'walk_ins': sum(r.walk_ins_treated or 0 for r in reconciliations),
        'new_patients': sum(r.new_patients_booked or 0 for r in reconciliations),
        'total_variance': sum(float(r.variance or 0) for r in reconciliations),
        'total_refunds': sum(float(r.refunds_expenses or 0) for r in reconciliations),
    }

    # Calculate averages
    if total_days > 0:
        averages = {
            'daily_collections': summary['net_collections'] / total_days,
            'daily_patients': summary['patients_treated'] / total_days,
            'daily_no_shows': summary['no_shows'] / total_days,
            'daily_production': summary['goodx_production'] / total_days,
        }
    else:
        averages = {'daily_collections': 0, 'daily_patients': 0, 'daily_no_shows': 0, 'daily_production': 0}

    # Calculate rates
    total_appointments = summary['patients_treated'] + summary['no_shows'] + summary['cancelled']
    if total_appointments > 0:
        rates = {
            'show_rate': (summary['patients_treated'] / total_appointments) * 100,
            'no_show_rate': (summary['no_shows'] / total_appointments) * 100,
            'cancellation_rate': (summary['cancelled'] / total_appointments) * 100,
        }
    else:
        rates = {'show_rate': 0, 'no_show_rate': 0, 'cancellation_rate': 0}

    # Collection rate (collections vs production)
    if summary['goodx_production'] > 0:
        rates['collection_rate'] = (summary['goodx_collections'] / summary['goodx_production']) * 100
    else:
        rates['collection_rate'] = 0

    # Daily trends for charts
    daily_data = []
    for r in reconciliations:
        daily_data.append({
            'date': r.date.strftime('%d/%m'),
            'date_full': r.date.isoformat(),
            'net_collections': float(r.net_collections or 0),
            'production': float(r.goodx_production or 0),
            'patients': r.patients_treated or 0,
            'no_shows': r.no_shows or 0,
            'variance': float(r.variance or 0),
        })

    # Payment method breakdown
    payment_breakdown = {
        'EFT': sum(float(r.eft_received or 0) for r in reconciliations),
        'Card (FNB)': sum(float(r.card_fnb or 0) for r in reconciliations),
        'Card (Capitec)': sum(float(r.card_capitec or 0) for r in reconciliations),
        'EFT (FNB)': sum(float(r.eft_fnb or 0) for r in reconciliations),
        'EFT (Capitec)': sum(float(r.eft_capitec or 0) for r in reconciliations),
        'Medical Aid': sum(float(r.medical_aid_payments or 0) for r in reconciliations),
        'Med Aid Balance': sum(float(r.medical_aid_balance_payments or 0) for r in reconciliations),
        'Other': sum(float(r.other_payments or 0) for r in reconciliations),
    }

    # Day of week analysis
    day_analysis = {day: {'count': 0, 'collections': 0, 'patients': 0, 'no_shows': 0}
                    for day in DAYS_OF_WEEK}
    for r in reconciliations:
        if r.day_of_week:
            day_analysis[r.day_of_week]['count'] += 1
            day_analysis[r.day_of_week]['collections'] += float(r.net_collections or 0)
            day_analysis[r.day_of_week]['patients'] += r.patients_treated or 0
            day_analysis[r.day_of_week]['no_shows'] += r.no_shows or 0

    # Calculate averages per day
    for day in DAYS_OF_WEEK:
        if day_analysis[day]['count'] > 0:
            day_analysis[day]['avg_collections'] = day_analysis[day]['collections'] / day_analysis[day]['count']
            day_analysis[day]['avg_patients'] = day_analysis[day]['patients'] / day_analysis[day]['count']
        else:
            day_analysis[day]['avg_collections'] = 0
            day_analysis[day]['avg_patients'] = 0

    # Doctor performance
    doctor_stats = {}
    for r in reconciliations:
        if r.dentists_on_duty and r.appointments_booked:
            for d_id in r.dentists_on_duty:
                d_id_str = str(d_id)
                if d_id not in doctor_stats:
                    dentist = User.query.get(d_id)
                    doctor_stats[d_id] = {
                        'name': dentist.full_name if dentist else f'Doctor {d_id}',
                        'days_worked': 0,
                        'total_appointments': 0,
                    }
                doctor_stats[d_id]['days_worked'] += 1
                doctor_stats[d_id]['total_appointments'] += r.appointments_booked.get(d_id_str, 0)

    # Best and worst days
    if reconciliations:
        best_day = max(reconciliations, key=lambda r: float(r.net_collections or 0))
        worst_day = min(reconciliations, key=lambda r: float(r.net_collections or 0))
    else:
        best_day = worst_day = None

    # Per-practitioner billing and cash flow from the billing sheets.
    # ERA (KAS6) payments are made to the practice number and cannot be
    # split per practitioner, so they are reported at practice level.
    practitioner_rows = db.session.query(
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
        DailyReconciliation.date >= start_date,
        DailyReconciliation.date <= end_date
    ).group_by(
        ReconciliationBillingEntry.provider_name
    ).order_by(
        ReconciliationBillingEntry.provider_name
    ).all()

    # Billed is reported net of credit notes: a credit note reverses an
    # invoice, so gross would double-count every corrected claim.
    practitioner_stats = [{
        'name': name,
        'patients': patients,
        'gross_billed': float(billed),
        'credit_notes': float(credit),
        'billed': float(billed) - float(credit),
        'card': float(card),
        'eft': float(eft),
        'received': float(card) + float(eft),
    } for name, patients, billed, card, eft, credit in practitioner_rows]

    practitioner_totals = {
        'patients': sum(p['patients'] for p in practitioner_stats),
        'gross_billed': sum(p['gross_billed'] for p in practitioner_stats),
        'credit_notes': sum(p['credit_notes'] for p in practitioner_stats),
        'billed': sum(p['billed'] for p in practitioner_stats),
        'card': sum(p['card'] for p in practitioner_stats),
        'eft': sum(p['eft'] for p in practitioner_stats),
        'received': sum(p['received'] for p in practitioner_stats),
    }

    # Credit notes and journals broken down by reason, so the monthly report
    # shows not just how much was reversed or written off but why.
    def _by_reason(amount_column, reason_column):
        rows = db.session.query(
            reason_column,
            func.count(ReconciliationBillingEntry.id),
            func.coalesce(func.sum(amount_column), 0),
        ).join(
            DailyReconciliation,
            ReconciliationBillingEntry.reconciliation_id == DailyReconciliation.id
        ).filter(
            DailyReconciliation.date >= start_date,
            DailyReconciliation.date <= end_date,
            amount_column > 0
        ).group_by(reason_column).order_by(func.sum(amount_column).desc()).all()

        return [{
            'reason': reason or 'Not specified',
            'count': count,
            'amount': float(amount),
        } for reason, count, amount in rows]

    credit_by_reason = _by_reason(ReconciliationBillingEntry.credit_note,
                                  ReconciliationBillingEntry.credit_note_reason)
    journal_by_reason = _by_reason(ReconciliationBillingEntry.journal,
                                   ReconciliationBillingEntry.journal_reason)

    adjustments = {
        'credit_total': sum(r['amount'] for r in credit_by_reason),
        'credit_count': sum(r['count'] for r in credit_by_reason),
        'journal_total': sum(r['amount'] for r in journal_by_reason),
        'journal_count': sum(r['count'] for r in journal_by_reason),
    }

    # Practice-level ERA money received in the period (KAS6)
    era_period_total = sum(float(r.medical_aid_payments or 0) for r in reconciliations)

    return render_template('reconciliation/analytics.html',
                          period=period,
                          period_label=period_label,
                          start_date=start_date,
                          end_date=end_date,
                          total_days=total_days,
                          summary=summary,
                          averages=averages,
                          rates=rates,
                          daily_data=daily_data,
                          payment_breakdown=payment_breakdown,
                          day_analysis=day_analysis,
                          doctor_stats=doctor_stats,
                          best_day=best_day,
                          worst_day=worst_day,
                          practitioner_stats=practitioner_stats,
                          practitioner_totals=practitioner_totals,
                          credit_by_reason=credit_by_reason,
                          journal_by_reason=journal_by_reason,
                          adjustments=adjustments,
                          era_period_total=era_period_total,
                          days_of_week=DAYS_OF_WEEK)
