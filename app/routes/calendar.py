from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DateField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Optional
from app import db
from app.models import CalendarEvent, User, LeaveRequest, Announcement
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from datetime import date, timedelta
import calendar as cal

bp = Blueprint('calendar', __name__, url_prefix='/calendar')

# Event types with their colors
EVENT_TYPES = [
    ('Birthday', 'success'),
    ('Awareness Day', 'info'),
    ('Holiday', 'danger'),
    ('Meeting', 'primary'),
    ('Training', 'warning'),
    ('Other', 'secondary')
]

EVENT_TYPE_CHOICES = [(t[0], t[0]) for t in EVENT_TYPES]
COLOR_MAP = {t[0]: t[1] for t in EVENT_TYPES}


class CalendarEventForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    event_date = DateField('Date', validators=[DataRequired()])
    event_type = SelectField('Event Type', choices=EVENT_TYPE_CHOICES, validators=[DataRequired()])
    is_recurring = BooleanField('Repeats Yearly')
    staff_id = SelectField('Link to Staff (for birthdays)', coerce=int, validators=[Optional()])
    submit = SubmitField('Save Event')


@bp.route('/')
@login_required
def index():
    """Display calendar view."""
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)

    # Handle month overflow
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    # Get calendar data
    month_calendar = cal.monthcalendar(year, month)
    month_name = cal.month_name[month]

    # Calculate first and last day of month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # Get calendar events for this month
    events = CalendarEvent.query.filter(
        CalendarEvent.event_date >= first_day,
        CalendarEvent.event_date <= last_day
    ).all()

    # Also get recurring events (match month and day from any year)
    recurring_events = CalendarEvent.query.filter(
        CalendarEvent.is_recurring == True,
        db.extract('month', CalendarEvent.event_date) == month
    ).all()

    # Get approved leave for this month
    leave_requests = LeaveRequest.query.filter(
        LeaveRequest.status == 'Approved',
        LeaveRequest.start_date <= last_day,
        LeaveRequest.end_date >= first_day
    ).all()

    # Organize events by date
    events_by_date = {}

    # Add regular events
    for event in events:
        day = event.event_date.day
        if day not in events_by_date:
            events_by_date[day] = []
        events_by_date[day].append({
            'id': event.id,
            'title': event.title,
            'type': event.event_type,
            'color': COLOR_MAP.get(event.event_type, 'secondary'),
            'description': event.description,
            'is_recurring': event.is_recurring
        })

    # Add recurring events (birthdays, awareness days)
    for event in recurring_events:
        if event not in events:  # Avoid duplicates
            day = event.event_date.day
            if day not in events_by_date:
                events_by_date[day] = []
            # Check if this recurring event is already added
            already_added = any(e['id'] == event.id for e in events_by_date.get(day, []))
            if not already_added:
                events_by_date[day].append({
                    'id': event.id,
                    'title': event.title,
                    'type': event.event_type,
                    'color': COLOR_MAP.get(event.event_type, 'secondary'),
                    'description': event.description,
                    'is_recurring': True
                })

    # Add leave to calendar
    leave_by_date = {}
    for leave in leave_requests:
        current_date = max(leave.start_date, first_day)
        end = min(leave.end_date, last_day)
        while current_date <= end:
            if current_date.month == month:
                day = current_date.day
                if day not in leave_by_date:
                    leave_by_date[day] = []
                leave_by_date[day].append({
                    'staff': leave.staff,
                    'type': leave.leave_type
                })
            current_date += timedelta(days=1)

    # Navigation
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1

    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1

    return render_template('calendar/index.html',
                          month_calendar=month_calendar,
                          month=month,
                          year=year,
                          month_name=month_name,
                          today=today,
                          events_by_date=events_by_date,
                          leave_by_date=leave_by_date,
                          prev_month=prev_month,
                          prev_year=prev_year,
                          next_month=next_month,
                          next_year=next_year)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@manager_required
