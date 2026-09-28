"""Staff leave report: every staff member's leave for a year, as a PDF.

Asked for by the Practice Manager. It is a management document, so it
includes sick leave and is marked confidential on every page.

Days are counted the way the in-app balance counts them - weekdays only,
against the year the leave starts in. The one deliberate difference is
duplicates: when the same request was submitted and approved twice, the
app counts it twice and this report counts it once, and says so.
"""
import calendar
from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether, CondPageBreak)

from app.models import LeaveRequest, LeaveDocument, User
from app.routes.leave import ANNUAL_ALLOWANCES, LEAVE_TYPES, working_days
from app.utils.turnover_pdf import _practice_logo

ACCENT = colors.HexColor('#1F5F4E')
LIGHT = colors.HexColor('#EAF2EE')
GRID = colors.HexColor('#E2E7E4')
DARK = colors.HexColor('#16211E')
MUTED = colors.HexColor('#5D6E69')
WARN_BG = colors.HexColor('#FBF1E4')
WARN_INK = colors.HexColor('#845812')

# Chart series, validated for colour-blind separation against a white page.
SERIES = [
    ('Annual', colors.HexColor('#138A68')),
    ('Sick', colors.HexColor('#C8711F')),
    ('Other', colors.HexColor('#3C6FC4')),
]

# Staff accounts that are not employees taking leave (the owner's admin
# account, the developer). Still included if they ever record leave.
NON_STAFF_ROLES = {'Super Admin'}

# BCEA s23: a medical certificate may be required for more than two
# consecutive days of sick leave.
SICK_NOTE_THRESHOLD = 2

BALANCE_TYPES = list(ANNUAL_ALLOWANCES)
TYPE_ORDER = [code for code, _label in LEAVE_TYPES]


def _d(value):
    return value.strftime('%d/%m/%Y') if value else '-'


def _span(start, end):
    if start == end:
        return _d(start)
    if start.year == end.year:
        return f"{start.strftime('%d/%m')} - {_d(end)}"
    return f'{_d(start)} - {_d(end)}'


def _text(value):
    """User-typed text made safe for the PDF.

    Escapes markup and drops characters the built-in Helvetica cannot
    draw - an emoji in a leave reason otherwise prints as a black box.
    """
    value = (value or '').strip()
    value = value.encode('cp1252', 'ignore').decode('cp1252').strip()
    return escape(value)


