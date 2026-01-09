from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import SelectField, DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired
from app import db, mail
from app.models import LeaveRequest, User, PerformanceEvent, Schedule, Notification
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from app.utils.email import (
    send_email, email_leave_request_submitted,
    email_leave_request_approved, email_leave_request_rejected
)
from datetime import datetime, date, timedelta

bp = Blueprint('leave', __name__, url_prefix='/leave')

# SA BCEA Leave Types and Entitlements
# Annual Leave: 21 consecutive days (or by agreement: 1 day per 17 days worked, or 1 hour per 17 hours worked)
# Sick Leave: 30 days over a 3-year cycle (6 weeks)
# Maternity Leave: 4 consecutive months (unpaid unless UIF)
# Family Responsibility Leave: 3 days per year (birth, illness, death of close family)
# Parental Leave: 10 consecutive days (unpaid, for fathers/partners when child is born)
# Adoption Leave: 10 consecutive weeks (unpaid, for adopting parent)
# Commissioning Parental Leave: 10 consecutive weeks (unpaid, for commissioning parent in surrogacy)

LEAVE_TYPES = [
    ('Annual', 'Annual Leave (21 days/year)'),
    ('Sick', 'Sick Leave (30 days/3 years)'),
    ('Family Responsibility', 'Family Responsibility Leave (3 days/year)'),
    ('Maternity', 'Maternity Leave (4 months)'),
    ('Parental', 'Parental Leave (10 days)'),
    ('Adoption', 'Adoption Leave (10 weeks)'),
    ('Commissioning Parental', 'Commissioning Parental Leave (10 weeks)'),
    ('Unpaid', 'Unpaid Leave'),
    ('Study', 'Study Leave'),
    ('Other', 'Other')
]

# Leave entitlements info for display
LEAVE_ENTITLEMENTS = {
    'Annual': {
        'description': 'Annual leave as per BCEA',
        'entitlement': '21 consecutive days per year (or 15 working days)',
        'notes': 'Must be taken within 6 months of the end of the annual leave cycle'
    },
    'Sick': {
        'description': 'Sick leave as per BCEA',
        'entitlement': '30 days over a 3-year cycle',
        'notes': 'Medical certificate required for absences of more than 2 consecutive days'
    },
    'Family Responsibility': {
        'description': 'For birth, illness or death of immediate family',
        'entitlement': '3 days per year',
        'notes': 'Applies when child is born, when child is sick, or death of spouse/life partner, parent, adoptive parent, grandparent, child, adopted child, grandchild or sibling'
    },
    'Maternity': {
        'description': 'Maternity leave as per BCEA',
        'entitlement': '4 consecutive months',
        'notes': 'May commence 4 weeks before expected date of birth. Employee cannot work for 6 weeks after birth unless certified fit by a medical practitioner'
    },
    'Parental': {
        'description': 'Parental leave for fathers/partners',
        'entitlement': '10 consecutive days',
        'notes': 'Must be taken when the child is born. Unpaid unless UIF claim is made'
    },
    'Adoption': {
        'description': 'Leave for adopting a child',
        'entitlement': '10 consecutive weeks',
        'notes': 'Only one adopting parent qualifies. Unpaid unless UIF claim is made'
    },
    'Commissioning Parental': {
        'description': 'Leave for commissioning parent in surrogacy',
        'entitlement': '10 consecutive weeks',
        'notes': 'For the parent who commissioned the surrogacy. Unpaid unless UIF claim is made'
    },
    'Unpaid': {
        'description': 'Unpaid leave by agreement',
        'entitlement': 'As agreed with employer',
        'notes': 'No statutory entitlement - subject to employer approval'
    },
    'Study': {
        'description': 'Study leave',
        'entitlement': 'As per company policy',
        'notes': 'Not a statutory entitlement - subject to company policy'
    },
    'Other': {
        'description': 'Other leave types',
        'entitlement': 'As agreed',
        'notes': 'Subject to employer approval'
    }
}


class LeaveRequestForm(FlaskForm):
    leave_type = SelectField('Leave Type', choices=LEAVE_TYPES, validators=[DataRequired()])
    start_date = DateField('Start Date', validators=[DataRequired()])
    end_date = DateField('End Date', validators=[DataRequired()])
    reason = TextAreaField('Reason')
    submit = SubmitField('Submit Request')


