from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import KPIScore, KPICategory, RoleKPI, User, PerformanceEvent, Warning, Notification
from app.utils.decorators import manager_required
from app.utils.audit import log_audit
from datetime import date, datetime
from sqlalchemy import func
import calendar

bp = Blueprint('kpi', __name__, url_prefix='/kpi')

# Roles that have KPIs defined
KPI_ROLES = ['Dental Assistant', 'Dentist', 'Receptionist', 'Cleaner']

# Practice Manager uses Dentist KPIs (since the PM is also a dentist in this practice)
# Super Admin (practice owner) is excluded from KPIs
SCORABLE_ROLES = ['Dental Assistant', 'Dentist', 'Receptionist', 'Cleaner', 'Practice Manager']

def get_kpi_role(user_role):
    """Map user role to KPI role. Practice Manager uses Dentist KPIs."""
    if user_role == 'Practice Manager':
        return 'Dentist'
    return user_role

MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]


def get_kpis_for_role(role):
    """Get all KPIs organized by category for a specific role."""
    categories = KPICategory.query.filter_by(role=role, is_active=True).order_by(KPICategory.name).all()
    result = []
    for cat in categories:
        kpis = RoleKPI.query.filter_by(category_id=cat.id, is_active=True).all()
        result.append({
            'category': cat,
            'kpis': kpis
        })
    return result


def calculate_monthly_score(staff_id, month, year):
    """Calculate the overall KPI score for a staff member for a given month."""
    staff = User.query.get(staff_id)
    if not staff or staff.role not in KPI_ROLES:
        return None

    # Get all KPIs for this staff's role (Practice Manager uses Dentist KPIs)
    kpi_role = get_kpi_role(staff.role)
    role_kpis = RoleKPI.query.filter_by(role=kpi_role, is_active=True).all()
    if not role_kpis:
        return None

    kpi_ids = [k.id for k in role_kpis]

    # Get scores for this month
    scores = KPIScore.query.filter(
        KPIScore.staff_id == staff_id,
        KPIScore.kpi_id.in_(kpi_ids),
        KPIScore.month == month,
        KPIScore.year == year
    ).all()

    if not scores:
        return None

    met = sum(1 for s in scores if s.score == 1)
    total = len(scores)
    percentage = (met / total * 100) if total > 0 else 0

    return {
        'met': met,
        'total': total,
        'percentage': percentage,
        'total_kpis': len(role_kpis),
        'scored': total == len(role_kpis)  # True if all KPIs have been scored
    }


@bp.route('/')
@login_required
def index():
    """View KPI dashboard."""
    today = date.today()
    current_month = today.month
    current_year = today.year

    if current_user.role in ['Practice Manager', 'Super Admin']:
        # Show team overview for managers (excludes Super Admin from being scored)
        staff = User.query.filter(
            User.status == 'Active',
            User.role.in_(SCORABLE_ROLES)
        ).order_by(User.role, User.full_name).all()

        scores_by_staff = {}
        for member in staff:
            score_data = calculate_monthly_score(member.id, current_month, current_year)
            if score_data:
                scores_by_staff[member.id] = score_data

        return render_template('kpi/index.html',
                              staff=staff,
                              scores_by_staff=scores_by_staff,
                              current_month=current_month,
                              current_year=current_year,
                              month_name=MONTH_NAMES[current_month])
    else:
        # Show own KPIs for regular staff
        return redirect(url_for('kpi.my_kpis'))


@bp.route('/my-kpis')
@login_required
def my_kpis():
    """View own KPIs."""
    today = date.today()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    if current_user.role not in SCORABLE_ROLES:
        flash('No KPIs are defined for your role.', 'info')
        return redirect(url_for('dashboard.index'))

    # Get KPIs organized by category (Practice Manager uses Dentist KPIs)
    kpi_role = get_kpi_role(current_user.role)
    kpi_data = get_kpis_for_role(kpi_role)

    # Get existing scores for this month
    scores_dict = {}
    scores = KPIScore.query.filter_by(
        staff_id=current_user.id,
        month=month,
        year=year
    ).all()
    for score in scores:
        scores_dict[score.kpi_id] = score

    # Calculate overall score
    score_summary = calculate_monthly_score(current_user.id, month, year)

    return render_template('kpi/my_kpis.html',
                          kpi_data=kpi_data,
                          scores_dict=scores_dict,
                          month=month,
                          year=year,
                          month_name=MONTH_NAMES[month],
                          score_summary=score_summary)