def _plural(n, word, plural=None):
    return f"{n} {word if n == 1 else (plural or word + 's')}"


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def build_leave_report_data(year, today):
    """Gather and work out everything the report prints."""
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)

    requests = LeaveRequest.query.filter(
        LeaveRequest.start_date >= year_start,
        LeaveRequest.start_date <= year_end,
    ).order_by(LeaveRequest.start_date, LeaveRequest.id).all()

    # Which requests have a doctor's note, without loading the files
    noted = set()
    if requests:
        noted = {rid for (rid,) in LeaveDocument.query.with_entities(
            LeaveDocument.leave_request_id).filter(
            LeaveDocument.leave_request_id.in_([r.id for r in requests])).all()}

    users = {u.id: u for u in User.query.all()}
    with_leave = {r.staff_id for r in requests}
    staff = sorted(
        (u for u in users.values()
         if u.id in with_leave
         or (u.status == 'Active' and u.role not in NON_STAFF_ROLES)),
        key=lambda u: u.full_name.lower())

    rows = []
    for r in requests:
        rows.append({
            'id': r.id,
            'staff_id': r.staff_id,
            'staff': users[r.staff_id].full_name if r.staff_id in users else f'Staff #{r.staff_id}',
            'type': r.leave_type,
            'start': r.start_date,
            'end': r.end_date,
            'days': working_days(r.start_date, r.end_date),
            'status': r.status,
            'reason': _text(r.reason),
            'manager_note': _text(r.approval_notes),
            'decided_by': users[r.approved_by].full_name if r.approved_by in users else None,
            'decided_at': r.approved_at.date() if r.approved_at else None,
            'has_note': r.id in noted,
            'requested_at': r.created_at.date() if r.created_at else None,
        })

    # Duplicates: the same person, type and dates submitted more than once.
    # The first copy stands; the rest are marked and left out of every
    # count, so nobody's leave is counted twice.
    groups = defaultdict(list)
    for r in rows:
        r['duplicate'] = False
        if r['status'] in ('Pending', 'Approved'):
            groups[(r['staff_id'], r['type'], r['start'], r['end'])].append(r)
    duplicates = [g for g in groups.values() if len(g) > 1]
    for group in duplicates:
        for r in group[1:]:
            r['duplicate'] = True

    approved = [r for r in rows if r['status'] == 'Approved' and not r['duplicate']]
    pending = [r for r in rows if r['status'] == 'Pending']
    rejected = [r for r in rows if r['status'] == 'Rejected']

    # ---- per staff balances
    balances = []
    for u in staff:
        mine = [r for r in approved if r['staff_id'] == u.id]
        used = defaultdict(int)
        for r in mine:
            used[r['type']] += r['days']
        app_extra = defaultdict(int)
        for r in rows:
            if r['staff_id'] == u.id and r['duplicate'] and r['status'] == 'Approved':
                app_extra[r['type']] += r['days']
        entry = {
            'user': u,
            'types': {},
            'app_extra': dict(app_extra),
            'other': sum(d for t, d in used.items() if t not in ANNUAL_ALLOWANCES),
            'total': sum(used.values()),
            'pending_days': sum(r['days'] for r in pending
                                if r['staff_id'] == u.id and not r['duplicate']),
            'requests': [r for r in rows if r['staff_id'] == u.id],
        }
        for t, allowance in ANNUAL_ALLOWANCES.items():
            entry['types'][t] = {
                'used': used.get(t, 0),
                'allowance': allowance,
                'remaining': max(0, allowance - used.get(t, 0)),
                'over': max(0, used.get(t, 0) - allowance),
                'app_shows': max(0, allowance - used.get(t, 0) - app_extra.get(t, 0)),
            }
        balances.append(entry)

    # ---- by type, in the order the request form lists them
    by_type = []
    seen_types = {r['type'] for r in rows}
    for t in TYPE_ORDER + sorted(seen_types - set(TYPE_ORDER)):
        if t not in seen_types:
            continue
        of_type = [r for r in rows if r['type'] == t and not r['duplicate']]
        by_type.append({
            'type': t,
            'approved': sum(1 for r in of_type if r['status'] == 'Approved'),
            'approved_days': sum(r['days'] for r in of_type if r['status'] == 'Approved'),
            'pending': sum(1 for r in of_type if r['status'] == 'Pending'),
            'pending_days': sum(r['days'] for r in of_type if r['status'] == 'Pending'),
            'rejected': sum(1 for r in of_type if r['status'] == 'Rejected'),
        })

    # ---- month by month, each leave day placed in the month it falls in
    monthly = {m: {'Annual': 0, 'Sick': 0, 'Other': 0} for m in range(1, 13)}
    away_on = defaultdict(set)   # date -> staff names on approved leave
    for r in approved:
        series = r['type'] if r['type'] in ('Annual', 'Sick') else 'Other'
        day = r['start']
        while day <= r['end']:
            if day.weekday() < 5 and year_start <= day <= year_end:
                monthly[day.month][series] += 1
                away_on[day].add(r['staff'])
            day += timedelta(days=1)

    overlaps = [(d, sorted(names)) for d, names in sorted(away_on.items())
                if len(names) >= 2]

    is_current = year == today.year
    as_at = today if is_current else year_end

    data = {
        'year': year,
        'today': today,
        'as_at': as_at,
        'is_current': is_current,
        'period_start': year_start,
        'period_end': year_end,
        'staff': staff,
        'rows': rows,
        'approved': approved,
        'pending': pending,
        'rejected': rejected,
        'balances': balances,
        'by_type': by_type,
        'monthly': monthly,
        'overlaps': overlaps,
        'duplicates': duplicates,
        'upcoming': sorted((r for r in approved if r['end'] >= today),
                           key=lambda r: (r['start'], r['staff'])),
        'approved_days': sum(r['days'] for r in approved),
        'pending_days': sum(r['days'] for r in pending if not r['duplicate']),
        'pending_distinct': [r for r in pending if not r['duplicate']],
    }
    data['attention'] = _attention_points(data)
    data['summary_text'] = _summary_text(data)
    return data


