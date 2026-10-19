"""Report periods: weeks, months, quarters and years.

The practice's financial year runs March to February, so quarters are
Q1 March to May, Q2 June to August, Q3 September to November and Q4
December to February. Weeks stay inside their month (see month_weeks), so
every shorter period adds up exactly to the longer ones.
"""
import calendar
from datetime import date, timedelta

from app.utils.month_activity import month_weeks, week_containing

FY_START_MONTH = 3
KINDS = ('weekly', 'monthly', 'quarterly', 'yearly')
KIND_LABELS = {'weekly': 'Weekly', 'monthly': 'Monthly', 'quarterly': 'Quarterly',
               'yearly': 'Yearly'}


def _month_end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(year, month, n):
    index = year * 12 + (month - 1) + n
    return index // 12, index % 12 + 1


def fy_start_year(day):
    """The calendar year the financial year containing `day` starts in."""
    return day.year if day.month >= FY_START_MONTH else day.year - 1


def fy_label(start_year):
    return f'{start_year}/{(start_year + 1) % 100:02d}'


def quarter_of(day):
    """(financial year start, quarter number 1-4) for `day`."""
    return fy_start_year(day), ((day.month - FY_START_MONTH) % 12) // 3 + 1


def resolve(kind, day):
    """The period of the given kind that contains `day`."""
    if kind not in KINDS:
        kind = 'monthly'

    if kind == 'weekly':
        week = week_containing(day)
        start, end = week['start'], week['end']
        title = f"{calendar.month_name[week['month']]} {week['year']}, Week {week['number']}"
        shown = (week['shown_start'], week['shown_end'])
        extra = {'week': week, 'month_weeks': month_weeks(week['year'], week['month'])}
    elif kind == 'monthly':
        start = date(day.year, day.month, 1)
        end = _month_end(day.year, day.month)
        title = f'{calendar.month_name[day.month]} {day.year}'
        shown = (start, end)
        extra = {}
    elif kind == 'quarterly':
        fy, q = quarter_of(day)
        y, m = _add_months(fy, FY_START_MONTH, (q - 1) * 3)
        start = date(y, m, 1)
        ey, em = _add_months(y, m, 2)
        end = _month_end(ey, em)
        title = f'Q{q} of financial year {fy_label(fy)}'
        shown = (start, end)
        extra = {'fy': fy, 'quarter': q}
    else:
        fy = fy_start_year(day)
        start = date(fy, FY_START_MONTH, 1)
        end = _month_end(fy + 1, FY_START_MONTH - 1)
        title = f'Financial year {fy_label(fy)}'
        shown = (start, end)
        extra = {'fy': fy}

    months = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        months.append((y, m))
        y, m = _add_months(y, m, 1)

    today = date.today()
    span = f"{shown[0].strftime('%d/%m/%Y')} to {shown[1].strftime('%d/%m/%Y')}"
    if kind in ('quarterly', 'yearly'):
        span = (f"{calendar.month_name[start.month]} {start.year} to "
                f"{calendar.month_name[end.month]} {end.year}")
    return {
        'kind': kind,
        'kind_label': KIND_LABELS[kind],
        'start': start,
        'end': end,
        'shown_start': shown[0],
        'shown_end': shown[1],
        'title': title,
        'span': span,
        'months': months,
        'fy_label': f'Financial year {fy_label(fy_start_year(start))}',
        'is_current': start <= today <= end,
        'prev_day': start - timedelta(days=1),
        'next_day': end + timedelta(days=1) if end < today else None,
        **extra,
    }


def picker_options(kind, earliest):
    """Choices for the quarter and year pickers, newest first, from the
    financial year of `earliest` (the first daily sheet) to today."""
    today = date.today()
    first_fy, this_fy = fy_start_year(earliest), fy_start_year(today)
    if kind == 'yearly':
        return [{'value': date(fy, FY_START_MONTH, 1).isoformat(),
                 'label': f'Financial year {fy_label(fy)} (March {fy} to February {fy + 1})'}
                for fy in range(this_fy, first_fy - 1, -1)]
    if kind == 'quarterly':
        options = []
        for fy in range(this_fy, first_fy - 1, -1):
            for q in (4, 3, 2, 1):
                y, m = _add_months(fy, FY_START_MONTH, (q - 1) * 3)
                if date(y, m, 1) > today:
                    continue
                ey, em = _add_months(y, m, 2)
                options.append({
                    'value': date(y, m, 1).isoformat(),
                    'label': (f'Q{q} {fy_label(fy)}: {calendar.month_abbr[m]} {y} to '
                              f'{calendar.month_abbr[em]} {ey}'),
                })
        return options
    return []
