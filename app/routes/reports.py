"""Financial Reports: analytics and the turnover report in one place, for
a week, month, quarter or financial year, on screen or as a PDF."""
from datetime import date, timedelta

from flask import Blueprint, render_template, request, send_file
from flask_login import login_required, current_user

from app.routes.reconciliation import finance_access_required
from app.utils.audit import log_audit
from app.utils.financial_periods import KINDS, KIND_LABELS, picker_options

bp = Blueprint('reports', __name__, url_prefix='/financial-reports')


def _requested():
    """The kind of report and a day inside the period asked for.

    `?kind=monthly&on=2026-09-15` picks the period holding that date. Any
    date in the period will do. `?month=2026-09` (from the month picker)
    is also understood. Without a date it's the period holding yesterday,
    so the first morning of a new week or month opens on the one that has
    just finished rather than an empty one."""
    kind = request.args.get('kind', 'monthly')
    if kind not in KINDS:
        kind = 'monthly'
    today = date.today()
    day = today - timedelta(days=1)
    month = request.args.get('month', '')
    if month:
        try:
            y, m = (int(x) for x in month.split('-'))
            day = date(y, m, 1)
            if (y, m) == (today.year, today.month):
                day = max(day, today - timedelta(days=1))
        except ValueError:
            pass
    else:
        try:
            day = date.fromisoformat(request.args.get('on', ''))
        except ValueError:
            pass
    return kind, min(day, today)


@bp.route('/')
@login_required
@finance_access_required
def index():
    from app.utils.financial_report import build_report

    kind, day = _requested()
    report = build_report(kind, day)
    return render_template('reports/index.html',
                           r=report,
                           p=report['period'],
                           kinds=KIND_LABELS,
                           today=date.today(),
                           options=picker_options(kind, report['earliest']))


@bp.route('/pdf')
@login_required
@finance_access_required
def pdf():
    from app.utils.financial_pdf import build_financial_pdf
    from app.utils.financial_report import build_report

    kind, day = _requested()
    report = build_report(kind, day)
    buffer = build_financial_pdf(report, generated_by=current_user.full_name)
    period = report['period']
    log_audit('Downloaded Financial Report', 'FinancialReport', None,
              {'kind': kind, 'period': period['title']})
    slug = period['title'].lower().replace(',', '').replace('/', '-').replace(' ', '_')
    return send_file(buffer, as_attachment=True,
                     download_name=f'financial_report_{slug}.pdf',
                     mimetype='application/pdf')
