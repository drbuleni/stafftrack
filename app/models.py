from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # Staff, Receptionist, Dentist, Dental Assistant, Cleaner, Practice Manager, Super Admin
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    start_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='Active')  # Active/Inactive
    practice_id = db.Column(db.Integer, db.ForeignKey('practices.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    receipts = db.relationship('Receipt', backref='creator', lazy='dynamic', foreign_keys='Receipt.created_by')
    assigned_tasks = db.relationship('Task', backref='assignee', lazy='dynamic', foreign_keys='Task.assigned_to')
    created_tasks = db.relationship('Task', backref='creator', lazy='dynamic', foreign_keys='Task.created_by')
    schedules = db.relationship('Schedule', backref='staff', lazy='dynamic', foreign_keys='Schedule.staff_id')
    leave_requests = db.relationship('LeaveRequest', backref='staff', lazy='dynamic', foreign_keys='LeaveRequest.staff_id')
    kpi_scores = db.relationship('KPIScore', backref='staff', lazy='dynamic', foreign_keys='KPIScore.staff_id')
    performance_events = db.relationship('PerformanceEvent', backref='staff', lazy='dynamic', foreign_keys='PerformanceEvent.staff_id')
    sop_acknowledgements = db.relationship('SOPAcknowledgement', backref='staff', lazy='dynamic')
    warnings_received = db.relationship('Warning', backref='staff', lazy='dynamic', foreign_keys='Warning.staff_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


class Receipt(db.Model):
    __tablename__ = 'receipts'

    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # Cash/Card/EFT
    description = db.Column(db.Text)
    # Patient details for receipt
    patient_name = db.Column(db.String(100))
    patient_email = db.Column(db.String(100))
    email_sent = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Receipt {self.receipt_number}>'


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='To Do')  # To Do/In Progress/Done
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Task {self.title}>'


class Schedule(db.Model):
    __tablename__ = 'schedule'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    role = db.Column(db.String(50), nullable=False)
    shift_type = db.Column(db.String(20), default='Full Day')  # Full Day/Morning/Afternoon/Off
    room = db.Column(db.String(50))  # Black Room/Red Room/Pink Room (for dental assistants)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('staff_id', 'date', name='unique_staff_date'),)

    creator = db.relationship('User', foreign_keys=[created_by], backref='created_schedules')

    def __repr__(self):
        return f'<Schedule {self.staff_id} on {self.date}>'


class LeaveRequest(db.Model):
    __tablename__ = 'leave_requests'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type = db.Column(db.String(50), nullable=False)  # Annual/Sick/Unpaid/Other
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pending')  # Pending/Approved/Rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approval_notes = db.Column(db.Text)
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_leaves')

    def __repr__(self):
        return f'<LeaveRequest {self.staff_id} {self.leave_type}>'


class LeaveDocument(db.Model):
    """A doctor's note attached to a sick leave request.

    Stored in the database rather than on disk: the server filesystem is
    ephemeral on Render, and a sick note is exactly the document someone
    needs to produce months later. Kept in its own table so that bulk
    queries over leave_requests never pull file bytes into memory.
    """
    __tablename__ = 'leave_documents'

    id = db.Column(db.Integer, primary_key=True)
    leave_request_id = db.Column(db.Integer, db.ForeignKey('leave_requests.id'),
                                 nullable=False, index=True)

    filename = db.Column(db.String(255))
    content_type = db.Column(db.String(100))
    byte_size = db.Column(db.Integer)
    data = db.Column(db.LargeBinary, nullable=False)

    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    leave_request = db.relationship(
        'LeaveRequest',
        backref=db.backref('documents', cascade='all, delete-orphan', lazy='select')
    )
    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    @property
    def size_display(self):
        """Human-readable file size."""
        size = self.byte_size or 0
        if size < 1024:
            return f'{size} B'
        if size < 1024 * 1024:
            return f'{size / 1024:.0f} KB'
        return f'{size / (1024 * 1024):.1f} MB'

    def __repr__(self):
        return f'<LeaveDocument {self.filename} for leave {self.leave_request_id}>'


class KPIScore(db.Model):
    """Monthly KPI scores for staff members."""
    __tablename__ = 'kpi_scores'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kpi_id = db.Column(db.Integer, db.ForeignKey('role_kpis.id'), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Integer, nullable=False)  # 0 = Not Met, 1 = Met
    notes = db.Column(db.Text)
    scored_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scored_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    kpi = db.relationship('RoleKPI', backref='scores')
    scorer = db.relationship('User', foreign_keys=[scored_by], backref='scored_kpis')

    __table_args__ = (db.UniqueConstraint('staff_id', 'kpi_id', 'month', 'year', name='unique_staff_kpi_month'),)

    def __repr__(self):
        return f'<KPIScore {self.staff_id} KPI:{self.kpi_id} {self.month}/{self.year}>'


class PerformanceEvent(db.Model):
    __tablename__ = 'performance_events'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)  # Warning/Recognition/KPI_Score/Task_Complete/Leave
    event_description = db.Column(db.Text, nullable=False)
    event_data = db.Column(db.JSON)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by], backref='created_events')

    def __repr__(self):
        return f'<PerformanceEvent {self.staff_id} {self.event_type}>'