class ApprovalForm(FlaskForm):
    approval_notes = TextAreaField('Notes')
    submit_approve = SubmitField('Approve')
    submit_reject = SubmitField('Reject')


def calculate_leave_balance(user_id):
    """Calculate leave balance for a user based on approved leave this year."""
    current_year = date.today().year
    year_start = date(current_year, 1, 1)
    year_end = date(current_year, 12, 31)

    # Leave entitlements per year
    entitlements = {
        'Annual': 21,
        'Sick': 10,  # 30 days over 3 years = ~10 per year
        'Family Responsibility': 3,
    }

    balance = {}

    for leave_type, total_days in entitlements.items():
        # Get approved leave for this type this year
        approved_leave = LeaveRequest.query.filter(
            LeaveRequest.staff_id == user_id,
            LeaveRequest.leave_type == leave_type,
            LeaveRequest.status == 'Approved',
            LeaveRequest.start_date >= year_start,
            LeaveRequest.start_date <= year_end
        ).all()

        # Calculate days used (excluding weekends)
        days_used = 0
        for leave in approved_leave:
            current_date = leave.start_date
            while current_date <= leave.end_date:
                # Count only weekdays
                if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                    days_used += 1
                current_date = current_date + timedelta(days=1)

        balance[leave_type] = {
            'total': total_days,
            'used': days_used,
            'remaining': max(0, total_days - days_used)
        }

    return balance


@bp.route('/')
@login_required
def index():
    """View leave requests."""
    if current_user.role in ['Practice Manager', 'Super Admin']:
        # Managers see all requests
        pending = LeaveRequest.query.filter_by(status='Pending').order_by(LeaveRequest.created_at.desc()).all()
        processed = LeaveRequest.query.filter(LeaveRequest.status != 'Pending').order_by(LeaveRequest.approved_at.desc()).limit(20).all()
        # For managers, show their own balance
        leave_balance = calculate_leave_balance(current_user.id)
    else:
        # Staff see only their own
        pending = LeaveRequest.query.filter_by(staff_id=current_user.id, status='Pending').all()
        processed = LeaveRequest.query.filter(
            LeaveRequest.staff_id == current_user.id,
            LeaveRequest.status != 'Pending'
        ).order_by(LeaveRequest.approved_at.desc()).all()
        leave_balance = calculate_leave_balance(current_user.id)

    return render_template('leave/index.html', pending=pending, processed=processed, leave_balance=leave_balance, current_year=date.today().year)


@bp.route('/request', methods=['GET', 'POST'])
@login_required
def request_leave():
    """Submit a leave request."""
    form = LeaveRequestForm()

    if form.validate_on_submit():
        # Validate dates
        if form.end_date.data < form.start_date.data:
            flash('End date cannot be before start date.', 'danger')
            return render_template('leave/request.html', form=form)

        leave = LeaveRequest(
            staff_id=current_user.id,
            leave_type=form.leave_type.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            reason=form.reason.data
        )
        db.session.add(leave)
        db.session.commit()

        log_audit('Submitted Leave Request', 'LeaveRequest', leave.id, {
            'leave_type': leave.leave_type,
            'start_date': leave.start_date.isoformat(),
            'end_date': leave.end_date.isoformat()
        })

        # Send notification to managers (Practice Manager and Super Admin)
        managers = User.query.filter(
            User.role.in_(['Practice Manager', 'Super Admin']),
            User.status == 'Active'
        ).all()
        for manager in managers:
            notification = Notification(
                user_id=manager.id,
                title='New Leave Request',
                message=f'{current_user.full_name} has requested {leave.leave_type} leave from {leave.start_date.strftime("%d %b %Y")} to {leave.end_date.strftime("%d %b %Y")}',
                notification_type='leave_request',
                link=url_for('leave.approve', leave_id=leave.id)
            )
            db.session.add(notification)
        db.session.commit()

        # Send email to managers
        if current_app.config.get('MAIL_ENABLED'):
            for manager in managers:
                if manager.email:
                    html = email_leave_request_submitted(
                        current_user.full_name,
                        leave.leave_type,
                        leave.start_date.strftime('%d %b %Y'),
                        leave.end_date.strftime('%d %b %Y'),
                        leave.reason
                    )
                    send_email(f'Leave Request from {current_user.full_name}', manager.email, html, mail)

        flash('Leave request submitted successfully.', 'success')
        return redirect(url_for('leave.index'))

    return render_template('leave/request.html', form=form)


