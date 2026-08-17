"""Daily patient flow: how many patients were treated, walked in, or did not show.

Kept separate from Daily Reconciliation on purpose - Sinah asked for patient
flow to stand on its own rather than sit inside the money sheet. The counts
feed the monthly turnover report.
"""
import calendar
from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import PatientFlow
from app.routes.reconciliation import finance_access_required
from app.utils.audit import log_audit
from app.utils.decorators import manager_required

bp = Blueprint('patient_flow', __name__, url_prefix='/patient-flow')

FIELDS = [
    ('treated', 'Patients treated', 'Seen by a practitioner today'),
    ('walk_ins', 'Walk-ins', 'Treated without a booking'),
    ('no_shows', 'No-shows', 'Booked but did not arrive'),
]


def _count(field):
    """Read a non-negative integer from the form."""
    value = request.form.get(field, type=int)
    return max(value, 0) if value else 0


def _month_bounds(year, month):
    first = date(year, month, 1)
    return first, date(year, month, calendar.monthrange(year, month)[1])


def month_totals(year, month):
    """Totals for a month, used here and by the turnover report."""
    first, last = _month_bounds(year, month)
    row = db.session.query(
        func.coalesce(func.sum(PatientFlow.treated), 0),
        func.coalesce(func.sum(PatientFlow.walk_ins), 0),
        func.coalesce(func.sum(PatientFlow.no_shows), 0),
        func.count(PatientFlow.id),
    ).filter(PatientFlow.date >= first, PatientFlow.date <= last).one()

    treated, walk_ins, no_shows, days = row
    expected = treated + no_shows
    return {
        'treated': treated,
        'walk_ins': walk_ins,
        'no_shows': no_shows,
        'days_recorded': days,
        'expected': expected,
        'no_show_rate': (no_shows / expected * 100) if expected else 0,
        'walk_in_share': (walk_ins / treated * 100) if treated else 0,
    }


@bp.route('/')
@login_required
@finance_access_required
def index():
    """Month view of daily patient flow."""
    today = date.today()
    month = min(max(request.args.get('month', today.month, type=int), 1), 12)
    year = request.args.get('year', today.year, type=int)
    first, last = _month_bounds(year, month)

    entries = PatientFlow.query.filter(
        PatientFlow.date >= first, PatientFlow.date <= last
    ).order_by(PatientFlow.date.desc()).all()

    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)

    return render_template('patient_flow/index.html',
                           entries=entries,
                           totals=month_totals(year, month),
                           month=month, year=year,
                           month_name=calendar.month_name[month],
                           prev_month=prev_month, prev_year=prev_year,
                           next_month=next_month, next_year=next_year,
                           today=today)


@bp.route('/record', methods=['GET', 'POST'])
@bp.route('/record/<selected_date>', methods=['GET', 'POST'])
@login_required
@finance_access_required
def record(selected_date=None):
    """Capture or update one day's counts."""
    try:
        flow_date = date.fromisoformat(selected_date) if selected_date else date.today()
    except ValueError:
        flow_date = date.today()

    entry = PatientFlow.query.filter_by(date=flow_date).first()

    if request.method == 'POST':
        form_date = request.form.get('date')
        if form_date:
            try:
                flow_date = date.fromisoformat(form_date)
            except ValueError:
                pass

        # Editing an existing day rather than creating a duplicate
        entry = PatientFlow.query.filter_by(date=flow_date).first()
        is_new = entry is None
        if is_new:
            entry = PatientFlow(date=flow_date, recorded_by=current_user.id)
            db.session.add(entry)

        entry.treated = _count('treated')
        entry.walk_ins = _count('walk_ins')
        entry.no_shows = _count('no_shows')
        entry.notes = request.form.get('notes', '')
        db.session.commit()

        log_audit('Recorded Patient Flow', 'PatientFlow', entry.id, {
            'date': entry.date.isoformat(),
            'treated': entry.treated,
            'walk_ins': entry.walk_ins,
            'no_shows': entry.no_shows,
        })

        flash(f"Patient flow for {flow_date.strftime('%d/%m/%Y')} "
              f"{'recorded' if is_new else 'updated'}.", 'success')
        return redirect(url_for('patient_flow.index',
                                month=flow_date.month, year=flow_date.year))

    return render_template('patient_flow/record.html',
                           entry=entry, flow_date=flow_date, fields=FIELDS)


@bp.route('/delete/<int:entry_id>', methods=['POST'])
@login_required
@manager_required
def delete(entry_id):
    entry = PatientFlow.query.get_or_404(entry_id)
    entry_date = entry.date

    log_audit('Deleted Patient Flow', 'PatientFlow', entry.id,
              {'date': entry_date.isoformat()})
    db.session.delete(entry)
    db.session.commit()

    flash(f"Patient flow for {entry_date.strftime('%d/%m/%Y')} deleted.", 'success')
    return redirect(url_for('patient_flow.index',
                            month=entry_date.month, year=entry_date.year))