class SOPDocument(db.Model):
    __tablename__ = 'sop_documents'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    version = db.Column(db.String(20), default='1.0')
    description = db.Column(db.Text)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploader = db.relationship('User', foreign_keys=[uploaded_by], backref='uploaded_sops')
    acknowledgements = db.relationship('SOPAcknowledgement', backref='sop', lazy='dynamic')

    def __repr__(self):
        return f'<SOPDocument {self.title}>'


class SOPAcknowledgement(db.Model):
    __tablename__ = 'sop_acknowledgements'

    id = db.Column(db.Integer, primary_key=True)
    sop_id = db.Column(db.Integer, db.ForeignKey('sop_documents.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    acknowledged_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('sop_id', 'staff_id', name='unique_sop_staff'),)

    def __repr__(self):
        return f'<SOPAcknowledgement {self.sop_id} by {self.staff_id}>'


class Warning(db.Model):
    __tablename__ = 'warnings'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    warning_type = db.Column(db.String(50), nullable=False)  # Late/Task_Missed/KPI_Failed/Manual
    reason = db.Column(db.Text, nullable=False)
    auto_generated = db.Column(db.Boolean, default=False)
    issued_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)

    issuer = db.relationship('User', foreign_keys=[issued_by], backref='issued_warnings')

    def __repr__(self):
        return f'<Warning {self.staff_id} {self.warning_type}>'


class AuditLog(db.Model):
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='audit_logs')

    def __repr__(self):
        return f'<AuditLog {self.action} by {self.user_id}>'


