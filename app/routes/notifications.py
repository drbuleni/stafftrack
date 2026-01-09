"""Notifications routes for system alerts and notifications."""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Notification, Task, User
from datetime import datetime, date, timedelta

bp = Blueprint('notifications', __name__, url_prefix='/notifications')


def create_notification(user_id, title, message, notification_type, link=None):
    """Create a notification for a user."""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def check_overdue_tasks():
    """Check for overdue tasks and create notifications."""
    today = date.today()

    # Find overdue tasks
    overdue_tasks = Task.query.filter(
        Task.due_date < today,
        Task.status != 'Done'
    ).all()

    for task in overdue_tasks:
        if task.assigned_to:
            # Check if notification already exists for this task today
            existing = Notification.query.filter(
                Notification.user_id == task.assigned_to,
                Notification.notification_type == 'task_overdue',
                Notification.message.contains(str(task.id)),
                Notification.created_at >= datetime.combine(today, datetime.min.time())
            ).first()

            if not existing:
                days_overdue = (today - task.due_date).days
                create_notification(
                    user_id=task.assigned_to,
                    title='Overdue Task',
                    message=f'Task "{task.title}" is {days_overdue} day(s) overdue. [Task ID: {task.id}]',
                    notification_type='task_overdue',
                    link=url_for('tasks.index')
                )

    # Notify managers about all overdue tasks
    managers = User.query.filter(
        User.role.in_(['Practice Manager', 'Super Admin']),
        User.status == 'Active'
    ).all()

    if overdue_tasks:
        for manager in managers:
            # Check if notification already exists for managers today
            existing = Notification.query.filter(
                Notification.user_id == manager.id,
                Notification.notification_type == 'task_overdue',
                Notification.title == 'Overdue Tasks Summary',
                Notification.created_at >= datetime.combine(today, datetime.min.time())
            ).first()

            if not existing:
                create_notification(
                    user_id=manager.id,
                    title='Overdue Tasks Summary',
                    message=f'There are {len(overdue_tasks)} overdue task(s) that need attention.',
                    notification_type='task_overdue',
                    link=url_for('tasks.index')
                )


def check_upcoming_tasks():
    """Check for tasks due tomorrow and create reminders."""
    tomorrow = date.today() + timedelta(days=1)

    tasks_due_tomorrow = Task.query.filter(
        Task.due_date == tomorrow,
        Task.status != 'Done'
    ).all()

    for task in tasks_due_tomorrow:
        if task.assigned_to:
            # Check if reminder already sent
            existing = Notification.query.filter(
                Notification.user_id == task.assigned_to,
                Notification.notification_type == 'task_reminder',
                Notification.message.contains(str(task.id)),
                Notification.created_at >= datetime.combine(date.today(), datetime.min.time())
            ).first()

            if not existing:
                create_notification(
                    user_id=task.assigned_to,
                    title='Task Due Tomorrow',
                    message=f'Task "{task.title}" is due tomorrow. [Task ID: {task.id}]',
                    notification_type='task_reminder',
                    link=url_for('tasks.index')
                )


@bp.route('/')
@login_required
def index():
    """View all notifications."""
    # Run notification checks
    check_overdue_tasks()
    check_upcoming_tasks()

    page = request.args.get('page', 1, type=int)
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    return render_template('notifications/index.html', notifications=notifications)


@bp.route('/unread-count')
@login_required
def unread_count():
    """Get unread notification count (for AJAX)."""
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    return jsonify({'count': count})


@bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    """Mark a notification as read."""
    notification = Notification.query.get_or_404(notification_id)

    if notification.user_id != current_user.id:
        flash('You cannot modify this notification.', 'danger')
        return redirect(url_for('notifications.index'))

    notification.is_read = True
    db.session.commit()

    # Redirect to link if available
    if notification.link:
        return redirect(notification.link)

    return redirect(url_for('notifications.index'))


@bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    """Mark all notifications as read."""
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()

    flash('All notifications marked as read.', 'success')
    return redirect(url_for('notifications.index'))


@bp.route('/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete(notification_id):
    """Delete a notification."""
    notification = Notification.query.get_or_404(notification_id)

    if notification.user_id != current_user.id:
        flash('You cannot delete this notification.', 'danger')
        return redirect(url_for('notifications.index'))

    db.session.delete(notification)
    db.session.commit()

    flash('Notification deleted.', 'success')
    return redirect(url_for('notifications.index'))


@bp.route('/clear-all', methods=['POST'])
@login_required
def clear_all():
    """Clear all read notifications."""
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=True
    ).delete()
    db.session.commit()

    flash('All read notifications cleared.', 'success')
    return redirect(url_for('notifications.index'))