@bp.route('/score', methods=['GET', 'POST'])
@login_required
@manager_required
def score():
    """Score KPIs for a staff member."""
    # Get staff members who can be scored (excludes Super Admin)
    staff_list = User.query.filter(
        User.status == 'Active',
        User.role.in_(SCORABLE_ROLES)
    ).order_by(User.role, User.full_name).all()

    today = date.today()
    default_month = today.month
    default_year = today.year

    if request.method == 'POST':
        staff_id = request.form.get('staff_id', type=int)
        month = request.form.get('month', type=int)
        year = request.form.get('year', type=int)

        if not all([staff_id, month, year]):
            flash('Please select a staff member and month.', 'warning')
            return redirect(url_for('kpi.score'))

        staff = User.query.get(staff_id)
        if not staff or staff.role not in SCORABLE_ROLES:
            flash('Invalid staff member selected.', 'danger')
            return redirect(url_for('kpi.score'))

        # Get all KPIs for this role (Practice Manager uses Dentist KPIs)
        kpi_role = get_kpi_role(staff.role)
        role_kpis = RoleKPI.query.filter_by(role=kpi_role, is_active=True).all()

        # Delete existing scores for this month (allow re-scoring)
        KPIScore.query.filter_by(
            staff_id=staff_id,
            month=month,
            year=year
        ).delete()

        # Save new scores
        met_count = 0
        total_count = 0

        for kpi in role_kpis:
            score_value = request.form.get(f'kpi_{kpi.id}', type=int)
            notes = request.form.get(f'notes_{kpi.id}', '')

            if score_value is not None:
                kpi_score = KPIScore(
                    staff_id=staff_id,
                    kpi_id=kpi.id,
                    month=month,
                    year=year,
                    score=score_value,
                    notes=notes if notes else None,
                    scored_by=current_user.id
                )
                db.session.add(kpi_score)
                total_count += 1
                if score_value == 1:
                    met_count += 1

        db.session.commit()

        # Calculate percentage
        percentage = (met_count / total_count * 100) if total_count > 0 else 0

        # Create performance event
        event = PerformanceEvent(
            staff_id=staff_id,
            event_type='KPI_Score',
            event_description=f'Monthly KPI: {met_count}/{total_count} ({percentage:.0f}%) for {MONTH_NAMES[month]} {year}',
            event_data={
                'month': month,
                'year': year,
                'met': met_count,
                'total': total_count,
                'percentage': percentage
            },
            created_by=current_user.id
        )
        db.session.add(event)

        # Create notification for staff member
        notification = Notification(
            user_id=staff_id,
            title=f'KPI Score for {MONTH_NAMES[month]} {year}',
            message=f'Your KPI score has been recorded: {met_count}/{total_count} ({percentage:.0f}%)',
            notification_type='kpi_score',
            link=url_for('kpi.my_kpis', month=month, year=year)
        )
        db.session.add(notification)

        db.session.commit()

        # Check for auto-warning if below 70%
        if percentage < 70:
            check_kpi_warning(staff_id, month, year, percentage)

        log_audit('Scored KPIs', 'KPIScore', None, {
            'staff_id': staff_id,
            'staff_name': staff.full_name,
            'month': month,
            'year': year,
            'percentage': percentage
        })

        flash(f'KPI scores saved for {staff.full_name}. Score: {percentage:.0f}%', 'success')
        return redirect(url_for('kpi.index'))

    # GET request - show scoring form
    selected_staff_id = request.args.get('staff_id', type=int)
    selected_month = request.args.get('month', default_month, type=int)
    selected_year = request.args.get('year', default_year, type=int)

    kpi_data = None
    existing_scores = {}
    selected_staff = None

    if selected_staff_id:
        selected_staff = User.query.get(selected_staff_id)
        if selected_staff and selected_staff.role in SCORABLE_ROLES:
            kpi_role = get_kpi_role(selected_staff.role)
            kpi_data = get_kpis_for_role(kpi_role)

            # Get existing scores if any
            scores = KPIScore.query.filter_by(
                staff_id=selected_staff_id,
                month=selected_month,
                year=selected_year
            ).all()
            for score in scores:
                existing_scores[score.kpi_id] = score

    return render_template('kpi/score.html',
                          staff_list=staff_list,
                          selected_staff=selected_staff,
                          kpi_data=kpi_data,
                          existing_scores=existing_scores,
                          selected_month=selected_month,
                          selected_year=selected_year,
                          month_names=MONTH_NAMES,
                          current_year=today.year)


