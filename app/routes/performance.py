from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models import User, PerformanceEvent, KPIScore, Task, Warning, LeaveRequest
from app.utils.decorators import manager_required
from datetime import date, timedelta

bp = Blueprint('performance', __name__, url_prefix='/performance')


@bp.route('/')
@login_required
def index():
    """View performance overview (managers) or own performance (staff)."""
    if current_user.role in ['Practice Manager', 'Super Admin']:
        staff = User.query.filter_by(status='Active').all()
        return render_template('performance/index.html', staff=staff)
    else:
        return timeline(current_user.id)


@bp.route('/timeline/<int:staff_id>')
@login_required
def timeline(staff_id):
    """View performance timeline for a staff member."""
    # Check permission
    if staff_id != current_user.id and current_user.role not in ['Practice Manager', 'Super Admin']:
        return render_template('errors/403.html'), 403

    staff = User.query.get_or_404(staff_id)

    # Get date range filter
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str:
        start_date = date.fromisoformat(start_date_str)
    else:
        start_date = date.today() - timedelta(days=90)  # Last 90 days by default

    if end_date_str:
        end_date = date.fromisoformat(end_date_str)
    else:
        end_date = date.today()

    # Get performance events
    events = PerformanceEvent.query.filter(
        PerformanceEvent.staff_id == staff_id,
        PerformanceEvent.created_at >= start_date,
        PerformanceEvent.created_at <= end_date + timedelta(days=1)
    ).order_by(PerformanceEvent.created_at.desc()).all()

    # Get warnings
    warnings = Warning.query.filter(
        Warning.staff_id == staff_id,
        Warning.issued_at >= start_date,
        Warning.issued_at <= end_date + timedelta(days=1)
    ).order_by(Warning.issued_at.desc()).all()

    # Get completed tasks
    completed_tasks = Task.query.filter(
        Task.assigned_to == staff_id,
        Task.status == 'Done',
        Task.updated_at >= start_date,
        Task.updated_at <= end_date + timedelta(days=1)
    ).order_by(Task.updated_at.desc()).all()

    # Calculate summary stats
    total_warnings = Warning.query.filter_by(staff_id=staff_id).count()
    total_tasks_completed = Task.query.filter_by(assigned_to=staff_id, status='Done').count()

    # Recent KPI average
    recent_kpis = KPIScore.query.filter(
        KPIScore.staff_id == staff_id,
        KPIScore.scored_at >= date.today() - timedelta(days=30)
    ).all()

    if recent_kpis:
        kpi_avg = (sum(k.score for k in recent_kpis) / len(recent_kpis)) * 100
    else:
        kpi_avg = None

    return render_template('performance/timeline.html',
                          staff=staff,
                          events=events,
                          warnings=warnings,
                          completed_tasks=completed_tasks,
                          total_warnings=total_warnings,
                          total_tasks_completed=total_tasks_completed,
                          kpi_avg=kpi_avg,
                          start_date=start_date,
                          end_date=end_date)


@bp.route('/summary')
@login_required
@manager_required
def summary():
    """View team performance summary."""
    staff = User.query.filter_by(status='Active').all()

    summary_data = []
    for member in staff:
        # Get warning count
        warnings = Warning.query.filter_by(staff_id=member.id).count()

        # Get completed tasks this month
        month_start = date.today().replace(day=1)
        tasks_completed = Task.query.filter(
            Task.assigned_to == member.id,
            Task.status == 'Done',
            Task.updated_at >= month_start
        ).count()

        # Get recent KPI average
        recent_kpis = KPIScore.query.filter(
            KPIScore.staff_id == member.id,
            KPIScore.scored_at >= date.today() - timedelta(days=30)
        ).all()

        if recent_kpis:
            kpi_avg = (sum(k.score for k in recent_kpis) / len(recent_kpis)) * 100
        else:
            kpi_avg = None

        summary_data.append({
            'staff': member,
            'warnings': warnings,
            'tasks_completed': tasks_completed,
            'kpi_avg': kpi_avg
        })

    return render_template('performance/summary.html', summary_data=summary_data)
