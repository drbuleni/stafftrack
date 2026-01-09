from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired
from app import db, mail
from app.models import Warning, User, PerformanceEvent
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from app.utils.email import send_email, email_warning_issued

bp = Blueprint('warnings', __name__, url_prefix='/warnings')


class WarningForm(FlaskForm):
    staff_id = SelectField('Staff Member', coerce=int, validators=[DataRequired()])
    warning_type = SelectField('Warning Type', choices=[
        ('Manual', 'Manual Warning'),
        ('Late', 'Late Arrival'),
        ('Task_Missed', 'Missed Task'),
        ('KPI_Failed', 'Failed KPI'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    reason = TextAreaField('Reason', validators=[DataRequired()])
    submit = SubmitField('Issue Warning')


@bp.route('/')
@login_required
def index():
    """View warnings."""
    if current_user.role in ['Practice Manager', 'Super Admin']:
        # Managers see all warnings
        warnings = Warning.query.order_by(Warning.issued_at.desc()).limit(50).all()
    else:
        # Staff see only their own
        warnings = Warning.query.filter_by(staff_id=current_user.id).order_by(Warning.issued_at.desc()).all()

    return render_template('warnings/index.html', warnings=warnings)


@bp.route('/issue', methods=['GET', 'POST'])
@login_required
@manager_required
def issue():
    """Issue a warning to a staff member."""
    form = WarningForm()
    form.staff_id.choices = [
        (u.id, u.full_name) for u in User.query.filter_by(status='Active').all()
    ]

    if form.validate_on_submit():
        warning = Warning(
            staff_id=form.staff_id.data,
            warning_type=form.warning_type.data,
            reason=form.reason.data,
            auto_generated=False,
            issued_by=current_user.id
        )
        db.session.add(warning)
        db.session.commit()

        # Create performance event
        staff = User.query.get(form.staff_id.data)
        event = PerformanceEvent(
            staff_id=form.staff_id.data,
            event_type='Warning',
            event_description=f'Warning issued: {form.warning_type.data} - {form.reason.data[:100]}',
            event_data={
                'warning_id': warning.id,
                'warning_type': warning.warning_type,
                'reason': warning.reason
            },
            created_by=current_user.id
        )
        db.session.add(event)
        db.session.commit()

        log_audit('Issued Warning', 'Warning', warning.id, {
            'staff_id': warning.staff_id,
            'warning_type': warning.warning_type,
            'reason': warning.reason
        })

        # Send email to staff member
        if current_app.config.get('MAIL_ENABLED') and staff.email:
            html = email_warning_issued(
                staff.full_name,
                warning.warning_type,
                warning.reason,
                current_user.full_name
            )
            send_email('Warning Issued', staff.email, html, mail)

        flash(f'Warning issued to {staff.full_name}.', 'warning')
        return redirect(url_for('warnings.index'))

    return render_template('warnings/issue.html', form=form)


@bp.route('/staff/<int:staff_id>')
@login_required
def staff_warnings(staff_id):
    """View warnings for a specific staff member."""
    # Check permission
    if staff_id != current_user.id and current_user.role not in ['Practice Manager', 'Super Admin']:
        flash('You do not have permission to view this.', 'danger')
        return redirect(url_for('warnings.index'))

    staff = User.query.get_or_404(staff_id)
    warnings = Warning.query.filter_by(staff_id=staff_id).order_by(Warning.issued_at.desc()).all()

    return render_template('warnings/staff_warnings.html', staff=staff, warnings=warnings)
