from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (StringField, IntegerField, DecimalField, TextAreaField,
                     DateField, SelectMultipleField, SubmitField, SelectField)
from wtforms.validators import DataRequired, Optional, NumberRange
from wtforms.widgets import ListWidget, CheckboxInput
from app import db
from app.models import DailyReconciliation, User
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from datetime import date, datetime, timedelta
from decimal import Decimal

bp = Blueprint('reconciliation', __name__, url_prefix='/reconciliation')

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


def get_dentists():
    """Get all users who can be dentists on duty (Dentist, Practice Manager, Super Admin with dental duties)."""
    return User.query.filter(
        User.status == 'Active',
        User.role.in_(['Dentist', 'Practice Manager'])
    ).order_by(User.full_name).all()


def get_all_active_staff():
    """Get all active staff members."""
    return User.query.filter_by(status='Active').order_by(User.full_name).all()


@bp.route('/')
@login_required
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
        'total_money_in': sum(r.total_money_in or 0 for r in reconciliations),
        'net_collections': sum(r.net_collections or 0 for r in reconciliations),
        'patients_treated': sum(r.patients_treated or 0 for r in reconciliations),
        'no_shows': sum(r.no_shows or 0 for r in reconciliations),
        'walk_ins': sum(r.walk_ins_treated or 0 for r in reconciliations),
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
def new(selected_date=None):
    """Create a new daily reconciliation sheet."""
    # Only receptionist, practice manager, or super admin can create
    if current_user.role not in ['Receptionist', 'Practice Manager', 'Super Admin']:
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

        # Get dentists on duty
        dentists_on_duty = request.form.getlist('dentists_on_duty')
        dentists_on_duty = [int(d) for d in dentists_on_duty if d]

        # Get appointments per dentist
        appointments_booked = {}
        for dentist_id in dentists_on_duty:
            appt_count = request.form.get(f'appointments_{dentist_id}', 0, type=int)
            appointments_booked[str(dentist_id)] = appt_count

        # Get retail sales
        retail_sales = {}
        for item in RETAIL_ITEMS:
            qty = request.form.get(f'retail_qty_{item}', 0, type=int)
            amount = request.form.get(f'retail_amount_{item}', 0, type=float)
            if qty > 0 or amount > 0:
                retail_sales[item] = {'qty': qty, 'amount': amount}

        # Create reconciliation record
        rec = DailyReconciliation(
            date=rec_date,
            day_of_week=DAYS_OF_WEEK[rec_date.weekday()],

            # Section A
            dentists_on_duty=dentists_on_duty,
            staff_on_duty=request.form.get('staff_on_duty', 0, type=int),
            appointments_booked=appointments_booked,
            confirmed_appointments=request.form.get('confirmed_appointments', 0, type=int),
            reminder_messages_sent=request.form.get('reminder_messages_sent', 0, type=int),
            new_patients_booked=request.form.get('new_patients_booked', 0, type=int),
            medical_aid_preauth_received=request.form.get('medical_aid_preauth_received', 0, type=int),
            lab_cases=request.form.get('lab_cases', 0, type=int),

            # Section B
            patients_treated=request.form.get('patients_treated', 0, type=int),
            no_shows=request.form.get('no_shows', 0, type=int),
            cancelled=request.form.get('cancelled', 0, type=int),
            rescheduled=request.form.get('rescheduled', 0, type=int),
            walk_ins_treated=request.form.get('walk_ins_treated', 0, type=int),

            # Section C - Money In
            eft_received=Decimal(request.form.get('eft_received', '0') or '0'),
            card_fnb=Decimal(request.form.get('card_fnb', '0') or '0'),
            card_capitec=Decimal(request.form.get('card_capitec', '0') or '0'),
            medical_aid_payments=Decimal(request.form.get('medical_aid_payments', '0') or '0'),
            medical_aid_balance_payments=Decimal(request.form.get('medical_aid_balance_payments', '0') or '0'),
            other_payments=Decimal(request.form.get('other_payments', '0') or '0'),
            other_payments_description=request.form.get('other_payments_description', ''),

            # Money Out
            refunds_expenses=Decimal(request.form.get('refunds_expenses', '0') or '0'),

            # Section D - Reconciliation
            goodx_production=Decimal(request.form.get('goodx_production', '0') or '0'),
            goodx_collections=Decimal(request.form.get('goodx_collections', '0') or '0'),
            variance_explanation=request.form.get('variance_explanation', ''),

            # Section E - Retail
            retail_sales=retail_sales,

            # Section F - References
            fnb_batch=request.form.get('fnb_batch', ''),
            capitec_batch=request.form.get('capitec_batch', ''),
            eft_ref=request.form.get('eft_ref', ''),
            cash_deposit=request.form.get('cash_deposit', ''),
            med_aid_ref=request.form.get('med_aid_ref', ''),

            # Sign-off
            prepared_by=current_user.id,
            prepared_at=datetime.utcnow(),
            notes=request.form.get('notes', ''),
            status='Submitted'
        )

        # Calculate totals
        rec.calculate_totals()

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
                          retail_items=RETAIL_ITEMS,
                          days_of_week=DAYS_OF_WEEK,
                          is_edit=False)


