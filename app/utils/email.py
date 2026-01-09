"""Email notification utilities."""
from flask import current_app, render_template_string
from flask_mail import Message
from threading import Thread


def send_async_email(app, msg, mail):
    """Send email asynchronously."""
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"Failed to send email: {e}")


def send_email(subject, recipient, html_body, mail):
    """
    Send an email notification.

    Args:
        subject: Email subject
        recipient: Email address to send to
        html_body: HTML content of the email
        mail: Flask-Mail instance
    """
    if not recipient:
        return

    msg = Message(
        subject=f"[StaffTrack] {subject}",
        recipients=[recipient],
        html=html_body
    )

    # Send asynchronously to not block the request
    Thread(
        target=send_async_email,
        args=(current_app._get_current_object(), msg, mail)
    ).start()


# Email Templates
EMAIL_HEADER = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #16a34a 0%, #22c55e 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }
        .header h1 { margin: 0; font-size: 24px; }
        .content { background: #ffffff; padding: 30px; border: 1px solid #e5e7eb; }
        .footer { background: #f9fafb; padding: 15px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 8px 8px; border: 1px solid #e5e7eb; border-top: none; }
        .btn { display: inline-block; background: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 15px; }
        .btn:hover { background: #15803d; }
        .alert-warning { background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 15px 0; }
        .alert-danger { background: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; margin: 15px 0; }
        .alert-success { background: #dcfce7; border-left: 4px solid #22c55e; padding: 15px; margin: 15px 0; }
        .alert-info { background: #e0f2fe; border-left: 4px solid #0ea5e9; padding: 15px; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Staff<span style="color: #bbf7d0;">Track</span></h1>
        </div>
        <div class="content">
"""

EMAIL_FOOTER = """
        </div>
        <div class="footer">
            <p>This is an automated message from StaffTrack.</p>
            <p>Dr. Buleni's Dental Practice</p>
        </div>
    </div>
</body>
</html>
"""


def email_leave_request_submitted(staff_name, leave_type, start_date, end_date, reason):
    """Email template for leave request submission (sent to managers)."""
    return f"""{EMAIL_HEADER}
        <h2>New Leave Request</h2>
        <p><strong>{staff_name}</strong> has submitted a leave request.</p>

        <div class="alert-info">
            <p><strong>Leave Type:</strong> {leave_type}</p>
            <p><strong>Dates:</strong> {start_date} to {end_date}</p>
            <p><strong>Reason:</strong> {reason or 'Not specified'}</p>
        </div>

        <p>Please log in to StaffTrack to approve or reject this request.</p>
    {EMAIL_FOOTER}"""


def email_leave_request_approved(staff_name, leave_type, start_date, end_date, notes):
    """Email template for leave approval (sent to staff)."""
    return f"""{EMAIL_HEADER}
        <h2>Leave Request Approved</h2>

        <div class="alert-success">
            <p>Good news! Your leave request has been <strong>approved</strong>.</p>
        </div>

        <p><strong>Leave Type:</strong> {leave_type}</p>
        <p><strong>Dates:</strong> {start_date} to {end_date}</p>
        {f'<p><strong>Notes:</strong> {notes}</p>' if notes else ''}

        <p>Enjoy your time off!</p>
    {EMAIL_FOOTER}"""


def email_leave_request_rejected(staff_name, leave_type, start_date, end_date, notes):
    """Email template for leave rejection (sent to staff)."""
    return f"""{EMAIL_HEADER}
        <h2>Leave Request Rejected</h2>

        <div class="alert-danger">
            <p>Unfortunately, your leave request has been <strong>rejected</strong>.</p>
        </div>

        <p><strong>Leave Type:</strong> {leave_type}</p>
        <p><strong>Dates:</strong> {start_date} to {end_date}</p>
        {f'<p><strong>Reason:</strong> {notes}</p>' if notes else ''}

        <p>Please speak with your manager if you have questions.</p>
    {EMAIL_FOOTER}"""


def email_task_assigned(staff_name, task_title, task_description, due_date):
    """Email template for task assignment."""
    return f"""{EMAIL_HEADER}
        <h2>New Task Assigned</h2>
        <p>Hello {staff_name},</p>
        <p>A new task has been assigned to you.</p>

        <div class="alert-info">
            <p><strong>Task:</strong> {task_title}</p>
            {f'<p><strong>Description:</strong> {task_description}</p>' if task_description else ''}
            <p><strong>Due Date:</strong> {due_date if due_date else 'No deadline'}</p>
        </div>

        <p>Please log in to StaffTrack to view and update your tasks.</p>
    {EMAIL_FOOTER}"""


def email_warning_issued(staff_name, warning_type, reason, issued_by):
    """Email template for warning notification."""
    return f"""{EMAIL_HEADER}
        <h2>Warning Issued</h2>
        <p>Hello {staff_name},</p>

        <div class="alert-warning">
            <p>A warning has been issued to you.</p>
        </div>

        <p><strong>Warning Type:</strong> {warning_type.replace('_', ' ')}</p>
        <p><strong>Reason:</strong> {reason}</p>
        <p><strong>Issued By:</strong> {issued_by}</p>

        <p>Please speak with your manager if you have questions about this warning.</p>
    {EMAIL_FOOTER}"""


def email_kpi_scored(staff_name, week_start, total_kpis, met_kpis, percentage):
    """Email template for KPI score notification."""
    alert_class = 'alert-success' if percentage >= 70 else 'alert-warning' if percentage >= 50 else 'alert-danger'

    return f"""{EMAIL_HEADER}
        <h2>Weekly KPI Scores</h2>
        <p>Hello {staff_name},</p>
        <p>Your KPI scores for the week of {week_start} have been recorded.</p>

        <div class="{alert_class}">
            <p style="font-size: 24px; font-weight: bold; margin: 0;">{percentage:.0f}%</p>
            <p style="margin: 5px 0 0 0;">{met_kpis} out of {total_kpis} KPIs met</p>
        </div>

        <p>Log in to StaffTrack to see detailed scores.</p>
    {EMAIL_FOOTER}"""
