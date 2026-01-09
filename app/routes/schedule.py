from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import SelectField, DateField, TextAreaField, SubmitField, TimeField, BooleanField
from wtforms.validators import DataRequired, Optional
from app import db
from app.models import Schedule, User, LeaveRequest
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from app.utils.helpers import can_schedule, get_leave_for_date
from datetime import date, timedelta, time
import calendar

bp = Blueprint('schedule', __name__, url_prefix='/schedule')

# Practice rooms for dental assistants (rotation)
PRACTICE_ROOMS = ['Black Room', 'Red Room', 'Pink Room']

# Fixed room assignments for dentists (by name)
DENTIST_ROOMS = {
    'Dr. Buleni': 'Black Room',
    'Dr. Ramakuwela': 'Red Room',
    'Zwane': 'Pink Room'
}

ROOM_CHOICES = [
    ('', 'No Room Assigned'),
    ('Black Room', 'Black Room'),
    ('Red Room', 'Red Room'),
    ('Pink Room', 'Pink Room')
]

# Shift types
SHIFT_TYPES = [
    ('Full Day', 'Full Day'),
    ('Morning', 'Morning'),
    ('Afternoon', 'Afternoon'),
    ('Off', 'Off/Not Working')
]

# Standard work hours
STANDARD_START = time(8, 0)   # 8:00 AM
STANDARD_END = time(17, 0)    # 5:00 PM (Mon-Fri)
SATURDAY_END = time(13, 0)    # 1:00 PM (Saturday)