class KPICategory(db.Model):
    """KPI categories for organizing KPIs by role."""
    __tablename__ = 'kpi_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    role = db.Column(db.String(50), nullable=False)  # Dental Assistant, Dentist, Receptionist, Cleaner
    weight = db.Column(db.Integer, default=0)  # Category weight percentage (e.g., 30 = 30%)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to KPIs in this category
    kpis = db.relationship('RoleKPI', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<KPICategory {self.name} for {self.role}>'


class RoleKPI(db.Model):
    """Individual KPIs for each role."""
    __tablename__ = 'role_kpis'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('kpi_categories.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    role = db.Column(db.String(50), nullable=False)  # Redundant but useful for queries
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<RoleKPI {self.name}>'


class Notification(db.Model):
    """System notifications for users."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # task_overdue/leave_pending/warning/kpi_low/general
    link = db.Column(db.String(500))  # Optional link to related page
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='notifications')

    def __repr__(self):
        return f'<Notification {self.title} for {self.user_id}>'


class Room(db.Model):
    """Practice rooms for scheduling."""
    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20))  # For UI display
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Room {self.name}>'


class Announcement(db.Model):
    """Announcements posted by Super Admin or Practice Manager."""
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='Normal')  # Normal/Important/Urgent
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # Optional expiry date

    creator = db.relationship('User', foreign_keys=[created_by], backref='announcements')

    def __repr__(self):
        return f'<Announcement {self.title}>'


class CalendarEvent(db.Model):
    """Calendar events for birthdays, awareness days, and special occasions."""
    __tablename__ = 'calendar_events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    event_date = db.Column(db.Date, nullable=False)
    event_type = db.Column(db.String(50), nullable=False)  # Birthday, Awareness Day, Holiday, Meeting, Other
    color = db.Column(db.String(20), default='primary')  # Bootstrap color class
    is_recurring = db.Column(db.Boolean, default=False)  # Repeats yearly (for birthdays, awareness days)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # Link to staff for birthdays
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    staff = db.relationship('User', foreign_keys=[staff_id], backref='birthday_events')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_calendar_events')

    def __repr__(self):
        return f'<CalendarEvent {self.title} on {self.event_date}>'


class DailyReconciliation(db.Model):
    """Daily reconciliation sheet for tracking operations and cash-up."""
    __tablename__ = 'daily_reconciliations'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    day_of_week = db.Column(db.String(20))

    # Section A: Morning Counts
    dentists_on_duty = db.Column(db.JSON)  # List of dentist IDs on duty
    staff_on_duty = db.Column(db.Integer, default=0)
    appointments_booked = db.Column(db.JSON)  # {dentist_id: count}
    confirmed_appointments = db.Column(db.Integer, default=0)
    reminder_messages_sent = db.Column(db.Integer, default=0)
    new_patients_booked = db.Column(db.Integer, default=0)
    medical_aid_preauth_received = db.Column(db.Integer, default=0)
    lab_cases = db.Column(db.Integer, default=0)

    # Section B: End-of-Day Patient Flow
    patients_treated = db.Column(db.Integer, default=0)
    no_shows = db.Column(db.Integer, default=0)
    cancelled = db.Column(db.Integer, default=0)
    rescheduled = db.Column(db.Integer, default=0)
    walk_ins_treated = db.Column(db.Integer, default=0)

    # Section C: End-of-Day Cash-Up (Money In)
    eft_received = db.Column(db.Numeric(10, 2), default=0)  # total across both accounts
    eft_fnb = db.Column(db.Numeric(10, 2), default=0)
    eft_capitec = db.Column(db.Numeric(10, 2), default=0)
    card_fnb = db.Column(db.Numeric(10, 2), default=0)
    card_capitec = db.Column(db.Numeric(10, 2), default=0)
    medical_aid_payments = db.Column(db.Numeric(10, 2), default=0)
    medical_aid_balance_payments = db.Column(db.Numeric(10, 2), default=0)
    other_payments = db.Column(db.Numeric(10, 2), default=0)
    other_payments_description = db.Column(db.String(200))

    # Money Out
    refunds_expenses = db.Column(db.Numeric(10, 2), default=0)

    # Calculated fields (stored for reporting)
    total_money_in = db.Column(db.Numeric(10, 2), default=0)
    net_collections = db.Column(db.Numeric(10, 2), default=0)

    # Section D: Reconciliation
    # goodx_production holds total billed NET of credit notes for the day.
    # The credit-note total itself is derived from the billing rows rather
    # than stored, so there is only one source of truth.
    goodx_production = db.Column(db.Numeric(10, 2), default=0)
    goodx_collections = db.Column(db.Numeric(10, 2), default=0)
    variance = db.Column(db.Numeric(10, 2), default=0)
    variance_explanation = db.Column(db.Text)

    # Section E: Retail/Stock Sales
    retail_sales = db.Column(db.JSON)  # {item_name: {qty: x, amount: y}}

    # Section F: Payment References
    fnb_batch = db.Column(db.String(50))
    capitec_batch = db.Column(db.String(50))
    eft_ref = db.Column(db.String(50))
    cash_deposit = db.Column(db.String(50))
    med_aid_ref = db.Column(db.String(50))

    # Sign-off
    prepared_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    prepared_at = db.Column(db.DateTime)
    checked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    checked_at = db.Column(db.DateTime)

    # Notes
    notes = db.Column(db.Text)

    # Status
    status = db.Column(db.String(20), default='Draft')  # Draft, Submitted, Checked

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    preparer = db.relationship('User', foreign_keys=[prepared_by], backref='prepared_reconciliations')
    checker = db.relationship('User', foreign_keys=[checked_by], backref='checked_reconciliations')

    def calculate_totals(self):
        """Calculate total money in and net collections."""
        self.total_money_in = (
            (self.eft_received or 0) +
            (self.card_fnb or 0) +
            (self.card_capitec or 0) +
            (self.medical_aid_payments or 0) +
            (self.medical_aid_balance_payments or 0) +
            (self.other_payments or 0)
        )
        self.net_collections = self.total_money_in - (self.refunds_expenses or 0)
        self.variance = self.net_collections - (self.goodx_collections or 0)

    def __repr__(self):
        return f'<DailyReconciliation {self.date}>'


class ReconciliationBillingEntry(db.Model):
    """A single patient billing line on a provider's daily billing sheet."""
    __tablename__ = 'reconciliation_billing_entries'

    id = db.Column(db.Integer, primary_key=True)
    reconciliation_id = db.Column(db.Integer, db.ForeignKey('daily_reconciliations.id'), nullable=False)

    provider_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # optional link to a staff member
    provider_name = db.Column(db.String(100), nullable=False)  # display name, e.g. "Dr Buleni"

    computer_no = db.Column(db.String(50))
    file_no = db.Column(db.String(50))
    patient_name = db.Column(db.String(150))
    medical_aid = db.Column(db.String(100))  # medical aid name or "Private"
    amount_billed = db.Column(db.Numeric(10, 2), default=0)
    card_paid = db.Column(db.Numeric(10, 2), default=0)   # Card Payment KAS7
    card_bank = db.Column(db.String(10), default='FNB')   # which speedpoint: FNB or Capitec
    eft_paid = db.Column(db.Numeric(10, 2), default=0)    # EFT Payment KAS3
    eft_bank = db.Column(db.String(10), default='FNB')    # which account the EFT landed in
    credit_note = db.Column(db.Numeric(10, 2), default=0)  # reduces the billed amount
    credit_note_reason = db.Column(db.String(50))  # e.g. Wrong patient
    # A journal also removes a balance, but for an accounting reason rather
    # than a billing error: it is not income, profit or an amount billed.
    journal = db.Column(db.Numeric(10, 2), default=0)
    journal_reason = db.Column(db.String(60))  # e.g. Doctor Discount / Write-off
    receipt_no = db.Column(db.String(50))
    sort_order = db.Column(db.Integer, default=0)

    reconciliation = db.relationship(
        'DailyReconciliation',
        backref=db.backref('billing_entries', cascade='all, delete-orphan',
                           order_by='ReconciliationBillingEntry.sort_order')
    )
    provider = db.relationship('User', foreign_keys=[provider_id])

    def __repr__(self):
        return f'<ReconciliationBillingEntry {self.provider_name} - {self.patient_name}>'


class ReconciliationEraPayment(db.Model):
    """An ERA (medical aid remittance) payment received - KAS6."""
    __tablename__ = 'reconciliation_era_payments'

    id = db.Column(db.Integer, primary_key=True)
    reconciliation_id = db.Column(db.Integer, db.ForeignKey('daily_reconciliations.id'), nullable=False)

    batch_number = db.Column(db.String(50))
    medical_aid_name = db.Column(db.String(100))
    payment_date = db.Column(db.Date)
    amount_paid = db.Column(db.Numeric(10, 2), default=0)
    sort_order = db.Column(db.Integer, default=0)

    reconciliation = db.relationship(
        'DailyReconciliation',
        backref=db.backref('era_payments', cascade='all, delete-orphan',
                           order_by='ReconciliationEraPayment.sort_order')
    )

    def __repr__(self):
        return f'<ReconciliationEraPayment {self.batch_number} - {self.medical_aid_name}>'


class PatientFlow(db.Model):
    """Daily patient flow counts, captured separately from the money.

    Deliberately narrow: only the three figures the practice can record
    reliably. Reschedules and consultations were considered and dropped
    because front-desk data for them is not dependable, and a monthly
    report built on unreliable counts is worse than no report.
    """
    __tablename__ = 'patient_flow'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)

    treated = db.Column(db.Integer, default=0)
    walk_ins = db.Column(db.Integer, default=0)
    no_shows = db.Column(db.Integer, default=0)

    notes = db.Column(db.Text)

    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recorder = db.relationship('User', foreign_keys=[recorded_by])

    @property
    def total_expected(self):
        """Everyone who was meant to be seen: those treated plus no-shows.
        Walk-ins are excluded - they were never booked."""
        return (self.treated or 0) + (self.no_shows or 0)

    @property
    def no_show_rate(self):
        expected = self.total_expected
        return (self.no_shows or 0) / expected * 100 if expected else 0

    def __repr__(self):
        return f'<PatientFlow {self.date}>'


class TurnoverReport(db.Model):
    """Monthly Turnover & Cash Flow report. Figures are captured from GoodX;
    StaffTrack standardises the layout and computes all totals."""
    __tablename__ = 'turnover_reports'

    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)

    # Optional VAT summary
    vat_inclusive = db.Column(db.Numeric(12, 2))
    vat_exclusive = db.Column(db.Numeric(12, 2))
    vat_number = db.Column(db.String(30))  # practice VAT registration number

    # The two written sections of the monthly report document. Both are
    # pre-drafted from the figures, so Sinah edits rather than starts blank.
    interpretation = db.Column(db.Text)
    final_summary = db.Column(db.Text)

    notes = db.Column(db.Text)

    prepared_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    preparer = db.relationship('User', foreign_keys=[prepared_by])

    __table_args__ = (db.UniqueConstraint('year', 'month', name='unique_turnover_report_period'),)

    def __repr__(self):
        return f'<TurnoverReport {self.month}/{self.year}>'


