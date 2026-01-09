from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateTimeLocalField, SubmitField
from wtforms.validators import DataRequired, Length, Optional
from app import db
from app.models import Announcement, Notification, User
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from datetime import datetime

bp = Blueprint('announcements', __name__, url_prefix='/announcements')

PRIORITY_CHOICES = [
    ('Normal', 'Normal'),
    ('Important', 'Important'),
    ('Urgent', 'Urgent')
]


class AnnouncementForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    content = TextAreaField('Content', validators=[DataRequired()])
    priority = SelectField('Priority', choices=PRIORITY_CHOICES, validators=[DataRequired()])
    expires_at = DateTimeLocalField('Expires At (Optional)', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    submit = SubmitField('Post Announcement')


@bp.route('/')
@login_required
def index():
    """View all announcements."""
    # Mark all announcement notifications as read for this user
    Notification.query.filter_by(
        user_id=current_user.id,
        notification_type='announcement',
        is_read=False
    ).update({'is_read': True})
    db.session.commit()

    # Get active announcements that haven't expired
    announcements = Announcement.query.filter(
        Announcement.is_active == True,
        db.or_(
            Announcement.expires_at == None,
            Announcement.expires_at > datetime.utcnow()
        )
    ).order_by(
        db.case(
            (Announcement.priority == 'Urgent', 1),
            (Announcement.priority == 'Important', 2),
            else_=3
        ),
        Announcement.created_at.desc()
    ).all()

    return render_template('announcements/index.html', announcements=announcements)


@bp.route('/manage')
@login_required
@manager_required
def manage():
    """Manage all announcements (for admins/managers)."""
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('announcements/manage.html', announcements=announcements, now=datetime.utcnow())


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@manager_required
def create():
    """Create a new announcement."""
    form = AnnouncementForm()

    if form.validate_on_submit():
        announcement = Announcement(
            title=form.title.data,
            content=form.content.data,
            priority=form.priority.data,
            expires_at=form.expires_at.data,
            created_by=current_user.id
        )

        db.session.add(announcement)
        db.session.commit()

        # Create notifications for all active users
        active_users = User.query.filter_by(status='Active').all()
        for user in active_users:
            notification = Notification(
                user_id=user.id,
                title=f'New Announcement: {announcement.title}',
                message=announcement.content[:200] + ('...' if len(announcement.content) > 200 else ''),
                notification_type='announcement',
                link=url_for('announcements.index')
            )
            db.session.add(notification)

        db.session.commit()

        log_audit('Created Announcement', 'Announcement', announcement.id, {
            'title': announcement.title,
            'priority': announcement.priority
        })

        flash('Announcement posted successfully. All staff have been notified.', 'success')
        return redirect(url_for('announcements.manage'))

    return render_template('announcements/create.html', form=form)


@bp.route('/<int:announcement_id>/edit', methods=['GET', 'POST'])
@login_required
@manager_required
def edit(announcement_id):
    """Edit an announcement."""
    announcement = Announcement.query.get_or_404(announcement_id)
    form = AnnouncementForm(obj=announcement)

    if form.validate_on_submit():
        announcement.title = form.title.data
        announcement.content = form.content.data
        announcement.priority = form.priority.data
        announcement.expires_at = form.expires_at.data

        db.session.commit()

        log_audit('Updated Announcement', 'Announcement', announcement.id, {
            'title': announcement.title,
            'priority': announcement.priority
        })

        flash('Announcement updated successfully.', 'success')
        return redirect(url_for('announcements.manage'))

    return render_template('announcements/edit.html', form=form, announcement=announcement)


@bp.route('/<int:announcement_id>/delete', methods=['POST'])
@login_required
@manager_required
def delete(announcement_id):
    """Delete an announcement."""
    announcement = Announcement.query.get_or_404(announcement_id)
    title = announcement.title

    db.session.delete(announcement)
    db.session.commit()

    log_audit('Deleted Announcement', 'Announcement', announcement_id, {
        'title': title
    })

    flash(f'Announcement "{title}" has been deleted.', 'success')
    return redirect(url_for('announcements.manage'))


@bp.route('/<int:announcement_id>/toggle', methods=['POST'])
@login_required
@manager_required
def toggle(announcement_id):
    """Toggle announcement active status."""
    announcement = Announcement.query.get_or_404(announcement_id)
    announcement.is_active = not announcement.is_active

    db.session.commit()

    status = 'activated' if announcement.is_active else 'deactivated'
    log_audit(f'{status.capitalize()} Announcement', 'Announcement', announcement.id, {
        'title': announcement.title,
        'is_active': announcement.is_active
    })

    flash(f'Announcement "{announcement.title}" has been {status}.', 'success')
    return redirect(url_for('announcements.manage'))


@bp.route('/unread-count')
@login_required
def unread_count():
    """Get count of unread announcement notifications (for badge display)."""
    # Count unread announcement notifications for this user
    count = Notification.query.filter_by(
        user_id=current_user.id,
        notification_type='announcement',
        is_read=False
    ).count()

    return jsonify({'count': count})
