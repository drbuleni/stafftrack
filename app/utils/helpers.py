from datetime import datetime, date, timedelta
from app import db
from app.models import Receipt, LeaveRequest


def generate_receipt_number():
    """
    Generate a unique receipt number.
    Format: RCP-YYYYMMDD-XXXX
    Example: RCP-20260108-0001
    """
    today = datetime.today().strftime('%Y%m%d')
    count = Receipt.query.filter(
        Receipt.receipt_number.like(f'RCP-{today}-%')
    ).count()
    return f'RCP-{today}-{count + 1:04d}'


def can_schedule(staff_id, schedule_date):
    """
    Check if a staff member can be scheduled on a given date.
    Returns False if they have approved leave that day.
    """
    if isinstance(schedule_date, str):
        schedule_date = datetime.strptime(schedule_date, '%Y-%m-%d').date()

    approved_leave = LeaveRequest.query.filter(
        LeaveRequest.staff_id == staff_id,
        LeaveRequest.status == 'Approved',
        LeaveRequest.start_date <= schedule_date,
        LeaveRequest.end_date >= schedule_date
    ).first()

    return approved_leave is None


def get_leave_for_date(staff_id, check_date):
    """Get approved leave for a staff member on a specific date."""
    if isinstance(check_date, str):
        check_date = datetime.strptime(check_date, '%Y-%m-%d').date()

    return LeaveRequest.query.filter(
        LeaveRequest.staff_id == staff_id,
        LeaveRequest.status == 'Approved',
        LeaveRequest.start_date <= check_date,
        LeaveRequest.end_date >= check_date
    ).first()


def allowed_file(filename, allowed_extensions):
    """Check if a file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def format_currency(amount):
    """Format a number as South African Rand."""
    return f"R {amount:,.2f}"


def get_week_start(dt=None):
    """Get the Monday of the week for a given date."""
    if dt is None:
        dt = date.today()
    if isinstance(dt, str):
        dt = datetime.strptime(dt, '%Y-%m-%d').date()

    # Calculate days since Monday (Monday = 0)
    days_since_monday = dt.weekday()
    return dt - timedelta(days=days_since_monday)