class TurnoverReportSection(db.Model):
    """One practitioner's figures on a monthly turnover report."""
    __tablename__ = 'turnover_report_sections'

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('turnover_reports.id'), nullable=False)

    practitioner_name = db.Column(db.String(100), nullable=False)
    room = db.Column(db.String(50))  # optional room allocation

    # Turnover
    gross_turnover = db.Column(db.Numeric(12, 2), default=0)
    additional_turnover = db.Column(db.Numeric(12, 2), default=0)
    credit_notes = db.Column(db.Numeric(12, 2), default=0)  # stored positive, subtracted

    # Cash flow deposits per cashbook
    kas1_cash = db.Column(db.Numeric(12, 2), default=0)
    kas3_eft = db.Column(db.Numeric(12, 2), default=0)
    kas6_era = db.Column(db.Numeric(12, 2), default=0)
    kas7_card = db.Column(db.Numeric(12, 2), default=0)
    kas8_linking = db.Column(db.Numeric(12, 2), default=0)  # allocations, never added to cash totals

    # Corrections per cashbook
    kas1_corrections = db.Column(db.Numeric(12, 2), default=0)
    kas3_corrections = db.Column(db.Numeric(12, 2), default=0)
    kas6_corrections = db.Column(db.Numeric(12, 2), default=0)
    kas7_corrections = db.Column(db.Numeric(12, 2), default=0)
    kas8_corrections = db.Column(db.Numeric(12, 2), default=0)

    # General journal adjustments: list of {"description": str, "amount": float}
    journals = db.Column(db.JSON)

    movement_balance = db.Column(db.Numeric(12, 2), default=0)  # GoodX control total, captured not computed
    sort_order = db.Column(db.Integer, default=0)

    report = db.relationship(
        'TurnoverReport',
        backref=db.backref('sections', cascade='all, delete-orphan',
                           order_by='TurnoverReportSection.sort_order')
    )

    @property
    def net_turnover(self):
        return (self.gross_turnover or 0) + (self.additional_turnover or 0) - (self.credit_notes or 0)

    @property
    def cash_flow_total(self):
        """Actual money received: KAS1/3/6/7 deposits plus their corrections.
        KAS8 linking is excluded - it re-allocates money already received."""
        return ((self.kas1_cash or 0) + (self.kas3_eft or 0) + (self.kas6_era or 0) +
                (self.kas7_card or 0) + (self.kas1_corrections or 0) + (self.kas3_corrections or 0) +
                (self.kas6_corrections or 0) + (self.kas7_corrections or 0))

    @property
    def journals_total(self):
        return sum((j.get('amount') or 0) for j in (self.journals or []))

    def __repr__(self):
        return f'<TurnoverReportSection {self.practitioner_name}>'