def _attention_points(data):
    """Plain statements of anything a manager should act on or know."""
    points = []
    today = data['today']

    overdue = [r for r in data['pending_distinct'] if r['start'] <= today]
    if overdue:
        names = ', '.join(sorted({r['staff'] for r in overdue}))
        points.append((
            'Decisions outstanding on leave that has already started',
            f"{_plural(len(overdue), 'request')} ({names}) "
            f"{'is' if len(overdue) == 1 else 'are'} still pending although the first day "
            f"of leave has arrived or passed. Approve or decline "
            f"{'it' if len(overdue) == 1 else 'them'} so the balances are correct."))

    if data['duplicates']:
        lines = []
        extra = 0
        for group in data['duplicates']:
            first = group[0]
            extra += len(group) - 1
            statuses = sorted({r['status'] for r in group})
            lines.append(f"{first['staff']}: {first['type'].lower()} leave "
                         f"{_span(first['start'], first['end'])} submitted {len(group)} times "
                         f"({', '.join(statuses).lower()})")
        affected = []
        for b in data['balances']:
            for t, days in b['app_extra'].items():
                info = b['types'].get(t)
                if info:
                    affected.append(f"{b['user'].full_name} has {info['remaining']} "
                                    f"{t.lower()} days left, but StaffTrack shows "
                                    f"{info['app_shows']}")
        tail = ' Each request is counted once in this report.'
        if affected:
            tail += (' StaffTrack itself still counts the approved copies twice, so '
                     'until they are removed: ' + '; '.join(affected) + '.')
        points.append(('The same request submitted more than once',
                       '; '.join(lines) + f'. That is {_plural(extra, "extra copy", "extra copies")}.'
                       + tail))

    missing = [r for r in data['approved']
               if r['type'] == 'Sick' and r['days'] > SICK_NOTE_THRESHOLD and not r['has_note']]
    if missing:
        detail = '; '.join(f"{r['staff']} ({_span(r['start'], r['end'])}, "
                           f"{_plural(r['days'], 'day')})" for r in missing)
        points.append((
            "Sick leave of more than two days with no doctor's note on file",
            f"{detail}. Under the BCEA a medical certificate may be required for sick leave "
            f"longer than two consecutive days."))

    over, near = [], []
    for b in data['balances']:
        for t in BALANCE_TYPES:
            info = b['types'][t]
            name = b['user'].full_name
            if info['over']:
                over.append(f"{name} - {t.lower()} leave, {info['used']} used of "
                            f"{info['allowance']} ({info['over']} over)")
            elif info['used'] and info['remaining'] == 0:
                over.append(f"{name} - {t.lower()} leave, all {info['allowance']} days used")
            elif info['used'] and info['remaining'] <= max(1, info['allowance'] // 5):
                near.append(f"{name} - {t.lower()} leave, {info['remaining']} of "
                            f"{info['allowance']} days left")
    if over:
        points.append(('Allowance used up or exceeded', '; '.join(over) + '.'))
    if near:
        points.append(('Close to the allowance', '; '.join(near) + '.'))

    no_annual = [b['user'].full_name for b in data['balances']
                 if b['types']['Annual']['used'] == 0
                 and b['user'].role not in NON_STAFF_ROLES]
    if no_annual:
        when = f"so far in {data['year']}" if data['is_current'] else f"in {data['year']}"
        points.append((
            'No annual leave taken',
            f"{', '.join(no_annual)} {'has' if len(no_annual) == 1 else 'have'} not taken any "
            f"approved annual leave {when}. Annual leave must be granted within six months "
            f"of the end of the leave cycle, so it is worth planning it now rather than "
            f"having it fall due at once."))

    if data['overlaps']:
        most = max(len(names) for _d_, names in data['overlaps'])
        points.append((
            'Days with more than one person away',
            f"{_plural(len(data['overlaps']), 'working day')} had two or more staff on "
            f"approved leave at the same time (at most {most} on one day). They are "
            f"listed in section 5."))

    return points


def _summary_text(data):
    period = (f"from 1 January to {_d(data['as_at'])}" if data['is_current']
              else f"for the whole of {data['year']}")
    parts = [
        f"This report covers leave for all {_plural(len(data['staff']), 'staff member')} "
        f"{period}. {_plural(len(data['approved']), 'leave request')} "
        f"{'was' if len(data['approved']) == 1 else 'were'} approved, adding up to "
        f"<b>{_plural(data['approved_days'], 'working day')}</b> of leave."
    ]

    if data['approved_days']:
        shares = []
        for t in data['by_type']:
            if t['approved_days']:
                pct = t['approved_days'] / data['approved_days'] * 100
                shares.append(f"{t['type'].lower()} leave {t['approved_days']} "
                              f"({pct:.0f}%)")
        parts.append('By type: ' + ', '.join(shares) + '.')

        top = max(data['balances'], key=lambda b: b['total'])
        if top['total']:
            parts.append(f"The most leave was taken by {top['user'].full_name} "
                         f"({_plural(top['total'], 'day')}).")

    if data['pending_distinct']:
        n = len(data['pending_distinct'])
        parts.append(f"{_plural(n, 'request')} covering "
                     f"{_plural(data['pending_days'], 'day')} "
                     f"{'is' if n == 1 else 'are'} waiting for a decision.")
    if data['rejected']:
        parts.append(f"{_plural(len(data['rejected']), 'request')} "
                     f"{'was' if len(data['rejected']) == 1 else 'were'} declined.")
    return ' '.join(parts)


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

class _NumberedCanvas(pdf_canvas.Canvas):
    """Adds 'Page x of y' and the confidentiality line to every page."""

    footer_left = ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        width, _height = A4
        self.saveState()
        self.setStrokeColor(GRID)
        self.setLineWidth(0.5)
        self.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
        self.setFont('Helvetica', 7.5)
        self.setFillColor(MUTED)
        self.drawString(18 * mm, 9 * mm, self.footer_left)
        self.drawRightString(width - 18 * mm, 9 * mm,
                             f'Page {self._pageNumber} of {total}')
        self.restoreState()


def build_leave_report_pdf(data, generated_by=''):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            topMargin=16 * mm, bottomMargin=20 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            title=f"Staff Leave Report {data['year']}",
                            author='Smilez Dental Surgery')
    content_w = A4[0] - 36 * mm
    styles = getSampleStyleSheet()

    title = ParagraphStyle('LTitle', parent=styles['Heading1'], fontSize=19,
                           textColor=ACCENT, spaceAfter=2, leading=23)
    subtitle = ParagraphStyle('LSub', parent=styles['Normal'], fontSize=11,
                              textColor=DARK, spaceAfter=1, leading=14)
    meta = ParagraphStyle('LMeta', parent=styles['Normal'], fontSize=8.5,
                          textColor=MUTED, leading=11)
    section = ParagraphStyle('LSection', parent=styles['Heading2'], fontSize=13,
                             textColor=DARK, spaceBefore=14, spaceAfter=5)
    sub = ParagraphStyle('LSubSection', parent=styles['Heading3'], fontSize=10.5,
                         fontName='Helvetica-Bold', textColor=ACCENT,
                         spaceBefore=10, spaceAfter=3)
    body = ParagraphStyle('LBody', parent=styles['Normal'], fontSize=9,
                          textColor=colors.HexColor('#3A4843'), leading=13, spaceAfter=4)
    note = ParagraphStyle('LNote', parent=styles['Normal'], fontSize=7.5,
                          textColor=MUTED, leading=10, spaceAfter=3)
    cell = ParagraphStyle('LCell', parent=styles['Normal'], fontSize=7.5, leading=9.5,
                          textColor=DARK)
    cell_muted = ParagraphStyle('LCellMuted', parent=cell, textColor=MUTED)
    point_head = ParagraphStyle('LPointHead', parent=body, fontName='Helvetica-Bold',
                                textColor=WARN_INK, spaceAfter=1)

    def grid_table(rows, widths, align_right=(), bold_last=False, header=True,
                   font_size=8):
        t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), font_size),
            ('TEXTCOLOR', (0, 0), (-1, -1), DARK),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, -1), 0.4, GRID),
        ]
        if header:
            style += [
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BACKGROUND', (0, 0), (-1, 0), LIGHT),
                ('TEXTCOLOR', (0, 0), (-1, 0), ACCENT),
                ('LINEBELOW', (0, 0), (-1, 0), 0.8, ACCENT),
            ]
        for c in align_right:
            style.append(('ALIGN', (c, 0), (c, -1), 'RIGHT'))
        if bold_last:
            style += [('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                      ('BACKGROUND', (0, -1), (-1, -1), LIGHT)]
        t.setStyle(TableStyle(style))
        return t

    year = data['year']
    el = []

    # ---------------------------------------------------------- letterhead
    logo = _practice_logo()
    if logo is not None:
        el += [logo, Spacer(1, 6)]
    el.append(Paragraph('Smilez Dental Surgery', title))
    el.append(Paragraph(f'Staff Leave Report {year}', subtitle))
    period = (f"1 January {year} to {_d(data['as_at'])} (year to date)" if data['is_current']
              else f"1 January to 31 December {year}")
    el.append(Paragraph(f'Reporting period: <b>{period}</b>', subtitle))
    generated = f"Generated on {_d(data['today'])}"
    if generated_by:
        generated += f" by {escape(generated_by)}"
    el.append(Paragraph(generated, meta))
    el.append(Spacer(1, 5))
    el.append(HRFlowable(width='100%', thickness=1, color=ACCENT))
    el.append(Spacer(1, 5))
    el.append(Paragraph(
        '<b>Confidential.</b> This report contains sick leave and other personal leave '
        'records. It is intended for practice management only and should not be '
        'circulated to staff.', note))

    # ---------------------------------------------------------- 1. summary
    el.append(Paragraph('1. Summary', section))
    tiles = [
        (str(len(data['staff'])), 'Staff on record'),
        (str(data['approved_days']), 'Working days of leave taken'),
        (str(len(data['approved'])), 'Requests approved'),
        (str(len(data['pending_distinct'])), 'Awaiting a decision'),
    ]
    tile_num = ParagraphStyle('TileNum', parent=body, fontName='Helvetica-Bold',
                              fontSize=20, leading=23, textColor=ACCENT, spaceAfter=0)
    tile_lbl = ParagraphStyle('TileLbl', parent=note, fontSize=7.5, spaceAfter=0)
    tile_table = Table([[[Paragraph(n, tile_num), Paragraph(l, tile_lbl)] for n, l in tiles]],
                       colWidths=[content_w / 4] * 4)
    tile_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
        ('LINEAFTER', (0, 0), (-2, -1), 2, colors.white),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    el += [tile_table, Spacer(1, 7), Paragraph(data['summary_text'], body)]

    # ---------------------------------------------------------- 2. attention
    el.append(Paragraph('2. Needs Attention', section))
    if data['attention']:
        box_rows = [[[Paragraph(escape(h), point_head), Paragraph(escape(t), body)]]
                    for h, t in data['attention']]
        box = Table(box_rows, colWidths=[content_w])
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), WARN_BG),
            ('LINEBEFORE', (0, 0), (0, -1), 2.5, WARN_INK),
            ('LINEBELOW', (0, 0), (-1, -2), 0.6, colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
            ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ]))
        el.append(box)
    else:
        el.append(Paragraph('Nothing needs attention: no overdue decisions, duplicate '
                            'requests, missing sick notes or exhausted allowances.', body))

    # ---------------------------------------------------------- 3. balances
    bal_head = [
        Paragraph(f'3. Leave Balances by Staff Member ({year})', section),
        Paragraph('Working days of approved leave used against each allowance, with the days '
                  'left shown in brackets. Other covers study, unpaid, parental and any other '
                  'leave without an annual allowance.', body)]
    bal_rows = [['Staff member', 'Role', 'Started', 'Annual\nused (left)',
                 'Sick\nused (left)', 'Family resp.\nused (left)', 'Other', 'Total', 'Pending']]
    flagged = []
    for i, b in enumerate(data['balances'], start=1):
        row = [Paragraph(escape(b['user'].full_name), cell),
               Paragraph(escape(b['user'].role or '-'), cell_muted),
               _d(b['user'].start_date)]
        for t in BALANCE_TYPES:
            info = b['types'][t]
            text = f"{info['used']} ({info['remaining']})"
            if info['over']:
                text = f"{info['used']} (+{info['over']} over)"
            if info['over'] or (info['used'] and info['remaining'] == 0):
                flagged.append((i, 3 + BALANCE_TYPES.index(t)))
            row.append(text)
        row += [str(b['other'] or '-'), str(b['total']),
                str(b['pending_days']) if b['pending_days'] else '-']
        bal_rows.append(row)
    total_row = ['Total', '', '']
    for t in BALANCE_TYPES:
        total_row.append(str(sum(b['types'][t]['used'] for b in data['balances'])))
    total_row += [str(sum(b['other'] for b in data['balances'])),
                  str(sum(b['total'] for b in data['balances'])),
                  str(sum(b['pending_days'] for b in data['balances']))]
    bal_rows.append(total_row)
    widths = [36 * mm, 24 * mm, 17 * mm, 18 * mm, 18 * mm, 19 * mm, 12 * mm, 13 * mm, 17 * mm]
    bal = grid_table(bal_rows, widths, align_right=range(3, 9), bold_last=True, font_size=7.5)
    extra = []
    for r, c in flagged:
        extra += [('BACKGROUND', (c, r), (c, r), WARN_BG),
                  ('TEXTCOLOR', (c, r), (c, r), WARN_INK),
                  ('FONTNAME', (c, r), (c, r), 'Helvetica-Bold')]
    bal.setStyle(TableStyle(extra))
    el.append(KeepTogether(bal_head + [bal]))
    allowances = ', '.join(f'{t.lower()} {n} days' for t, n in ANNUAL_ALLOWANCES.items())
    dup_note = (' Leave submitted and approved twice is counted once here; see section 2.'
                if any(b['app_extra'] for b in data['balances']) else '')
    el.append(Paragraph(
        f'Allowances per year: {allowances}. Highlighted cells are allowances used up or '
        f'exceeded. Pending days are not deducted until approved.{dup_note}', note))

    # ---------------------------------------------------------- 4. by type
    el.append(Paragraph('4. Leave by Type', section))
    if data['by_type']:
        type_rows = [['Leave type', 'Approved', 'Days taken', 'Pending', 'Pending days', 'Declined']]
        for t in data['by_type']:
            type_rows.append([t['type'], t['approved'], t['approved_days'], t['pending'],
                              t['pending_days'], t['rejected']])
        type_rows.append(['Total',
                          sum(t['approved'] for t in data['by_type']),
                          sum(t['approved_days'] for t in data['by_type']),
                          sum(t['pending'] for t in data['by_type']),
                          sum(t['pending_days'] for t in data['by_type']),
                          sum(t['rejected'] for t in data['by_type'])])
        type_rows = [[str(c) for c in r] for r in type_rows]
        el.append(grid_table(type_rows, [54 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm],
                             align_right=range(1, 6), bold_last=True))
    else:
        el.append(Paragraph(f'No leave was requested in {year}.', body))

    # ---------------------------------------------------------- 5. monthly
    month_rows = [['', *[calendar.month_abbr[m] for m in range(1, 13)], 'Total']]
    for name, _colour in SERIES:
        values = [data['monthly'][m][name] for m in range(1, 13)]
        month_rows.append([name, *[str(v) if v else '-' for v in values], str(sum(values))])
    totals = [sum(data['monthly'][m].values()) for m in range(1, 13)]
    month_rows.append(['Total', *[str(v) if v else '-' for v in totals], str(sum(totals))])
    el.append(KeepTogether([
        Paragraph('5. Month by Month', section),
        Paragraph('Working days of approved leave in each month, split by type. A request '
                  'that runs across two months is counted in the month each day falls in.',
                  body),
        _monthly_chart(data['monthly'], content_w),
        grid_table(month_rows, [16 * mm] + [11.5 * mm] * 12 + [20 * mm],
                   align_right=range(1, 14), bold_last=True, font_size=7.5)]))

    if data['overlaps']:
        el.append(Paragraph('Days with more than one person away', sub))
        ov_rows = [['Date', 'Day', 'Away', 'Staff on leave']]
        for d, names in data['overlaps']:
            ov_rows.append([_d(d), d.strftime('%A'), str(len(names)),
                            Paragraph(escape(', '.join(names)), cell)])
        el.append(grid_table(ov_rows, [24 * mm, 22 * mm, 14 * mm, content_w - 60 * mm],
                             align_right=(2,)))

    # ---------------------------------------------------------- 6. upcoming
    up_head = Paragraph('6. Approved Leave Coming Up', section)
    if data['upcoming']:
        up_rows = [['Staff member', 'Type', 'Dates', 'Days', 'Approved by']]
        for r in data['upcoming']:
            up_rows.append([Paragraph(escape(r['staff']), cell), r['type'],
                            _span(r['start'], r['end']), str(r['days']),
                            Paragraph(escape(r['decided_by'] or '-'), cell_muted)])
        el.append(KeepTogether([up_head, grid_table(
            up_rows, [42 * mm, 34 * mm, 44 * mm, 14 * mm, content_w - 134 * mm],
            align_right=(3,))]))
    else:
        el += [up_head, Paragraph(f"No approved leave from {_d(data['today'])} onwards.", body)]

    # ---------------------------------------------------------- 7. pending
    pend_head = Paragraph('7. Awaiting a Decision', section)
    if data['pending']:
        pend_rows = [['Staff member', 'Type', 'Dates', 'Days', 'Requested', 'Reason']]
        for r in sorted(data['pending'], key=lambda r: (r['start'], r['staff'])):
            kind = escape(r['type'])
            if r['duplicate']:
                kind += "<br/><font color='#845812'>duplicate</font>"
            pend_rows.append([Paragraph(escape(r['staff']), cell), Paragraph(kind, cell),
                              _span(r['start'], r['end']), str(r['days']),
                              _d(r['requested_at']),
                              Paragraph(r['reason'] or '-', cell_muted)])
        pend = grid_table(pend_rows, [44 * mm, 22 * mm, 30 * mm, 11 * mm, 20 * mm,
                                      content_w - 127 * mm], align_right=(3,))
        late = [('TEXTCOLOR', (2, i), (2, i), WARN_INK)
                for i, r in enumerate(sorted(data['pending'],
                                             key=lambda r: (r['start'], r['staff'])), start=1)
                if r['start'] <= data['today']]
        pend.setStyle(TableStyle(late))
        el.append(KeepTogether([pend_head, pend]))
        if late:
            el.append(Paragraph('Dates in amber have already arrived or passed.', note))
    else:
        el += [pend_head, Paragraph('No requests are waiting for a decision.', body)]

    # ---------------------------------------------------------- 8. records
    el.append(CondPageBreak(70 * mm))
    el.append(Paragraph('8. Individual Leave Records', section))
    el.append(Paragraph(
        f'Every leave request made in {year}, per staff member, including declined and '
        f'pending requests. Only approved leave counts towards the days used.', body))
    rec_widths = [29 * mm, 24 * mm, 10 * mm, 17 * mm, 27 * mm, 15 * mm, content_w - 122 * mm]
    for b in data['balances']:
        u = b['user']
        heading = Paragraph(
            f"{escape(u.full_name)} <font size=8 color='#5D6E69'>&nbsp;&nbsp;"
            f"{escape(u.role or '')} &middot; {_plural(b['total'], 'day')} taken</font>", sub)
        if not b['requests']:
            el.append(KeepTogether([heading, Paragraph(f'No leave requests in {year}.', body)]))
            continue
        rec_rows = [['Dates', 'Type', 'Days', 'Status', 'Decided by', 'Sick note', 'Reason / notes']]
        status_cells = []
        for i, r in enumerate(b['requests'], start=1):
            notes = r['reason']
            if r['manager_note']:
                notes += ('<br/>' if notes else '') + \
                    f"<font color='#5D6E69'><i>Manager: {r['manager_note']}</i></font>"
            decided = r['decided_by'] or '-'
            if r['decided_at']:
                decided += f"<br/><font color='#5D6E69'>{_d(r['decided_at'])}</font>"
            dr_note = ('Yes' if r['has_note'] else 'No') if r['type'] == 'Sick' else '-'
            status = r['status']
            if r['duplicate']:
                status = Paragraph(f"{r['status']}<br/><font color='#845812'>duplicate, "
                                   f"not counted</font>", cell)
            rec_rows.append([_span(r['start'], r['end']), Paragraph(escape(r['type']), cell),
                             '-' if r['duplicate'] else str(r['days']), status,
                             Paragraph(decided if r['decided_by'] else '-', cell),
                             dr_note, Paragraph(notes or '-', cell)])
            colour = {'Approved': ACCENT, 'Pending': WARN_INK,
                      'Rejected': colors.HexColor('#9E3232')}.get(r['status'], DARK)
            status_cells.append(('TEXTCOLOR', (3, i), (3, i), colour))
        t = grid_table(rec_rows, rec_widths, align_right=(2,), font_size=7.5)
        t.setStyle(TableStyle(status_cells))
        el.append(KeepTogether([heading, t]) if len(rec_rows) <= 12 else heading)
        if len(rec_rows) > 12:
            el.append(t)

    # ---------------------------------------------------------- method
    el.append(Paragraph('How the figures are worked out', section))
    for text in (
        'Leave days are working days, Monday to Friday. Weekends inside a leave period are '
        'not counted. Public holidays are not deducted, so a request that spans one counts '
        'that day as leave.',
        'A request belongs to the year it starts in, the same rule the balance on each '
        'staff member\'s Leave page uses. The only difference: if the same request was '
        'submitted more than once, this report counts it once, while the in-app balance '
        'currently counts every copy.',
        f"Sick leave under the BCEA is 30 days over a three-year cycle. StaffTrack shows it "
        f"as {ANNUAL_ALLOWANCES['Sick']} days a year - one third of the cycle - so it can be "
        f"tracked within a single year.",
        'Declined requests are listed for the record but never count towards days used. '
        'Pending requests are shown separately and are only deducted once approved.',
    ):
        el.append(Paragraph(f'&bull;&nbsp; {text}', body))

    footer = f"Smilez Dental Surgery  ·  Staff Leave Report {year}  ·  Confidential"

    class _Canvas(_NumberedCanvas):
        footer_left = footer

    doc.build(el, canvasmaker=_Canvas)
    buffer.seek(0)
    return buffer


