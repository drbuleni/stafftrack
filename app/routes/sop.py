from flask import Blueprint, render_template, redirect, url_for, flash, request, send_from_directory, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length
from werkzeug.utils import secure_filename
from app import db
from app.models import SOPDocument, SOPAcknowledgement, User
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
import os
import uuid

bp = Blueprint('sop', __name__, url_prefix='/sop')


class SOPUploadForm(FlaskForm):
    title = StringField('Document Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description')
    version = StringField('Version', default='1.0')
    document = FileField('Document', validators=[
        FileRequired(),
        FileAllowed(['pdf', 'doc', 'docx'], 'Only PDF and Word documents allowed.')
    ])
    submit = SubmitField('Upload Document')


@bp.route('/')
@login_required
def index():
    """View all SOP documents."""
    documents = SOPDocument.query.order_by(SOPDocument.uploaded_at.desc()).all()

    # Get acknowledgement status for current user
    acknowledged_ids = [ack.sop_id for ack in
                        SOPAcknowledgement.query.filter_by(staff_id=current_user.id).all()]

    return render_template('sop/index.html',
                          documents=documents,
                          acknowledged_ids=acknowledged_ids)


@bp.route('/upload', methods=['GET', 'POST'])
@login_required
@manager_required
def upload():
    """Upload a new SOP document."""
    form = SOPUploadForm()

    if form.validate_on_submit():
        file = form.document.data
        # Generate secure filename with UUID
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{ext}"

        # Save file
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)

        # Create database record
        sop = SOPDocument(
            title=form.title.data,
            file_path=unique_filename,
            version=form.version.data,
            description=form.description.data,
            uploaded_by=current_user.id
        )
        db.session.add(sop)
        db.session.commit()

        log_audit('Uploaded SOP Document', 'SOPDocument', sop.id, {
            'title': sop.title,
            'version': sop.version
        })

        flash('SOP document uploaded successfully.', 'success')
        return redirect(url_for('sop.index'))

    return render_template('sop/upload.html', form=form)


@bp.route('/download/<int:sop_id>')
@login_required
def download(sop_id):
    """Download an SOP document."""
    sop = SOPDocument.query.get_or_404(sop_id)

    log_audit('Downloaded SOP Document', 'SOPDocument', sop.id, {
        'title': sop.title
    })

    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        sop.file_path,
        as_attachment=True,
        download_name=f"{sop.title}.{sop.file_path.rsplit('.', 1)[1]}"
    )


@bp.route('/acknowledge/<int:sop_id>', methods=['POST'])
@login_required
def acknowledge(sop_id):
    """Acknowledge an SOP document."""
    sop = SOPDocument.query.get_or_404(sop_id)

    # Check if already acknowledged
    existing = SOPAcknowledgement.query.filter_by(
        sop_id=sop_id,
        staff_id=current_user.id
    ).first()

    if existing:
        flash('You have already acknowledged this document.', 'warning')
        return redirect(url_for('sop.index'))

    # Create acknowledgement
    ack = SOPAcknowledgement(
        sop_id=sop_id,
        staff_id=current_user.id
    )
    db.session.add(ack)
    db.session.commit()

    log_audit('Acknowledged SOP Document', 'SOPAcknowledgement', ack.id, {
        'sop_id': sop_id,
        'sop_title': sop.title,
        'version': sop.version
    })

    flash(f'You have acknowledged "{sop.title}" (Version {sop.version}).', 'success')
    return redirect(url_for('sop.index'))


@bp.route('/acknowledgements/<int:sop_id>')
@login_required
@manager_required
def view_acknowledgements(sop_id):
    """View who has acknowledged a specific SOP."""
    sop = SOPDocument.query.get_or_404(sop_id)
    acknowledgements = SOPAcknowledgement.query.filter_by(sop_id=sop_id).all()

    # Get all active staff
    all_staff = User.query.filter_by(status='Active').all()
    acknowledged_staff_ids = [ack.staff_id for ack in acknowledgements]

    acknowledged = [s for s in all_staff if s.id in acknowledged_staff_ids]
    not_acknowledged = [s for s in all_staff if s.id not in acknowledged_staff_ids]

    return render_template('sop/acknowledgements.html',
                          sop=sop,
                          acknowledgements=acknowledgements,
                          acknowledged=acknowledged,
                          not_acknowledged=not_acknowledged)