# =====================================================================
# Quoting & Lead Pipeline module
# =====================================================================

class Practice(db.Model):
    """A tenant practice. All quoting/lead data is scoped to a practice."""
    __tablename__ = 'practices'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    logo_path = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship('User', backref='practice', lazy='dynamic', foreign_keys='User.practice_id')

    def __repr__(self):
        return f'<Practice {self.name}>'


class SadaCode(db.Model):
    """SADA procedure code in a practice's master library."""
    __tablename__ = 'sada_codes'

    id = db.Column(db.Integer, primary_key=True)
    practice_id = db.Column(db.Integer, db.ForeignKey('practices.id'), nullable=False, index=True)
    code = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=False)
    default_price_medical_aid = db.Column(db.Numeric(10, 2), default=0)
    default_price_cash = db.Column(db.Numeric(10, 2), default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('practice_id', 'code', name='unique_practice_sada_code'),)

    def __repr__(self):
        return f'<SadaCode {self.code}>'


class Icd10Code(db.Model):
    """ICD-10 diagnostic code in a practice's curated list."""
    __tablename__ = 'icd10_codes'

    id = db.Column(db.Integer, primary_key=True)
    practice_id = db.Column(db.Integer, db.ForeignKey('practices.id'), nullable=False, index=True)
    code = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('practice_id', 'code', name='unique_practice_icd10_code'),)

    def __repr__(self):
        return f'<Icd10Code {self.code}>'


