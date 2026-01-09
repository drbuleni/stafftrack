from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SelectField, TextAreaField, DateField, SubmitField, EmailField
from wtforms.validators import DataRequired, NumberRange, Optional, Email
from app import db, mail
from app.models import Receipt
from app.utils.decorators import receipt_access_required
from app.utils.audit import log_audit
from app.utils.helpers import generate_receipt_number
from app.utils.email import send_email
from datetime import date

bp = Blueprint('receipts', __name__, url_prefix='/receipts')


class ReceiptForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()])
    amount = DecimalField('Amount (R)', validators=[DataRequired(), NumberRange(min=0.01)])
    payment_method = SelectField('Payment Method',
                                 choices=[('Cash', 'Cash'), ('Card', 'Card'), ('EFT', 'EFT')],
                                 validators=[DataRequired()])
    description = TextAreaField('Description/Service')
    patient_name = StringField('Patient Name', validators=[Optional()])
    patient_email = EmailField('Patient Email', validators=[Optional(), Email()])
    submit = SubmitField('Create Receipt')


def generate_receipt_email(receipt):
    """Generate HTML email for patient receipt."""
    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #16a34a 0%, #22c55e 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ background: #ffffff; padding: 30px; border: 1px solid #e5e7eb; }}
        .receipt-box {{ background: #f9fafb; border: 2px dashed #d1d5db; padding: 20px; margin: 20px 0; border-radius: 8px; }}
        .receipt-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #e5e7eb; }}
        .receipt-row:last-child {{ border-bottom: none; }}
        .receipt-label {{ color: #6b7280; }}
        .receipt-value {{ font-weight: 600; }}
        .total-row {{ font-size: 1.25rem; color: #16a34a; }}
        .footer {{ background: #f9fafb; padding: 15px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 8px 8px; border: 1px solid #e5e7eb; border-top: none; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Dr. Buleni's Dental Practice</h1>
            <p style="margin: 5px 0 0 0;">Payment Receipt</p>
        </div>
        <div class="content">
            <p>Dear {receipt.patient_name or 'Valued Patient'},</p>
            <p>Thank you for your payment. Please find your receipt details below:</p>

            <div class="receipt-box">
                <div class="receipt-row">
                    <span class="receipt-label">Receipt Number:</span>
                    <span class="receipt-value">{receipt.receipt_number}</span>
                </div>
                <div class="receipt-row">
                    <span class="receipt-label">Date:</span>
                    <span class="receipt-value">{receipt.date.strftime('%d %B %Y')}</span>
                </div>
                <div class="receipt-row">
                    <span class="receipt-label">Service:</span>
                    <span class="receipt-value">{receipt.description or 'Dental Services'}</span>
                </div>
                <div class="receipt-row">
                    <span class="receipt-label">Payment Method:</span>
                    <span class="receipt-value">{receipt.payment_method}</span>
                </div>
                <div class="receipt-row total-row">
                    <span class="receipt-label">Amount Paid:</span>
                    <span class="receipt-value">R {float(receipt.amount):,.2f}</span>
                </div>
            </div>

            <p>If you have any questions about this receipt, please contact us.</p>
            <p>Thank you for choosing Dr. Buleni's Dental Practice!</p>
        </div>
        <div class="footer">
            <p>This is an automated receipt from StaffTrack.</p>
            <p>Dr. Buleni's Dental Practice</p>
        </div>
    </div>
</body>
</html>
"""


@bp.route('/')
@login_required
@receipt_access_required
def index():
    """List all receipts."""
    page = request.args.get('page', 1, type=int)
    receipts = Receipt.query.order_by(Receipt.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('receipts/index.html', receipts=receipts)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
@receipt_access_required
def create():
    """Create a new receipt."""
    form = ReceiptForm()
    if form.validate_on_submit():
        receipt = Receipt(
            receipt_number=generate_receipt_number(),
            date=form.date.data,
            amount=form.amount.data,
            payment_method=form.payment_method.data,
            description=form.description.data,
            patient_name=form.patient_name.data,
            patient_email=form.patient_email.data,
            created_by=current_user.id
        )
        db.session.add(receipt)
        db.session.commit()

        log_audit('Created Receipt', 'Receipt', receipt.id, {
            'receipt_number': receipt.receipt_number,
            'amount': float(receipt.amount),
            'payment_method': receipt.payment_method,
            'patient_name': receipt.patient_name
        })

        # Send receipt email to patient if email provided
        email_sent = False
        if receipt.patient_email and current_app.config.get('MAIL_ENABLED'):
            try:
                html = generate_receipt_email(receipt)
                send_email(
                    f'Payment Receipt - {receipt.receipt_number}',
                    receipt.patient_email,
                    html,
                    mail
                )
                receipt.email_sent = True
                db.session.commit()
                email_sent = True
            except Exception as e:
                current_app.logger.error(f"Failed to send receipt email: {e}")

        if email_sent:
            flash(f'Receipt {receipt.receipt_number} created and emailed to {receipt.patient_email}.', 'success')
        else:
            flash(f'Receipt {receipt.receipt_number} created successfully.', 'success')

        return redirect(url_for('receipts.index'))

    form.date.data = date.today()
    return render_template('receipts/create.html', form=form)


@bp.route('/<int:receipt_id>/resend-email', methods=['POST'])
@login_required
@receipt_access_required
def resend_email(receipt_id):
    """Resend receipt email to patient."""
    receipt = Receipt.query.get_or_404(receipt_id)

    if not receipt.patient_email:
        flash('No email address on this receipt.', 'warning')
        return redirect(url_for('receipts.index'))

    if not current_app.config.get('MAIL_ENABLED'):
        flash('Email sending is not enabled.', 'warning')
        return redirect(url_for('receipts.index'))

    try:
        html = generate_receipt_email(receipt)
        send_email(
            f'Payment Receipt - {receipt.receipt_number}',
            receipt.patient_email,
            html,
            mail
        )
        receipt.email_sent = True
        db.session.commit()
        flash(f'Receipt emailed to {receipt.patient_email}.', 'success')
    except Exception as e:
        current_app.logger.error(f"Failed to send receipt email: {e}")
        flash('Failed to send email. Please try again.', 'danger')

    return redirect(url_for('receipts.index'))


@bp.route('/daily-summary')
@login_required
@receipt_access_required
def daily_summary():
    """Show daily cash summary."""
    selected_date = request.args.get('date', date.today().isoformat())

    receipts = Receipt.query.filter_by(date=selected_date).all()

    cash_total = sum(r.amount for r in receipts if r.payment_method == 'Cash')
    card_total = sum(r.amount for r in receipts if r.payment_method == 'Card')
    eft_total = sum(r.amount for r in receipts if r.payment_method == 'EFT')
    grand_total = sum(r.amount for r in receipts)

    return render_template('receipts/daily_summary.html',
                          receipts=receipts,
                          selected_date=selected_date,
                          cash_total=cash_total,
                          card_total=card_total,
                          eft_total=eft_total,
                          grand_total=grand_total)
