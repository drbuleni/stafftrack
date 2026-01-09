from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, SubmitField
from wtforms.validators import DataRequired, Length
from app import db, mail
from app.models import Task, User
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from app.utils.email import send_email, email_task_assigned
from datetime import date

bp = Blueprint('tasks', __name__, url_prefix='/tasks')


class TaskForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description')
    assigned_to = SelectField('Assign To', coerce=int)
    due_date = DateField('Due Date')
    submit = SubmitField('Create Task')


class TaskStatusForm(FlaskForm):
    status = SelectField('Status',
                        choices=[('To Do', 'To Do'), ('In Progress', 'In Progress'), ('Done', 'Done')])
    submit = SubmitField('Update Status')


@bp.route('/')
@login_required
def index():
    """List all tasks (managers) or own tasks (staff)."""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    assignee_filter = request.args.get('assignee', '', type=int)

    query = Task.query

    # Staff can only see their own tasks
    if current_user.role not in ['Practice Manager', 'Super Admin']:
        query = query.filter_by(assigned_to=current_user.id)
    elif assignee_filter:
        query = query.filter_by(assigned_to=assignee_filter)

    if status_filter:
        query = query.filter_by(status=status_filter)

    tasks = query.order_by(Task.due_date).paginate(page=page, per_page=20, error_out=False)

    staff_list = User.query.filter(User.status == 'Active').all()

    return render_template('tasks/index.html',
                          tasks=tasks,
                          staff_list=staff_list,
                          status_filter=status_filter,
                          assignee_filter=assignee_filter)


@bp.route('/my-tasks')
@login_required
def my_tasks():
    """View current user's tasks."""
    tasks = Task.query.filter_by(assigned_to=current_user.id).order_by(Task.due_date).all()
    today = date.today()
    return render_template('tasks/my_tasks.html', tasks=tasks, today=today)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@manager_required
def create():
    """Create a new task."""
    form = TaskForm()
    form.assigned_to.choices = [(0, '-- Unassigned --')] + [
        (u.id, u.full_name) for u in User.query.filter_by(status='Active').all()
    ]

    if form.validate_on_submit():
        task = Task(
            title=form.title.data,
            description=form.description.data,
            assigned_to=form.assigned_to.data if form.assigned_to.data != 0 else None,
            due_date=form.due_date.data,
            created_by=current_user.id
        )
        db.session.add(task)
        db.session.commit()

        log_audit('Created Task', 'Task', task.id, {
            'title': task.title,
            'assigned_to': task.assigned_to
        })

        # Send email to assigned staff
        if current_app.config.get('MAIL_ENABLED') and task.assigned_to:
            assignee = User.query.get(task.assigned_to)
            if assignee and assignee.email:
                html = email_task_assigned(
                    assignee.full_name,
                    task.title,
                    task.description,
                    task.due_date.strftime('%d %b %Y') if task.due_date else None
                )
                send_email('New Task Assigned', assignee.email, html, mail)

        flash('Task created successfully.', 'success')
        return redirect(url_for('tasks.index'))

    return render_template('tasks/create.html', form=form)


@bp.route('/<int:task_id>/update-status', methods=['POST'])
@login_required
def update_status(task_id):
    """Update task status."""
    task = Task.query.get_or_404(task_id)

    # Check permission
    if task.assigned_to != current_user.id and current_user.role not in ['Practice Manager', 'Super Admin']:
        flash('You do not have permission to update this task.', 'danger')
        return redirect(url_for('tasks.index'))

    new_status = request.form.get('status')
    if new_status in ['To Do', 'In Progress', 'Done']:
        old_status = task.status
        task.status = new_status
        db.session.commit()

        log_audit('Updated Task Status', 'Task', task.id, {
            'title': task.title,
            'old_status': old_status,
            'new_status': new_status
        })

        flash(f'Task status updated to {new_status}.', 'success')

    return redirect(request.referrer or url_for('tasks.index'))


@bp.route('/<int:task_id>/delete', methods=['POST'])
@login_required
def delete(task_id):
    """Delete a task. Only Super Admin and Practice Manager can delete."""
    # Check permission - only Super Admin and Practice Manager can delete
    if current_user.role not in ['Practice Manager', 'Super Admin']:
        flash('You do not have permission to delete tasks.', 'danger')
        return redirect(url_for('tasks.index'))

    task = Task.query.get_or_404(task_id)

    log_audit('Deleted Task', 'Task', task.id, {
        'title': task.title,
        'assigned_to': task.assigned_to,
        'status': task.status
    })

    db.session.delete(task)
    db.session.commit()

    flash('Task deleted successfully.', 'success')
    return redirect(url_for('tasks.index'))