class TreatmentTemplate(db.Model):
    """A named treatment plan (Implant, Whitening, RCT, etc.) made of code lines."""
    __tablename__ = 'treatment_templates'

    id = db.Column(db.Integer, primary_key=True)
    practice_id = db.Column(db.Integer, db.ForeignKey('practices.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), default='General')
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lines = db.relationship(
        'TreatmentTemplateLine',
        backref='template',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='TreatmentTemplateLine.visit_number, TreatmentTemplateLine.sequence'
    )

    __table_args__ = (db.UniqueConstraint('practice_id', 'name', name='unique_practice_template_name'),)

    def __repr__(self):
        return f'<TreatmentTemplate {self.name}>'


class TreatmentTemplateLine(db.Model):
    """A single code line within a treatment template."""
    __tablename__ = 'treatment_template_lines'

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('treatment_templates.id'), nullable=False, index=True)
    visit_number = db.Column(db.Integer, default=1)
    visit_title = db.Column(db.String(200))
    sequence = db.Column(db.Integer, default=0)
    sada_code_id = db.Column(db.Integer, db.ForeignKey('sada_codes.id'), nullable=False)
    default_icd10_code_id = db.Column(db.Integer, db.ForeignKey('icd10_codes.id'))
    default_quantity = db.Column(db.Integer, default=1)
    default_tooth_number = db.Column(db.String(20))

    sada_code = db.relationship('SadaCode', foreign_keys=[sada_code_id])
    default_icd10_code = db.relationship('Icd10Code', foreign_keys=[default_icd10_code_id])

    def __repr__(self):
        return f'<TemplateLine tmpl={self.template_id} v{self.visit_number}.{self.sequence}>'


class Quote(db.Model):
    """A quote issued to a patient. Immutable doc-style record."""
    __tablename__ = 'quotes'

    id = db.Column(db.Integer, primary_key=True)
    practice_id = db.Column(db.Integer, db.ForeignKey('practices.id'), nullable=False, index=True)
    quote_number = db.Column(db.String(50), nullable=False)
    patient_name = db.Column(db.String(200), nullable=False)
    patient_phone = db.Column(db.String(50))
    quote_date = db.Column(db.Date, nullable=False)
    treatment_template_id = db.Column(db.Integer, db.ForeignKey('treatment_templates.id'))
    treatment_label = db.Column(db.String(200))
    pricing_mode = db.Column(db.String(20), default='medical_aid')  # medical_aid / cash
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lines = db.relationship(
        'QuoteLine',
        backref='quote',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='QuoteLine.visit_number, QuoteLine.sequence'
    )
    lead = db.relationship('Lead', backref='quote', uselist=False, cascade='all, delete-orphan')
    template = db.relationship('TreatmentTemplate', foreign_keys=[treatment_template_id])
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_quotes')

    __table_args__ = (db.UniqueConstraint('practice_id', 'quote_number', name='unique_practice_quote_number'),)

    def recalc_totals(self):
        total = sum((line.line_total or 0) for line in self.lines)
        self.subtotal = total
        self.grand_total = total

    def visit_groups(self):
        """Return lines grouped by visit_number, in order. List of (visit_number, [lines])."""
        groups = {}
        for line in self.lines:
            groups.setdefault(line.visit_number or 1, []).append(line)
        return sorted(groups.items())

    def __repr__(self):
        return f'<Quote {self.quote_number}>'


class QuoteLine(db.Model):
    """A single code line on a quote. Prices are snapshotted at quote time."""
    __tablename__ = 'quote_lines'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('quotes.id'), nullable=False, index=True)
    visit_number = db.Column(db.Integer, default=1)
    visit_title = db.Column(db.String(200))
    sequence = db.Column(db.Integer, default=0)
    sada_code_id = db.Column(db.Integer, db.ForeignKey('sada_codes.id'))
    icd10_code_id = db.Column(db.Integer, db.ForeignKey('icd10_codes.id'))
    code_snapshot = db.Column(db.String(20))
    icd10_snapshot = db.Column(db.String(20))
    description_snapshot = db.Column(db.Text)
    unit_price_snapshot = db.Column(db.Numeric(10, 2), default=0)
    tooth_number = db.Column(db.String(20))
    quantity = db.Column(db.Integer, default=1)
    line_total = db.Column(db.Numeric(12, 2), default=0)
    paid_status = db.Column(db.String(20), default='unpaid')  # unpaid / paid

    sada_code = db.relationship('SadaCode', foreign_keys=[sada_code_id])
    icd10_code = db.relationship('Icd10Code', foreign_keys=[icd10_code_id])

    def __repr__(self):
        return f'<QuoteLine quote={self.quote_id} code={self.code_snapshot}>'