@bp.route('/<int:leave_id>/approve', methods=['GET', 'POST'])
@login_required
@manager_required
def approve(leave_id):
    """Approve or reject a leave request."""
    leave = LeaveRequest.query.get_or_404(leave_id)

    if leave.status != 'Pending':
        flash('This leave request has already been processed.', 'warning')
        return redirect(url_for('leave.index'))

    form = ApprovalForm()

    if form.validate_on_submit():
        if form.submit_approve.data:
            leave.status = 'Approved'
            action = 'Approved Leave Request'
            msg = 'Leave request approved.'
        else:
            leave.status = 'Rejected'
            action = 'Rejected Leave Request'
            msg = 'Leave request rejected.'

        leave.approved_by = current_user.id
        leave.approval_notes = form.approval_notes.data
        leave.approved_at = datetime.utcnow()
        db.session.commit()

        # If approved, automatically remove conflicting schedules
        removed_schedules = 0
        if leave.status == 'Approved':
            conflicting = Schedule.query.filter(
                Schedule.staff_id == leave.staff_id,
                Schedule.date >= leave.start_date,
                Schedule.date <= leave.end_date
            ).all()
            removed_schedules = len(conflicting)
            for schedule in conflicting:
                db.session.delete(schedule)
            db.session.commit()

        # Create performance event
        event = PerformanceEvent(
            staff_id=leave.staff_id,
            event_type='Leave',
            event_description=f'{leave.leave_type} leave {leave.status.lower()}: {leave.start_date} to {leave.end_date}',
            event_data={
                'leave_id': leave.id,
                'leave_type': leave.leave_type,
                'status': leave.status,
                'start_date': leave.start_date.isoformat(),
                'end_date': leave.end_date.isoformat()
            },
            created_by=current_user.id
        )
        db.session.add(event)
        db.session.commit()

        log_audit(action, 'LeaveRequest', leave.id, {
            'staff_id': leave.staff_id,
            'status': leave.status,
            'notes': leave.approval_notes
        })

        # Send notification to the employee
        status_text = 'approved' if leave.status == 'Approved' else 'rejected'
        notification = Notification(
            user_id=leave.staff_id,
            title=f'Leave Request {leave.status}',
            message=f'Your {leave.leave_type} leave request from {leave.start_date.strftime("%d %b %Y")} to {leave.end_date.strftime("%d %b %Y")} has been {status_text}.',
            notification_type='leave_response',
            link=url_for('leave.index')
        )
        db.session.add(notification)
        db.session.commit()

        # Send email to staff member
        if current_app.config.get('MAIL_ENABLED'):
            staff_member = User.query.get(leave.staff_id)
            if staff_member and staff_member.email:
                if leave.status == 'Approved':
                    html = email_leave_request_approved(
                        staff_member.full_name,
                        leave.leave_type,
                        leave.start_date.strftime('%d %b %Y'),
                        leave.end_date.strftime('%d %b %Y'),
                        leave.approval_notes
                    )
                else:
                    html = email_leave_request_rejected(
                        staff_member.full_name,
                        leave.leave_type,
                        leave.start_date.strftime('%d %b %Y'),
                        leave.end_date.strftime('%d %b %Y'),
                        leave.approval_notes
                    )
                send_email(f'Leave Request {leave.status}', staff_member.email, html, mail)

        # Update message if schedules were removed
        if removed_schedules > 0:
            msg += f' {removed_schedules} schedule entries automatically removed.'

        flash(msg, 'success')
        return redirect(url_for('leave.index'))

    staff = User.query.get(leave.staff_id)
    return render_template('leave/approve.html', form=form, leave=leave, staff=staff)


@bp.route('/calendar')
@login_required
def calendar_view():
    """View leave calendar."""
    # Get approved leave for all staff
    approved_leave = LeaveRequest.query.filter_by(status='Approved').all()

    return render_template('leave/calendar.html', approved_leave=approved_leave)


@bp.route('/entitlements')
@login_required
def entitlements():
    """View leave entitlements based on SA BCEA."""
    return render_template('leave/entitlements.html', entitlements=LEAVE_ENTITLEMENTS)
