from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from config import Config
import os
import click

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
mail = Mail()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure instance and upload folders exist
    os.makedirs(os.path.join(app.root_path, '..', 'instance'), exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # Register blueprints
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.routes.dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)


    from app.routes.tasks import bp as tasks_bp
    app.register_blueprint(tasks_bp)

    from app.routes.schedule import bp as schedule_bp
    app.register_blueprint(schedule_bp)

    from app.routes.leave import bp as leave_bp
    app.register_blueprint(leave_bp)

    from app.routes.kpi import bp as kpi_bp
    app.register_blueprint(kpi_bp)

    from app.routes.performance import bp as performance_bp
    app.register_blueprint(performance_bp)

    from app.routes.sop import bp as sop_bp
    app.register_blueprint(sop_bp)

    from app.routes.warnings import bp as warnings_bp
    app.register_blueprint(warnings_bp)

    from app.routes.audit import bp as audit_bp
    app.register_blueprint(audit_bp)

    from app.routes.users import bp as users_bp
    app.register_blueprint(users_bp)

    from app.routes.exports import bp as exports_bp
    app.register_blueprint(exports_bp)


    from app.routes.notifications import bp as notifications_bp
    app.register_blueprint(notifications_bp)

    from app.routes.announcements import bp as announcements_bp
    app.register_blueprint(announcements_bp)

    from app.routes.calendar import bp as calendar_bp
    app.register_blueprint(calendar_bp)

    from app.routes.reconciliation import bp as reconciliation_bp
    app.register_blueprint(reconciliation_bp)

    from app.routes.turnover import bp as turnover_bp
    app.register_blueprint(turnover_bp)

    from app.routes.patient_flow import bp as patient_flow_bp
    app.register_blueprint(patient_flow_bp)


    # A file bigger than MAX_CONTENT_LENGTH is refused by Werkzeug before any
    # view runs. Show a readable message instead of the default 413 page.
    @app.errorhandler(413)
    def file_too_large(error):
        from flask import flash, redirect, request as flask_request, url_for
        flash('That file is too large to upload. Please keep files under 5MB.', 'danger')
        return redirect(flask_request.referrer or url_for('dashboard.index')), 302

    # Register CLI commands
    @app.cli.command('recompute-billed')
    def recompute_billed_command():
        """Recompute stored Total Billed net of credit notes.

        Total Billed used to be stored gross, so a credit note that reverses
        an invoice was double-counted rather than cancelling it out. The
        formula is fixed, but sheets captured before the fix keep their old
        stored figure until this runs. Safe to run repeatedly.
        """
        from decimal import Decimal
        from sqlalchemy import text

        rows = db.session.execute(text("""
            SELECT r.id, r.date, r.goodx_production,
                   COALESCE(SUM(e.amount_billed), 0) AS gross,
                   COALESCE(SUM(e.credit_note), 0)  AS credit
            FROM daily_reconciliations r
            LEFT JOIN reconciliation_billing_entries e
                   ON e.reconciliation_id = r.id
            GROUP BY r.id, r.date, r.goodx_production
            ORDER BY r.date
        """)).fetchall()

        changed = []
        for rec_id, rec_date, stored, gross, credit in rows:
            net = (gross or Decimal('0')) - (credit or Decimal('0'))
            if (stored or Decimal('0')) != net:
                changed.append((rec_id, rec_date, stored, net))

        for rec_id, rec_date, stored, net in changed:
            click.echo(f'  {rec_date}: R{stored or 0:,.2f} -> R{net:,.2f}')
            db.session.execute(
                text('UPDATE daily_reconciliations SET goodx_production = :net '
                     'WHERE id = :id'),
                {'net': net, 'id': rec_id})

        db.session.commit()
        click.echo(f'Examined {len(rows)} reconciliation(s), corrected {len(changed)}.')

    @app.cli.command('backfill-report-journals')
    def backfill_report_journals_command():
        """Fill journals into turnover reports saved before autofill existed.

        Journals captured on the daily sheets only started prefilling new
        reports once that was built. Reports saved before then hold an empty
        journals list, so section 5 of the document prints blank even though
        the daily sheets have the entries.

        Only sections with no journals are touched, so anything typed by hand
        is left alone. Safe to run repeatedly.
        """
        import calendar
        from datetime import date
        from app.models import (TurnoverReport, ReconciliationBillingEntry,
                                DailyReconciliation)
        from sqlalchemy import func
        from sqlalchemy.orm.attributes import flag_modified

        changed = 0
        for report in TurnoverReport.query.order_by(TurnoverReport.year,
                                                    TurnoverReport.month).all():
            first = date(report.year, report.month, 1)
            last = date(report.year, report.month,
                        calendar.monthrange(report.year, report.month)[1])

            rows = db.session.query(
                ReconciliationBillingEntry.provider_name,
                ReconciliationBillingEntry.journal_reason,
                func.coalesce(func.sum(ReconciliationBillingEntry.journal), 0),
            ).join(
                DailyReconciliation,
                ReconciliationBillingEntry.reconciliation_id == DailyReconciliation.id
            ).filter(
                DailyReconciliation.date >= first,
                DailyReconciliation.date <= last,
                ReconciliationBillingEntry.journal > 0
            ).group_by(
                ReconciliationBillingEntry.provider_name,
                ReconciliationBillingEntry.journal_reason
            ).all()

            by_provider = {}
            for name, reason, amount in rows:
                by_provider.setdefault(name, []).append(
                    {'description': reason or 'Journal', 'amount': float(amount)})

            period = f'{calendar.month_name[report.month]} {report.year}'
            matched = set()
            for section in report.sections:
                found = by_provider.get(section.practitioner_name)
                if not found:
                    continue
                matched.add(section.practitioner_name)
                if section.journals:
                    click.echo(f'  {period}: {section.practitioner_name} already has '
                               f'journals, left alone')
                    continue
                section.journals = found
                flag_modified(section, 'journals')
                total = sum(j['amount'] for j in found)
                click.echo(f'  {period}: {section.practitioner_name} '
                           f'+{len(found)} journal(s), R{total:,.2f}')
                changed += 1

            for name in set(by_provider) - matched:
                click.echo(f'  {period}: WARNING no report section named '
                           f'"{name}" - its journals were not carried over')

        db.session.commit()
        click.echo(f'Updated {changed} section(s).')

    @app.cli.command('send-room-notifications')
    def send_room_notifications_command():
        """Send daily room assignment notifications to dental assistants."""
        from app.routes.schedule import send_daily_room_notifications
        sent = send_daily_room_notifications()
        click.echo(f'Sent {sent} room assignment notifications.')

    return app