class Lead(db.Model):
    """The CRM-side record for an issued quote. One lead per quote."""
    __tablename__ = 'leads'

    id = db.Column(db.Integer, primary_key=True)
    practice_id = db.Column(db.Integer, db.ForeignKey('practices.id'), nullable=False, index=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('quotes.id'), nullable=False, unique=True)
    status = db.Column(db.String(20), default='new', nullable=False)
    # new / contacted / interested / converted / dead
    next_followup_date = db.Column(db.Date)
    converted_at = db.Column(db.DateTime)
    dead_at = db.Column(db.DateTime)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    interactions = db.relationship(
        'LeadInteraction',
        backref='lead',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='LeadInteraction.interacted_at.desc()'
    )
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_leads')

    def __repr__(self):
        return f'<Lead quote={self.quote_id} status={self.status}>'


class LeadInteraction(db.Model):
    """A logged interaction (call, message, note) on a lead."""
    __tablename__ = 'lead_interactions'

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False, index=True)
    interacted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    channel = db.Column(db.String(20), default='call')  # call / sms / whatsapp / email / in_person / note
    note = db.Column(db.Text)
    outcome = db.Column(db.String(200))
    status_at_interaction = db.Column(db.String(20))
    next_followup_date = db.Column(db.Date)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by], backref='created_interactions')

    def __repr__(self):
        return f'<LeadInteraction lead={self.lead_id} {self.channel} at {self.interacted_at}>'