def get_week_dates(start_date):
    """Get all dates for a week starting from Monday."""
    # Adjust to Monday
    monday = start_date - timedelta(days=start_date.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def is_on_leave(staff_id, check_date):
    """Check if staff member is on approved leave for a date."""
    leave = LeaveRequest.query.filter(
        LeaveRequest.staff_id == staff_id,
        LeaveRequest.status == 'Approved',
        LeaveRequest.start_date <= check_date,
        LeaveRequest.end_date >= check_date
    ).first()
    return leave is not None


def get_dentist_room(staff_name):
    """Get the fixed room assignment for a dentist based on their name."""
    for name_key, room in DENTIST_ROOMS.items():
        if name_key.lower() in staff_name.lower():
            return room
    return None


def auto_generate_schedule(week_start, created_by_id):
    """
    Automatically generate schedule for a week.
    - All active staff work Monday-Friday (8am-5pm)
    - Saturday: Staff take turns working (8am-1pm) - rotating each week
    - Dentists have FIXED room assignments (Dr. Buleni=Black, Dr. Ramakuwela=Red, Zwane=Pink)
    - Dental assistants ROTATE through Black/Red/Pink rooms
    - Staff on leave are automatically excluded
    - Super Admin is excluded (administrative role only)
    """
    week_dates = get_week_dates(week_start)
    weekdays = week_dates[:5]  # Monday to Friday
    saturday = week_dates[5]   # Saturday

    # Get all active staff (exclude Super Admin - administrative only)
    staff = User.query.filter(
        User.status == 'Active',
        User.role != 'Super Admin'
    ).all()

    # Separate staff by role
    dental_assistants = [s for s in staff if s.role == 'Dental Assistant']
    dentists = [s for s in staff if s.role == 'Dentist']
    other_staff = [s for s in staff if s.role not in ['Dental Assistant', 'Dentist']]

    created_count = 0
    skipped_leave = 0
    skipped_exists = 0

    # ===== MONDAY TO FRIDAY: Everyone works =====

    # Schedule dentists with FIXED room assignments (Mon-Fri)
    for dentist in dentists:
        room = get_dentist_room(dentist.full_name)

        for work_date in weekdays:
            # Skip if on leave
            if is_on_leave(dentist.id, work_date):
                skipped_leave += 1
                continue

            # Skip if already scheduled
            existing = Schedule.query.filter_by(
                staff_id=dentist.id,
                date=work_date
            ).first()

            if existing:
                skipped_exists += 1
                continue

            schedule = Schedule(
                staff_id=dentist.id,
                date=work_date,
                role=dentist.role,
                shift_type='Full Day',
                room=room,
                start_time=STANDARD_START,
                end_time=STANDARD_END,
                created_by=created_by_id
            )
            db.session.add(schedule)
            created_count += 1

    # Schedule other staff (receptionists, cleaners, etc.) - Mon-Fri
    for member in other_staff:
        for work_date in weekdays:
            # Skip if on leave
            if is_on_leave(member.id, work_date):
                skipped_leave += 1
                continue

            # Skip if already scheduled
            existing = Schedule.query.filter_by(
                staff_id=member.id,
                date=work_date
            ).first()

            if existing:
                skipped_exists += 1
                continue

            schedule = Schedule(
                staff_id=member.id,
                date=work_date,
                role=member.role,
                shift_type='Full Day',
                start_time=STANDARD_START,
                end_time=STANDARD_END,
                created_by=created_by_id
            )
            db.session.add(schedule)
            created_count += 1

    # Schedule dental assistants with ROTATING room assignments (Mon-Fri)
    if dental_assistants:
        for day_idx, work_date in enumerate(weekdays):
            available_assistants = [
                da for da in dental_assistants
                if not is_on_leave(da.id, work_date)
            ]

            for i, assistant in enumerate(available_assistants):
                # Skip if already scheduled
                existing = Schedule.query.filter_by(
                    staff_id=assistant.id,
                    date=work_date
                ).first()

                if existing:
                    skipped_exists += 1
                    continue

                # Rotate room assignment based on day and assistant index
                room_idx = (day_idx + i) % len(PRACTICE_ROOMS)
                room = PRACTICE_ROOMS[room_idx]

                schedule = Schedule(
                    staff_id=assistant.id,
                    date=work_date,
                    role='Dental Assistant',
                    shift_type='Full Day',
                    room=room,
                    start_time=STANDARD_START,
                    end_time=STANDARD_END,
                    created_by=created_by_id
                )
                db.session.add(schedule)
                created_count += 1

    # ===== SATURDAY: Staff take turns (8am-1pm) =====
    # Use week number to rotate who works on Saturday
    week_number = saturday.isocalendar()[1]

    # Get all available staff for Saturday (not on leave)
    available_dentists = [d for d in dentists if not is_on_leave(d.id, saturday)]
    available_assistants = [da for da in dental_assistants if not is_on_leave(da.id, saturday)]
    available_other = [s for s in other_staff if not is_on_leave(s.id, saturday)]

    # Rotate which dentist works Saturday (one at a time based on week)
    if available_dentists:
        saturday_dentist_idx = week_number % len(available_dentists)
        saturday_dentist = available_dentists[saturday_dentist_idx]

        existing = Schedule.query.filter_by(
            staff_id=saturday_dentist.id,
            date=saturday
        ).first()

        if not existing:
            room = get_dentist_room(saturday_dentist.full_name)
            schedule = Schedule(
                staff_id=saturday_dentist.id,
                date=saturday,
                role=saturday_dentist.role,
                shift_type='Morning',
                room=room,
                start_time=STANDARD_START,
                end_time=SATURDAY_END,
                created_by=created_by_id
            )
            db.session.add(schedule)
            created_count += 1

    # Rotate which dental assistant works Saturday (one at a time based on week)
    if available_assistants:
        saturday_assistant_idx = week_number % len(available_assistants)
        saturday_assistant = available_assistants[saturday_assistant_idx]

        existing = Schedule.query.filter_by(
            staff_id=saturday_assistant.id,
            date=saturday
        ).first()

        if not existing:
            # Assistant works in same room as the dentist on Saturday
            if available_dentists:
                room = get_dentist_room(available_dentists[saturday_dentist_idx].full_name)
            else:
                room = PRACTICE_ROOMS[week_number % len(PRACTICE_ROOMS)]

            schedule = Schedule(
                staff_id=saturday_assistant.id,
                date=saturday,
                role='Dental Assistant',
                shift_type='Morning',
                room=room,
                start_time=STANDARD_START,
                end_time=SATURDAY_END,
                created_by=created_by_id
            )
            db.session.add(schedule)
            created_count += 1

    # Rotate which other staff (receptionist, cleaner) works Saturday
    if available_other:
        saturday_other_idx = week_number % len(available_other)
        saturday_other = available_other[saturday_other_idx]

        existing = Schedule.query.filter_by(
            staff_id=saturday_other.id,
            date=saturday
        ).first()

        if not existing:
            schedule = Schedule(
                staff_id=saturday_other.id,
                date=saturday,
                role=saturday_other.role,
                shift_type='Morning',
                start_time=STANDARD_START,
                end_time=SATURDAY_END,
                created_by=created_by_id
            )
            db.session.add(schedule)
            created_count += 1

    db.session.commit()
    return created_count, skipped_leave, skipped_exists


def remove_schedule_for_leave(leave_request):
    """Remove scheduled entries that conflict with an approved leave request."""
    # Find and delete schedules that fall within the leave period
    conflicting = Schedule.query.filter(
        Schedule.staff_id == leave_request.staff_id,
        Schedule.date >= leave_request.start_date,
        Schedule.date <= leave_request.end_date
    ).all()

    count = len(conflicting)
    for schedule in conflicting:
        db.session.delete(schedule)

    db.session.commit()
    return count


class ScheduleForm(FlaskForm):
    staff_id = SelectField('Staff Member', coerce=int, validators=[DataRequired()])
    date = DateField('Date', validators=[DataRequired()])
    shift_type = SelectField('Shift Type', choices=SHIFT_TYPES, validators=[DataRequired()])
    role = SelectField('Role', choices=[
        ('Staff', 'Staff'),
        ('Receptionist', 'Receptionist'),
        ('Dentist', 'Dentist'),
        ('Dental Assistant', 'Dental Assistant'),
        ('Cleaner', 'Cleaner'),
        ('Practice Manager', 'Practice Manager')
    ], validators=[DataRequired()])
    room = SelectField('Room Assignment', choices=ROOM_CHOICES, validators=[Optional()])
    start_time = TimeField('Start Time', validators=[Optional()])
    end_time = TimeField('End Time', validators=[Optional()])
    notes = TextAreaField('Notes')
    submit = SubmitField('Add to Schedule')


class AutoScheduleForm(FlaskForm):
    """Form for auto-generating weekly schedules."""
    week_start = DateField('Week Starting (Monday)', validators=[DataRequired()])
    include_existing = BooleanField('Skip days already scheduled', default=True)
    submit = SubmitField('Generate Schedule')


@bp.route('/')
@login_required
def index():
    """View monthly schedule."""
    # Get month and year from query params or use current
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)

    # Get calendar data
    cal = calendar.Calendar(firstweekday=0)  # Monday first
    month_days = cal.monthdayscalendar(year, month)

    # Get all schedule entries for this month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    schedules = Schedule.query.filter(
        Schedule.date >= first_day,
        Schedule.date <= last_day
    ).all()

    # Get leave requests for this month
    leave_requests = LeaveRequest.query.filter(
        LeaveRequest.status == 'Approved',
        LeaveRequest.start_date <= last_day,
        LeaveRequest.end_date >= first_day
    ).all()

    # Get all active staff
    staff = User.query.filter_by(status='Active').all()

    # Organize data by date
    schedule_by_date = {}
    for s in schedules:
        day_key = s.date.day
        if day_key not in schedule_by_date:
            schedule_by_date[day_key] = []
        schedule_by_date[day_key].append(s)

    leave_by_date = {}
    for leave in leave_requests:
        current = max(leave.start_date, first_day)
        end = min(leave.end_date, last_day)
        while current <= end:
            if current.month == month:
                day_key = current.day
                if day_key not in leave_by_date:
                    leave_by_date[day_key] = []
                leave_by_date[day_key].append(leave)
            current += timedelta(days=1)

    # Navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render_template('schedule/index.html',
                          month_days=month_days,
                          year=year,
                          month=month,
                          month_name=calendar.month_name[month],
                          schedule_by_date=schedule_by_date,
                          leave_by_date=leave_by_date,
                          staff=staff,
                          prev_month=prev_month,
                          prev_year=prev_year,
                          next_month=next_month,
                          next_year=next_year,
                          today=date.today())


