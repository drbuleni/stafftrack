from functools import wraps
from flask import abort
from flask_login import current_user


def role_required(*roles):
    """
    Decorator to restrict access to specific roles.
    Usage: @role_required('Super Admin', 'Practice Manager')
    Note: Must be used AFTER @login_required decorator.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def manager_required(f):
    """Shortcut decorator for Practice Manager and Super Admin access."""
    return role_required('Practice Manager', 'Super Admin')(f)


def admin_required(f):
    """Shortcut decorator for Super Admin only access."""
    return role_required('Super Admin')(f)


def receipt_access_required(f):
    """Decorator for receipt creation - Receptionist, Practice Manager, Super Admin, Dentist."""
    return role_required('Receptionist', 'Practice Manager', 'Super Admin', 'Dentist')(f)