def add():
    """Add a new calendar event."""
    form = CalendarEventForm()

    # Populate staff choices for birthday linking
    staff = User.query.filter_by(status='Active').order_by(User.full_name).all()
    form.staff_id.choices = [(0, '-- None --')] + [(s.id, s.full_name) for s in staff]

    if form.validate_on_submit():
        event = CalendarEvent(
            title=form.title.data,
            description=form.description.data,
            event_date=form.event_date.data,
            event_type=form.event_type.data,
            color=COLOR_MAP.get(form.event_type.data, 'secondary'),
            is_recurring=form.is_recurring.data,
            staff_id=form.staff_id.data if form.staff_id.data != 0 else None,
            created_by=current_user.id
        )
        db.session.add(event)
        db.session.commit()

        log_audit('Created Calendar Event', 'CalendarEvent', event.id, {
            'title': event.title,
            'date': event.event_date.isoformat(),
            'type': event.event_type
        })

        flash(f'Event "{event.title}" added to calendar.', 'success')
        return redirect(url_for('calendar.index',
                               year=event.event_date.year,
                               month=event.event_date.month))

    return render_template('calendar/event_form.html', form=form, title='Add Event')


@bp.route('/edit/<int:event_id>', methods=['GET', 'POST'])
@login_required
@manager_required
def edit(event_id):
    """Edit a calendar event."""
    event = CalendarEvent.query.get_or_404(event_id)
    form = CalendarEventForm(obj=event)

    # Populate staff choices
    staff = User.query.filter_by(status='Active').order_by(User.full_name).all()
    form.staff_id.choices = [(0, '-- None --')] + [(s.id, s.full_name) for s in staff]

    if form.validate_on_submit():
        event.title = form.title.data
        event.description = form.description.data
        event.event_date = form.event_date.data
        event.event_type = form.event_type.data
        event.color = COLOR_MAP.get(form.event_type.data, 'secondary')
        event.is_recurring = form.is_recurring.data
        event.staff_id = form.staff_id.data if form.staff_id.data != 0 else None

        db.session.commit()

        log_audit('Updated Calendar Event', 'CalendarEvent', event.id, {
            'title': event.title,
            'date': event.event_date.isoformat(),
            'type': event.event_type
        })

        flash(f'Event "{event.title}" updated.', 'success')
        return redirect(url_for('calendar.index',
                               year=event.event_date.year,
                               month=event.event_date.month))

    # Pre-select staff if linked
    if event.staff_id:
        form.staff_id.data = event.staff_id

    return render_template('calendar/event_form.html', form=form, title='Edit Event', event=event)


@bp.route('/delete/<int:event_id>', methods=['POST'])
@login_required
@manager_required
def delete(event_id):
    """Delete a calendar event."""
    event = CalendarEvent.query.get_or_404(event_id)
    event_date = event.event_date

    log_audit('Deleted Calendar Event', 'CalendarEvent', event.id, {
        'title': event.title,
        'date': event.event_date.isoformat()
    })

    db.session.delete(event)
    db.session.commit()

    flash('Event deleted.', 'success')
    return redirect(url_for('calendar.index', year=event_date.year, month=event_date.month))


@bp.route('/view/<int:event_id>')
@login_required
def view(event_id):
    """View event details."""
    event = CalendarEvent.query.get_or_404(event_id)
    return render_template('calendar/view.html', event=event, color_map=COLOR_MAP)


@bp.route('/upcoming')
@login_required
def upcoming():
    """Show upcoming events for the next 30 days."""
    today = date.today()
    end_date = today + timedelta(days=30)

    # Get regular events
    events = CalendarEvent.query.filter(
        CalendarEvent.event_date >= today,
        CalendarEvent.event_date <= end_date
    ).order_by(CalendarEvent.event_date).all()

    # Get recurring events for the next 30 days
    upcoming_events = []
    for event in events:
        upcoming_events.append({
            'event': event,
            'date': event.event_date,
            'color': COLOR_MAP.get(event.event_type, 'secondary')
        })

    # Check for recurring events
    recurring = CalendarEvent.query.filter_by(is_recurring=True).all()
    for event in recurring:
        # Create this year's occurrence
        try:
            this_year_date = date(today.year, event.event_date.month, event.event_date.day)
            if today <= this_year_date <= end_date:
                if not any(e['event'].id == event.id and e['date'] == this_year_date for e in upcoming_events):
                    upcoming_events.append({
                        'event': event,
                        'date': this_year_date,
                        'color': COLOR_MAP.get(event.event_type, 'secondary')
                    })
        except ValueError:
            pass  # Invalid date (e.g., Feb 30)

    # Sort by date
    upcoming_events.sort(key=lambda x: x['date'])

    return render_template('calendar/upcoming.html',
                          upcoming_events=upcoming_events,
                          today=today)