@bp.route('/auto-generate', methods=['GET', 'POST'])
@login_required
@manager_required
def auto_generate():
    """Auto-generate weekly schedule."""
    form = AutoScheduleForm()

    if form.validate_on_submit():
        week_start = form.week_start.data
        # Adjust to Monday if not already
        week_start = week_start - timedelta(days=week_start.weekday())

        created, skipped_leave, skipped_exists = auto_generate_schedule(
            week_start,
            current_user.id
        )

        log_audit('Auto-generated Schedule', 'Schedule', None, {
            'week_start': week_start.isoformat(),
            'created': created,
            'skipped_leave': skipped_leave,
            'skipped_existing': skipped_exists
        })

        msg = f'Schedule generated: {created} entries created.'
        if skipped_leave > 0:
            msg += f' {skipped_leave} skipped (on leave).'
        if skipped_exists > 0:
            msg += f' {skipped_exists} skipped (already scheduled).'

        flash(msg, 'success')
        return redirect(url_for('schedule.index'))

    # Default to next Monday
    today = date.today()
    next_monday = today + timedelta(days=(7 - today.weekday()))
    form.week_start.data = next_monday

    return render_template('schedule/auto_generate.html', form=form)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
@manager_required
def add():
    """Add staff to schedule manually."""
    form = ScheduleForm()
    staff_list = User.query.filter_by(status='Active').all()
    form.staff_id.choices = [(u.id, f"{u.full_name} ({u.role})") for u in staff_list]

    if form.validate_on_submit():
        # Check if staff is on approved leave
        if is_on_leave(form.staff_id.data, form.date.data):
            leave = get_leave_for_date(form.staff_id.data, form.date.data)
            flash(f'Cannot schedule: Staff member is on approved {leave.leave_type} leave.', 'danger')
            return render_template('schedule/add.html', form=form, rooms=ROOM_CHOICES)

        # Check if already scheduled
        existing = Schedule.query.filter_by(
            staff_id=form.staff_id.data,
            date=form.date.data
        ).first()

        if existing:
            flash('Staff member is already scheduled for this date.', 'danger')
            return render_template('schedule/add.html', form=form, rooms=ROOM_CHOICES)

        schedule = Schedule(
            staff_id=form.staff_id.data,
            date=form.date.data,
            role=form.role.data,
            shift_type=form.shift_type.data,
            room=form.room.data if form.room.data else None,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            notes=form.notes.data,
            created_by=current_user.id
        )
        db.session.add(schedule)
        db.session.commit()

        log_audit('Added Schedule', 'Schedule', schedule.id, {
            'staff_id': schedule.staff_id,
            'date': schedule.date.isoformat(),
            'role': schedule.role,
            'shift_type': schedule.shift_type,
            'room': schedule.room
        })

        flash('Staff member added to schedule.', 'success')
        return redirect(url_for('schedule.index'))

    # Pre-select date if provided in query
    if 'date' in request.args:
        try:
            form.date.data = date.fromisoformat(request.args.get('date'))
        except ValueError:
            pass

    return render_template('schedule/add.html', form=form, rooms=ROOM_CHOICES)


