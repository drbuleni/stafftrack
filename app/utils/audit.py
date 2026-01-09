from flask import request
from flask_login import current_user
from app import db
from app.models import AuditLog


def log_audit(action, entity_type=None, entity_id=None, details=None):
    """
    Log an action to the audit log.

    Args:
        action: Description of the action (e.g., "Created Receipt", "Approved Leave")
        entity_type: Type of entity affected (e.g., "Receipt", "Leave", "Task")
        entity_id: ID of the affected entity
        details: Dictionary with additional details about the action
    """
    audit_entry = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=request.remote_addr if request else None
    )
    db.session.add(audit_entry)
    db.session.commit()
    return audit_entry
