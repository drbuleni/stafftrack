from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models import AuditLog, User
from app.utils.decorators import admin_required
from datetime import date, timedelta

bp = Blueprint('audit', __name__, url_prefix='/audit')


@bp.route('/')
@login_required
@admin_required
def index():
    """View audit log (Super Admin only)."""
    page = request.args.get('page', 1, type=int)

    # Filters
    user_filter = request.args.get('user_id', type=int)
    action_filter = request.args.get('action', '')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    query = AuditLog.query

    if user_filter:
        query = query.filter_by(user_id=user_filter)

    if action_filter:
        query = query.filter(AuditLog.action.like(f'%{action_filter}%'))

    if start_date_str:
        start_date = date.fromisoformat(start_date_str)
        query = query.filter(AuditLog.created_at >= start_date)

    if end_date_str:
        end_date = date.fromisoformat(end_date_str)
        query = query.filter(AuditLog.created_at <= end_date + timedelta(days=1))

    logs = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    # Get users for filter dropdown
    users = User.query.all()

    # Get unique actions for filter dropdown
    actions = AuditLog.query.with_entities(AuditLog.action).distinct().all()
    unique_actions = [a[0] for a in actions]

    return render_template('audit/index.html',
                          logs=logs,
                          users=users,
                          unique_actions=unique_actions,
                          user_filter=user_filter,
                          action_filter=action_filter,
                          start_date=start_date_str,
                          end_date=end_date_str)
