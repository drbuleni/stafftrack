from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import Task, LeaveRequest, KPIScore, Warning, SOPDocument, SOPAcknowledgement
from datetime import date, timedelta

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def index():
    """Main dashboard - shows role-specific content."""
    context = {
        'user': current_user,
        'today': date.today()
    }

    # Get pending tasks for current user
    my_tasks = Task.query.filter(
        Task.assigned_to == current_user.id,
        Task.status != 'Done'
    ).order_by(Task.due_date).limit(5).all()
    context['my_tasks'] = my_tasks

    # Get overdue tasks count
    overdue_count = Task.query.filter(
        Task.assigned_to == current_user.id,
        Task.status != 'Done',
        Task.due_date < date.today()
    ).count()
    context['overdue_count'] = overdue_count

    # Get pending leave requests (for managers)
    if current_user.role in ['Practice Manager', 'Super Admin']:
        pending_leave = LeaveRequest.query.filter_by(status='Pending').count()
        context['pending_leave'] = pending_leave

    # Get unacknowledged SOPs
    all_sops = SOPDocument.query.all()
    acknowledged_sop_ids = [ack.sop_id for ack in
                            SOPAcknowledgement.query.filter_by(staff_id=current_user.id).all()]
    unacknowledged_sops = [sop for sop in all_sops if sop.id not in acknowledged_sop_ids]
    context['unacknowledged_sops'] = len(unacknowledged_sops)

    # Get warning count for current user
    warning_count = Warning.query.filter_by(staff_id=current_user.id).count()
    context['warning_count'] = warning_count

    return render_template('dashboard.html', **context)
