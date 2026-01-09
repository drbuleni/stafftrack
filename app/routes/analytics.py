"""Analytics routes for dashboard charts and reporting."""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy import func
from app import db
from app.models import Receipt, Task, User, KPIScore, Warning, LeaveRequest, PerformanceEvent
from app.utils.decorators import manager_required

bp = Blueprint('analytics', __name__, url_prefix='/analytics')


@bp.route('/')
@login_required
@manager_required
def index():
    """Analytics dashboard with charts."""
    return render_template('analytics/index.html')


@bp.route('/api/receipts-by-day')
@login_required
def receipts_by_day():
    """Get receipts totals by day for the last 30 days."""
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    results = db.session.query(
        Receipt.date,
        func.sum(Receipt.amount).label('total')
    ).filter(
        Receipt.date >= start_date,
        Receipt.date <= end_date
    ).group_by(Receipt.date).order_by(Receipt.date).all()

    # Fill in missing days with 0
    data = {}
    current = start_date
    while current <= end_date:
        data[current.isoformat()] = 0
        current += timedelta(days=1)

    for row in results:
        data[row.date.isoformat()] = float(row.total)

    return jsonify({
        'labels': list(data.keys()),
        'values': list(data.values())
    })


@bp.route('/api/receipts-by-method')
@login_required
def receipts_by_method():
    """Get receipts breakdown by payment method for current month."""
    start_of_month = date.today().replace(day=1)

    results = db.session.query(
        Receipt.payment_method,
        func.sum(Receipt.amount).label('total')
    ).filter(
        Receipt.date >= start_of_month
    ).group_by(Receipt.payment_method).all()

    return jsonify({
        'labels': [r.payment_method for r in results],
        'values': [float(r.total) for r in results]
    })


@bp.route('/api/tasks-by-status')
@login_required
def tasks_by_status():
    """Get task counts by status."""
    results = db.session.query(
        Task.status,
        func.count(Task.id).label('count')
    ).group_by(Task.status).all()

    return jsonify({
        'labels': [r.status for r in results],
        'values': [r.count for r in results]
    })


@bp.route('/api/kpi-trends')
@login_required
@manager_required
def kpi_trends():
    """Get KPI score trends over the last 8 weeks."""
    weeks = []
    scores = []

    for i in range(7, -1, -1):
        week_start = date.today() - timedelta(days=date.today().weekday() + (i * 7))
        week_end = week_start + timedelta(days=6)

        total = db.session.query(func.count(KPIScore.id)).filter(
            KPIScore.week_start_date >= week_start,
            KPIScore.week_start_date <= week_end
        ).scalar() or 0

        met = db.session.query(func.count(KPIScore.id)).filter(
            KPIScore.week_start_date >= week_start,
            KPIScore.week_start_date <= week_end,
            KPIScore.score == 1
        ).scalar() or 0

        percentage = (met / total * 100) if total > 0 else 0

        weeks.append(week_start.strftime('%d %b'))
        scores.append(round(percentage, 1))

    return jsonify({
        'labels': weeks,
        'values': scores
    })


@bp.route('/api/staff-performance')
@login_required
@manager_required
def staff_performance():
    """Get performance comparison across staff members."""
    staff = User.query.filter_by(status='Active').all()

    labels = []
    kpi_scores = []
    task_completion = []
    warning_counts = []

    for member in staff:
        labels.append(member.full_name.split()[0])  # First name only

        # KPI average (last 30 days)
        total_kpis = KPIScore.query.filter(
            KPIScore.staff_id == member.id,
            KPIScore.week_start_date >= date.today() - timedelta(days=30)
        ).count()
        met_kpis = KPIScore.query.filter(
            KPIScore.staff_id == member.id,
            KPIScore.week_start_date >= date.today() - timedelta(days=30),
            KPIScore.score == 1
        ).count()
        kpi_pct = (met_kpis / total_kpis * 100) if total_kpis > 0 else 0
        kpi_scores.append(round(kpi_pct, 1))

        # Task completion rate
        total_tasks = Task.query.filter_by(assigned_to=member.id).count()
        done_tasks = Task.query.filter_by(assigned_to=member.id, status='Done').count()
        task_pct = (done_tasks / total_tasks * 100) if total_tasks > 0 else 0
        task_completion.append(round(task_pct, 1))

        # Warning count
        warnings = Warning.query.filter_by(staff_id=member.id).count()
        warning_counts.append(warnings)

    return jsonify({
        'labels': labels,
        'kpi_scores': kpi_scores,
        'task_completion': task_completion,
        'warning_counts': warning_counts
    })


@bp.route('/api/monthly-summary')
@login_required
@manager_required
def monthly_summary():
    """Get summary stats for the current month."""
    start_of_month = date.today().replace(day=1)

    # Revenue
    total_revenue = db.session.query(func.sum(Receipt.amount)).filter(
        Receipt.date >= start_of_month
    ).scalar() or 0

    # Tasks
    tasks_created = Task.query.filter(Task.created_at >= datetime.combine(start_of_month, datetime.min.time())).count()
    tasks_completed = Task.query.filter(
        Task.status == 'Done',
        Task.updated_at >= datetime.combine(start_of_month, datetime.min.time())
    ).count()

    # Leave requests
    leave_requests = LeaveRequest.query.filter(
        LeaveRequest.created_at >= datetime.combine(start_of_month, datetime.min.time())
    ).count()
    leave_approved = LeaveRequest.query.filter(
        LeaveRequest.status == 'Approved',
        LeaveRequest.approved_at >= datetime.combine(start_of_month, datetime.min.time())
    ).count()

    # Warnings
    warnings_issued = Warning.query.filter(
        Warning.issued_at >= datetime.combine(start_of_month, datetime.min.time())
    ).count()

    # KPIs
    total_kpis = KPIScore.query.filter(KPIScore.scored_at >= datetime.combine(start_of_month, datetime.min.time())).count()
    met_kpis = KPIScore.query.filter(
        KPIScore.scored_at >= datetime.combine(start_of_month, datetime.min.time()),
        KPIScore.score == 1
    ).count()
    kpi_rate = (met_kpis / total_kpis * 100) if total_kpis > 0 else 0

    return jsonify({
        'total_revenue': float(total_revenue),
        'tasks_created': tasks_created,
        'tasks_completed': tasks_completed,
        'leave_requests': leave_requests,
        'leave_approved': leave_approved,
        'warnings_issued': warnings_issued,
        'kpi_rate': round(kpi_rate, 1)
    })