def _monthly_chart(monthly, width):
    """Stacked bars of leave days per month. One axis, three series, legend."""
    height = 62 * mm
    drawing = Drawing(width, height)

    chart = VerticalBarChart()
    chart.x, chart.y = 22, 16
    chart.width, chart.height = width - 26, height - 40
    chart.data = [[monthly[m][name] for m in range(1, 13)] for name, _c in SERIES]
    chart.categoryAxis.categoryNames = [calendar.month_abbr[m] for m in range(1, 13)]
    chart.categoryAxis.style = 'stacked'
    chart.categoryAxis.labels.fontName = 'Helvetica'
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fillColor = MUTED
    chart.categoryAxis.strokeColor = GRID
    chart.categoryAxis.visibleTicks = False

    peak = max((sum(monthly[m].values()) for m in range(1, 13)), default=0)
    step = 1 if peak <= 6 else 2 if peak <= 12 else 5 if peak <= 30 else 10
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(step * 2, ((peak // step) + 1) * step)
    chart.valueAxis.valueStep = step
    chart.valueAxis.labels.fontName = 'Helvetica'
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = colors.white
    chart.valueAxis.visibleTicks = False
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.gridStrokeColor = GRID
    chart.valueAxis.gridStrokeWidth = 0.4

    chart.barWidth = 6
    chart.groupSpacing = 8
    for i, (_name, colour) in enumerate(SERIES):
        chart.bars[i].fillColor = colour
        chart.bars[i].strokeColor = colors.white   # surface gap between segments
        chart.bars[i].strokeWidth = 1
    drawing.add(chart)

    legend = Legend()
    legend.x, legend.y = 22, height - 6
    legend.fontName = 'Helvetica'
    legend.alignment = 'right'
    legend.columnMaximum = 1
    legend.deltax = 62
    legend.dx, legend.dy = 7, 7
    legend.fontSize = 7.5
    legend.fillColor = DARK
    legend.strokeColor = None
    legend.colorNamePairs = [(c, f'{n} leave' if n != 'Other' else 'Other leave')
                             for n, c in SERIES]
    drawing.add(legend)
    return drawing
