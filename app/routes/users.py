from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, DateField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional, EqualTo
from app import db
from app.models import User, Schedule, Task, LeaveRequest, KPIScore, Warning, PerformanceEvent
from app.utils.decorators import admin_required, manager_required
from app.utils.audit import log_audit

bp = Blueprint('users', __name__, url_prefix='/users')


def get_current_practice_manager():
    """Get the current practice manager (there should be only one)."""
    return User.query.filter_by(role='Practice Manager', status='Active').first()


# Staff roles (Practice Manager is assigned separately)
STAFF_ROLES = [
    ('Receptionist', 'Receptionist'),
    ('Dentist', 'Dentist'),
    ('Dental Assistant', 'Dental Assistant'),
    ('Cleaner', 'Cleaner'),
]


class UserCreateForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=50)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    role = SelectField('Role', choices=STAFF_ROLES, validators=[DataRequired()])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    start_date = DateField('Start Date', validators=[Optional()])
    submit = SubmitField('Create User')


class UserEditForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    role = SelectField('Role', choices=STAFF_ROLES, validators=[DataRequired()])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    status = SelectField('Status', choices=[
        ('Active', 'Active'),
        ('Inactive', 'Inactive')
    ], validators=[DataRequired()])
    submit = SubmitField('Update User')


class PasswordChangeForm(FlaskForm):
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField('Change Password')


@bp.route('/')
@login_required
@manager_required
def index():
    """View all users."""
    users = User.query.order_by(User.full_name).all()
    return render_template('users/index.html', users=users)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    """Create a new user (Super Admin only)."""
    form = UserCreateForm()

    if form.validate_on_submit():
        # Check if username exists
        existing = User.query.filter_by(username=form.username.data).first()
        if existing:
            flash('Username already exists.', 'danger')
            return render_template('users/create.html', form=form)

        user = User(
            username=form.username.data,
            full_name=form.full_name.data,
            role=form.role.data,
            email=form.email.data,
            phone=form.phone.data,
            start_date=form.start_date.data,
            status='Active'
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()

        log_audit('Created User', 'User', user.id, {
            'username': user.username,
            'role': user.role
        })

        flash(f'User {user.username} created successfully.', 'success')
        return redirect(url_for('users.index'))

    return render_template('users/create.html', form=form)


@bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(user_id):
    """Edit a user (Super Admin only)."""
    user = User.query.get_or_404(user_id)
    form = UserEditForm(obj=user)

    if form.validate_on_submit():
        user.full_name = form.full_name.data
        user.role = form.role.data
        user.email = form.email.data
        user.phone = form.phone.data
        user.status = form.status.data

        db.session.commit()

        log_audit('Updated User', 'User', user.id, {
            'username': user.username,
            'role': user.role,
            'status': user.status
        })

        flash(f'User {user.username} updated successfully.', 'success')
        return redirect(url_for('users.index'))

    return render_template('users/edit.html', form=form, user=user)


@bp.route('/<int:user_id>/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_password(user_id):
    """Change a user's password (Super Admin only)."""
    user = User.query.get_or_404(user_id)
    form = PasswordChangeForm()

    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        db.session.commit()

        log_audit('Changed User Password', 'User', user.id, {
            'username': user.username
        })

        flash(f'Password changed for {user.username}.', 'success')
        return redirect(url_for('users.index'))

    return render_template('users/change_password.html', form=form, user=user)


@bp.route('/profile')
@login_required
def profile():
    """View own profile."""
    return render_template('users/profile.html', user=current_user)


@bp.route('/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(user_id):
    """Delete a user (Super Admin only)."""
    user = User.query.get_or_404(user_id)

    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('users.index'))

    # Prevent deleting the only Super Admin
    if user.role == 'Super Admin':
        admin_count = User.query.filter_by(role='Super Admin', status='Active').count()
        if admin_count <= 1:
            flash('Cannot delete the only Super Admin.', 'danger')
            return redirect(url_for('users.index'))

    username = user.username
    user_id_deleted = user.id

    # Delete related records or set to null
    Schedule.query.filter_by(staff_id=user.id).delete()
    Task.query.filter_by(assigned_to=user.id).update({'assigned_to': None})
    LeaveRequest.query.filter_by(staff_id=user.id).delete()
    KPIScore.query.filter_by(staff_id=user.id).delete()
    Warning.query.filter_by(staff_id=user.id).delete()
    PerformanceEvent.query.filter_by(staff_id=user.id).delete()

    db.session.delete(user)
    db.session.commit()

    log_audit('Deleted User', 'User', user_id_deleted, {
        'username': username
    })

    flash(f'User {username} has been deleted.', 'success')
    return redirect(url_for('users.index'))


@bp.route('/practice-manager')
@login_required
@admin_required
def practice_manager():
    """View and manage Practice Manager assignment."""
    current_pm = get_current_practice_manager()
    # Get all active staff who could be Practice Manager (exclude Super Admin)
    eligible_staff = User.query.filter(
        User.status == 'Active',
        User.role != 'Super Admin'
    ).order_by(User.full_name).all()

    return render_template('users/practice_manager.html',
                          current_pm=current_pm,
                          eligible_staff=eligible_staff)


@bp.route('/practice-manager/assign/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def assign_practice_manager(user_id):
    """Assign a user as the Practice Manager."""
    new_pm = User.query.get_or_404(user_id)

    if new_pm.role == 'Super Admin':
        flash('Super Admin cannot be assigned as Practice Manager.', 'danger')
        return redirect(url_for('users.practice_manager'))

    # Remove Practice Manager role from current PM (if any)
    current_pm = get_current_practice_manager()
    old_pm_name = None
    if current_pm and current_pm.id != new_pm.id:
        old_pm_name = current_pm.full_name
        # Revert to their base role (we'll store it or default to their previous role)
        # For simplicity, we'll set them to Dentist if they were PM
        # In a real system, you'd store their original role
        current_pm.role = 'Dentist'  # Default fallback

    # Set new Practice Manager
    new_pm.role = 'Practice Manager'
    db.session.commit()

    log_audit('Assigned Practice Manager', 'User', new_pm.id, {
        'new_pm': new_pm.full_name,
        'old_pm': old_pm_name
    })

    msg = f'{new_pm.full_name} is now the Practice Manager.'
    if old_pm_name:
        msg += f' {old_pm_name} has been removed from the role.'
    flash(msg, 'success')

    return redirect(url_for('users.practice_manager'))


@bp.route('/practice-manager/remove', methods=['POST'])
@login_required
@admin_required
def remove_practice_manager():
    """Remove the current Practice Manager (revert to regular staff)."""
    current_pm = get_current_practice_manager()

    if not current_pm:
        flash('No Practice Manager is currently assigned.', 'warning')
        return redirect(url_for('users.practice_manager'))

    old_name = current_pm.full_name
    current_pm.role = 'Dentist'  # Default fallback
    db.session.commit()

    log_audit('Removed Practice Manager', 'User', current_pm.id, {
        'removed_pm': old_name
    })

    flash(f'{old_name} is no longer the Practice Manager.', 'success')
    return redirect(url_for('users.practice_manager'))