@bp.route('/edit/<int:rec_id>', methods=['GET', 'POST'])
@login_required
def edit(rec_id):
    """Edit an existing reconciliation sheet."""
    rec = DailyReconciliation.query.get_or_404(rec_id)

    # Check permissions
    if current_user.role not in ['Receptionist', 'Practice Manager', 'Super Admin']:
        flash('You do not have permission to edit reconciliation sheets.', 'danger')
        return redirect(url_for('reconciliation.index'))

    # Don't allow editing checked sheets unless manager
    if rec.status == 'Checked' and current_user.role not in ['Practice Manager', 'Super Admin']:
        flash('This sheet has been checked and cannot be edited.', 'warning')
        return redirect(url_for('reconciliation.view', rec_id=rec.id))

    dentists = get_dentists()

    if request.method == 'POST':
        # Get dentists on duty
        dentists_on_duty = request.form.getlist('dentists_on_duty')
        dentists_on_duty = [int(d) for d in dentists_on_duty if d]

        # Get appointments per dentist
        appointments_booked = {}
        for dentist_id in dentists_on_duty:
            appt_count = request.form.get(f'appointments_{dentist_id}', 0, type=int)
            appointments_booked[str(dentist_id)] = appt_count

        # Get retail sales
        retail_sales = {}
        for item in RETAIL_ITEMS:
            qty = request.form.get(f'retail_qty_{item}', 0, type=int)
            amount = request.form.get(f'retail_amount_{item}', 0, type=float)
            if qty > 0 or amount > 0:
                retail_sales[item] = {'qty': qty, 'amount': amount}

        # Update record
        rec.dentists_on_duty = dentists_on_duty
        rec.staff_on_duty = request.form.get('staff_on_duty', 0, type=int)
        rec.appointments_booked = appointments_booked
        rec.confirmed_appointments = request.form.get('confirmed_appointments', 0, type=int)
        rec.reminder_messages_sent = request.form.get('reminder_messages_sent', 0, type=int)
        rec.new_patients_booked = request.form.get('new_patients_booked', 0, type=int)
        rec.medical_aid_preauth_received = request.form.get('medical_aid_preauth_received', 0, type=int)
        rec.lab_cases = request.form.get('lab_cases', 0, type=int)

        rec.patients_treated = request.form.get('patients_treated', 0, type=int)
        rec.no_shows = request.form.get('no_shows', 0, type=int)
        rec.cancelled = request.form.get('cancelled', 0, type=int)
        rec.rescheduled = request.form.get('rescheduled', 0, type=int)
        rec.walk_ins_treated = request.form.get('walk_ins_treated', 0, type=int)

        rec.eft_received = Decimal(request.form.get('eft_received', '0') or '0')
        rec.card_fnb = Decimal(request.form.get('card_fnb', '0') or '0')
        rec.card_capitec = Decimal(request.form.get('card_capitec', '0') or '0')
        rec.medical_aid_payments = Decimal(request.form.get('medical_aid_payments', '0') or '0')
        rec.medical_aid_balance_payments = Decimal(request.form.get('medical_aid_balance_payments', '0') or '0')
        rec.other_payments = Decimal(request.form.get('other_payments', '0') or '0')
        rec.other_payments_description = request.form.get('other_payments_description', '')
        rec.refunds_expenses = Decimal(request.form.get('refunds_expenses', '0') or '0')

        rec.goodx_production = Decimal(request.form.get('goodx_production', '0') or '0')
        rec.goodx_collections = Decimal(request.form.get('goodx_collections', '0') or '0')
        rec.variance_explanation = request.form.get('variance_explanation', '')

        rec.retail_sales = retail_sales

        rec.fnb_batch = request.form.get('fnb_batch', '')
        rec.capitec_batch = request.form.get('capitec_batch', '')
        rec.eft_ref = request.form.get('eft_ref', '')
        rec.cash_deposit = request.form.get('cash_deposit', '')
        rec.med_aid_ref = request.form.get('med_aid_ref', '')

        rec.notes = request.form.get('notes', '')

        # Calculate totals
        rec.calculate_totals()

        db.session.commit()

        log_audit('Updated Daily Reconciliation', 'DailyReconciliation', rec.id, {
            'date': rec.date.isoformat()
        })

        flash('Reconciliation sheet updated!', 'success')
        return redirect(url_for('reconciliation.view', rec_id=rec.id))

    return render_template('reconciliation/form.html',
                          rec=rec,
                          rec_date=rec.date,
                          dentists=dentists,
                          retail_items=RETAIL_ITEMS,
                          days_of_week=DAYS_OF_WEEK,
                          is_edit=True)


@bp.route('/view/<int:rec_id>')
@login_required
def view(rec_id):
    """View a reconciliation sheet."""
    rec = DailyReconciliation.query.get_or_404(rec_id)

    # Get dentist names for display
    dentist_names = []
    if rec.dentists_on_duty:
        for d_id in rec.dentists_on_duty:
            dentist = User.query.get(d_id)
            if dentist:
                dentist_names.append(dentist.full_name)

    # Get appointments with dentist names
    appointments_display = {}
    if rec.appointments_booked:
        for d_id, count in rec.appointments_booked.items():
            dentist = User.query.get(int(d_id))
            if dentist:
                appointments_display[dentist.full_name] = count

    return render_template('reconciliation/view.html',
                          rec=rec,
                          dentist_names=dentist_names,
                          appointments_display=appointments_display,
                          retail_items=RETAIL_ITEMS)


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

    db.session.delete(rec)
    db.session.commit()

    flash(f'Reconciliation sheet for {rec_date} deleted.', 'success')
    return redirect(url_for('reconciliation.index'))


@bp.route('/today')
@login_required
def today():
    """Redirect to today's reconciliation (create or edit)."""
    today_date = date.today()
    existing = DailyReconciliation.query.filter_by(date=today_date).first()

    if existing:
        return redirect(url_for('reconciliation.edit', rec_id=existing.id))
    else:
        return redirect(url_for('reconciliation.new'))
