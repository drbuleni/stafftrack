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