@bp.route('/<int:schedule_id>/delete', methods=['POST'])
@login_required
@manager_required
def delete(schedule_id):
    """Remove staff from schedule."""
    schedule = Schedule.query.get_or_404(schedule_id)

    log_audit('Deleted Schedule', 'Schedule', schedule.id, {
        'staff_id': schedule.staff_id,
        'date': schedule.date.isoformat()
    })

    db.session.delete(schedule)
    db.session.commit()

    flash('Schedule entry removed.', 'success')
    return redirect(url_for('schedule.index'))


@bp.route('/weekly')
@login_required
def weekly_view():
    """Weekly schedule view with room assignments."""
    # Get week start from query params or use current week
    week_start_str = request.args.get('week_start')
    if week_start_str:
        try:
            week_start = date.fromisoformat(week_start_str)
        except ValueError:
            week_start = date.today() - timedelta(days=date.today().weekday())
    else:
        week_start = date.today() - timedelta(days=date.today().weekday())

    week_end = week_start + timedelta(days=6)

    # Get all schedules for this week
    schedules = Schedule.query.filter(
        Schedule.date >= week_start,
        Schedule.date <= week_end
    ).all()

    # Get all staff
    staff = User.query.filter_by(status='Active').order_by(User.role, User.full_name).all()

    # Organize by staff and date
    schedule_grid = {}
    for member in staff:
        schedule_grid[member.id] = {
            'staff': member,
            'days': {}
        }
        for i in range(7):
            schedule_grid[member.id]['days'][i] = None

    for s in schedules:
        if s.staff_id in schedule_grid:
            day_index = (s.date - week_start).days
            if 0 <= day_index < 7:
                schedule_grid[s.staff_id]['days'][day_index] = s

    # Get leave for this week
    leave_requests = LeaveRequest.query.filter(
        LeaveRequest.status == 'Approved',
        LeaveRequest.start_date <= week_end,
        LeaveRequest.end_date >= week_start
    ).all()

    leave_by_staff_date = {}
    for leave in leave_requests:
        if leave.staff_id not in leave_by_staff_date:
            leave_by_staff_date[leave.staff_id] = {}
        current = max(leave.start_date, week_start)
        while current <= min(leave.end_date, week_end):
            day_index = (current - week_start).days
            leave_by_staff_date[leave.staff_id][day_index] = leave
            current += timedelta(days=1)

    # Navigation
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    # Generate day headers
    days = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        days.append({
            'date': day_date,
            'name': calendar.day_abbr[i],
            'is_today': day_date == date.today()
        })

    return render_template('schedule/weekly.html',
                          week_start=week_start,
                          week_end=week_end,
                          days=days,
                          schedule_grid=schedule_grid,
                          leave_by_staff_date=leave_by_staff_date,
                          prev_week=prev_week,
                          next_week=next_week,
                          rooms=PRACTICE_ROOMS)