@bp.route('/history/<int:staff_id>')
@login_required
def history(staff_id):
    """View KPI history for a staff member."""
    # Check permission
    if staff_id != current_user.id and current_user.role not in ['Practice Manager', 'Super Admin']:
        flash('You do not have permission to view this.', 'danger')
        return redirect(url_for('kpi.index'))

    staff = User.query.get_or_404(staff_id)

    if staff.role not in SCORABLE_ROLES:
        flash('No KPIs are defined for this role.', 'info')
        return redirect(url_for('kpi.index'))

    # Get monthly summaries for the past 12 months
    today = date.today()
    monthly_scores = []

    for i in range(12):
        # Calculate month/year going backwards
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1

        score_data = calculate_monthly_score(staff_id, month, year)
        if score_data:
            monthly_scores.append({
                'month': month,
                'year': year,
                'month_name': MONTH_NAMES[month],
                **score_data
            })

    return render_template('kpi/history.html',
                          staff=staff,
                          monthly_scores=monthly_scores)


@bp.route('/rankings')
@login_required
def rankings():
    """View KPI rankings for current month."""
    today = date.today()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    # Get all staff who can be scored (excludes Super Admin)
    staff = User.query.filter(
        User.status == 'Active',
        User.role.in_(SCORABLE_ROLES)
    ).all()

    rankings_data = []
    for member in staff:
        score_data = calculate_monthly_score(member.id, month, year)
        if score_data and score_data['scored']:
            rankings_data.append({
                'staff': member,
                **score_data
            })

    # Sort by percentage descending
    rankings_data.sort(key=lambda x: x['percentage'], reverse=True)

    # Determine employee of the month
    employee_of_month = rankings_data[0] if rankings_data and rankings_data[0]['percentage'] >= 70 else None

    return render_template('kpi/rankings.html',
                          rankings=rankings_data,
                          month=month,
                          year=year,
                          month_name=MONTH_NAMES[month],
                          employee_of_month=employee_of_month)


def check_kpi_warning(staff_id, month, year, percentage):
    """Check if staff should receive an auto-warning for low KPI performance."""
    # Check previous month as well
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1

    prev_score = calculate_monthly_score(staff_id, prev_month, prev_year)

    # If 2 consecutive months below 70%, issue warning
    if prev_score and prev_score['percentage'] < 70:
        staff = User.query.get(staff_id)
        warning = Warning(
            staff_id=staff_id,
            warning_type='KPI_Failed',
            reason=f'Two consecutive months with KPI score below 70%: {MONTH_NAMES[prev_month]} ({prev_score["percentage"]:.0f}%) and {MONTH_NAMES[month]} ({percentage:.0f}%)',
            auto_generated=True,
            issued_by=1  # System/admin
        )
        db.session.add(warning)

        # Create notification for staff
        notification = Notification(
            user_id=staff_id,
            title='Performance Warning Issued',
            message=f'You have received an automatic warning for two consecutive months with KPI scores below 70%.',
            notification_type='warning',
            link=url_for('warnings.index')
        )
        db.session.add(notification)

        db.session.commit()

        log_audit('Auto-generated Warning', 'Warning', warning.id, {
            'staff_id': staff_id,
            'staff_name': staff.full_name,
            'warning_type': 'KPI_Failed',
            'auto_generated': True
        })


@bp.route('/view-kpis')
@login_required
def view_kpis():
    """View all KPIs for all roles (reference)."""
    all_kpis = {}
    for role in KPI_ROLES:
        all_kpis[role] = get_kpis_for_role(role)

    return render_template('kpi/view_kpis.html', all_kpis=all_kpis, roles=KPI_ROLES)