@bp.route('/rooms')
@login_required
def room_view():
    """View schedule by room assignments for dental assistants."""
    # Get date from query params or use today
    view_date_str = request.args.get('date')
    if view_date_str:
        try:
            view_date = date.fromisoformat(view_date_str)
        except ValueError:
            view_date = date.today()
    else:
        view_date = date.today()

    # Get schedules for this date with room assignments
    schedules = Schedule.query.filter(
        Schedule.date == view_date,
        Schedule.room.isnot(None),
        Schedule.room != ''
    ).all()

    # Organize by room
    room_schedules = {
        'Black Room': [],
        'Red Room': [],
        'Pink Room': []
    }

    for s in schedules:
        if s.room in room_schedules:
            room_schedules[s.room].append(s)

    # Navigation
    prev_date = view_date - timedelta(days=1)
    next_date = view_date + timedelta(days=1)

    return render_template('schedule/rooms.html',
                          view_date=view_date,
                          room_schedules=room_schedules,
                          prev_date=prev_date,
                          next_date=next_date)


@bp.route('/clear-week', methods=['POST'])
@login_required
@manager_required
def clear_week():
    """Clear all schedules for a specific week."""
    week_start_str = request.form.get('week_start')
    if not week_start_str:
        flash('No week specified.', 'danger')
        return redirect(url_for('schedule.index'))

    try:
        week_start = date.fromisoformat(week_start_str)
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('schedule.index'))

    week_end = week_start + timedelta(days=6)

    # Delete all schedules for this week
    deleted = Schedule.query.filter(
        Schedule.date >= week_start,
        Schedule.date <= week_end
    ).delete()

    db.session.commit()

    log_audit('Cleared Week Schedule', 'Schedule', None, {
        'week_start': week_start.isoformat(),
        'deleted_count': deleted
    })

    flash(f'Cleared {deleted} schedule entries for the week.', 'success')
    return redirect(url_for('schedule.weekly_view', week_start=week_start.isoformat()))
