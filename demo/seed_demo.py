"""Build the demo database: a fictional practice with fake staff, patients,
leave, KPI scores and daily reconciliation sheets.

    python demo/seed_demo.py      # (re)build instance/demo/demo.db
    python demo/run_demo.py       # serve it on http://127.0.0.1:5050

Nothing here comes from the real practice. Every name, patient, amount and
date is generated, and the script refuses to run unless the app is pointed
at the demo SQLite file, so it can never write to the live database.

Data runs from 1 January of the current year up to yesterday, so the demo
always looks current. The same seed gives the same data every time.

Daily sheets are submitted through the real reconciliation route, so every
stored total is worked out by the same code as a real sheet.
"""
import json
import os
import random
import sys
import warnings
from collections import defaultdict
from datetime import date, datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_env  # noqa: E402  must run before anything imports app

demo_env.configure()
warnings.filterwarnings('ignore', message='.*Decimal objects natively.*')

from app import create_app, db  # noqa: E402
from app.models import (User, LeaveRequest, KPICategory, RoleKPI, KPIScore,  # noqa: E402
                        PerformanceEvent, Notification, Task, Announcement,
                        DailyReconciliation, PatientFlow, AuditLog)
from app.routes.reconciliation import CREDIT_NOTE_REASONS, JOURNAL_REASONS  # noqa: E402
from kpi_definitions import KPI_DEFINITIONS  # noqa: E402

rng = random.Random(20260101)
TODAY = date.today()
START = date(TODAY.year, 1, 1) if TODAY.month >= 3 else date(TODAY.year - 1, 7, 1)
PASSWORD = 'demo1234'
EMAIL_DOMAIN = 'brightwater-demo.example'


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------

STAFF = [
    # key, username, full name, role, start date
    ('owner', 'demo', 'Dr. Ayanda Mthembu', 'Super Admin', date(2017, 3, 1)),
    ('pm', 'naledi', 'Dr. Naledi Dube', 'Practice Manager', date(2019, 8, 5)),
    ('dentist', 'kabelo', 'Dr. Kabelo Molefe', 'Dentist', date(2021, 2, 1)),
    ('billing1', 'lindiwe', 'Lindiwe Zulu', 'Billing', date(2020, 6, 15)),
    ('billing2', 'thandeka', 'Thandeka Radebe', 'Billing', date(START.year, 3, 2)),
    ('reception', 'palesa', 'Palesa Mahlangu', 'Receptionist', date(2022, 1, 10)),
    ('da1', 'nomsa', 'Nomsa Shabalala', 'Dental Assistant', date(2018, 4, 3)),
    ('da2', 'refilwe', 'Refilwe Sithole', 'Dental Assistant', date(2023, 5, 2)),
    ('da3', 'andile', 'Andile Cele', 'Dental Assistant', date(2024, 9, 16)),
    ('cleaner', 'grace', 'Grace Mabuza', 'Cleaner', date(2019, 11, 4)),
]

# Practitioners who bill: typical patients per day and the days they work
PRACTITIONERS = {
    'owner': {'per_day': 6.5, 'weekdays': {0, 1, 2, 3, 4}},
    'dentist': {'per_day': 5.5, 'weekdays': {0, 1, 2, 3, 4}},
    'pm': {'per_day': 3.5, 'weekdays': {0, 2, 4}},   # practises part-time
}

FIRST_NAMES = [
    'Thabo', 'Sizwe', 'Mpho', 'Lerato', 'Zodwa', 'Johan', 'Annelie', 'Pieter', 'Michelle',
    'Kagiso', 'Nandi', 'Bongani', 'Ayesha', 'Fatima', 'Yusuf', 'Precious', 'Tshepo',
    'Neo', 'Karabo', 'Lwazi', 'Sibusiso', 'Ntombi', 'Hendrik', 'Elize', 'Marius',
    'Charlene', 'Desmond', 'Gugu', 'Themba', 'Busisiwe', 'Siyabonga', 'Dineo', 'Keitumetse',
    'Rorisang', 'Lebo', 'Zanele', 'Mandla', 'Nokuthula', 'Jabulani', 'Hlengiwe', 'Priya',
    'Kevin', 'Shireen', 'Wandile', 'Tumelo', 'Onalenna', 'Phindile', 'Musa', 'Ruan',
    'Carmen', 'Dumisani', 'Nolwazi', 'Tebogo', 'Boitumelo', 'Vusi', 'Amahle', 'Liam',
    'Ethan', 'Olivia', 'Mia', 'Kamogelo', 'Ofentse', 'Rethabile', 'Zinhle', 'Simphiwe',
]
SURNAMES = [
    'Mokoena', 'Botha', 'Naidoo', 'Pillay', 'Van Wyk', 'Mahlaba', 'Tshabalala', 'Mabaso',
    'Ngcobo', 'Mkhize', 'Govender', 'Pretorius', 'Du Plessis', 'Ramaphosa', 'Sebola',
    'Mashaba', 'Letsoalo', 'Moloi', 'Nel', 'Venter', 'Coetzee', 'Maseko', 'Mazibuko',
    'Hendricks', 'Adams', 'Petersen', 'Mabena', 'Mtshali', 'Ntuli', 'Gumede', 'Kubheka',
    'Makgoba', 'Rampedi', 'Morake', 'Seabi', 'Phiri', 'Banda', 'Kruger', 'Smit', 'Jacobs',
    'Mathebula', 'Baloyi', 'Chauke', 'Rikhotso', 'Netshitenzhe', 'Mudau', 'Ramovha',
    'Tau', 'Modise', 'Kekana', 'Sono', 'Lekganyane', 'Bhengu', 'Zwide', 'Majola',
]
MEDICAL_AIDS = [
    # name, share of patients, weekday ERA is usually paid
    ('Private', 30, None),
    ('Discovery Health', 22, 1),
    ('Bonitas', 12, 2),
    ('GEMS', 10, 4),
    ('Momentum Health', 8, 0),
    ('Medshield', 6, 3),
    ('Bestmed', 5, 1),
    ('Polmed', 4, 4),
    ('Fedhealth', 3, 2),
]
TREATMENTS = [
    # weight, low, high
    (24, 420, 690),     # consultation & exam
    (16, 640, 980),     # scale and polish
    (18, 820, 1950),    # fillings
    (10, 760, 1450),    # extractions
    (12, 290, 560),     # x-rays
    (5, 3800, 7600),    # root canal
    (3, 6400, 11200),   # crown
    (3, 3400, 5600),    # whitening
    (3, 4300, 9100),    # dentures
    (6, 880, 1560),     # orthodontic adjustment
]
EXPENSES = [
    ('Cleaning supplies', 120, 480),
    ('Courier to dental lab', 90, 260),
    ('Milk, tea and sugar for the staff kitchen', 60, 180),
    ('Stationery and printer paper', 80, 340),
    ('Parking for lab collection', 30, 70),
    ('Gloves and masks top-up', 210, 690),
    ('Plumber - staff toilet', 450, 1250),
]


def money(value):
    return f'{value:.2f}'


def price(low, high):
    """A tariff-looking amount: whole rand plus tens of cents."""
    return round(rng.uniform(low, high), 1)


# --------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------

def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def public_holidays(year):
    fixed = [(1, 1), (3, 21), (4, 27), (5, 1), (6, 16), (8, 9), (9, 24),
             (12, 16), (12, 25), (12, 26)]
    days = {date(year, m, d) for m, d in fixed}
    e = easter(year)
    days |= {e - timedelta(days=2), e + timedelta(days=1)}
    days |= {d + timedelta(days=1) for d in list(days) if d.weekday() == 6}
    return days


HOLIDAYS = public_holidays(START.year) | public_holidays(START.year + 1)


def is_open(d):
    if d.weekday() == 6 or d in HOLIDAYS:
        return False
    if (d.month == 12 and d.day >= 22) or (d.month == 1 and d.day <= 4):
        return False   # festive season closure
    return True


def next_open(d):
    while not is_open(d):
        d += timedelta(days=1)
    return d


def weekday_span(start, days):
    """End date of a leave block of `days` weekdays starting at `start`."""
    d, counted = start, 0
    while True:
        if d.weekday() < 5:
            counted += 1
            if counted == days:
                return d
        d += timedelta(days=1)


def at(d, hour, minute=0):
    return datetime.combine(d, time(hour, minute))


# --------------------------------------------------------------------------
# Leave plan - a story worth showing: one person close to their allowance,
# one with no annual leave yet, a 3-day sick spell with no note, a couple of
# declined requests and some pending ones waiting for a decision.
# --------------------------------------------------------------------------

LEAVE_PLAN = {
    # key: [(type, month, day, weekdays, status-if-future, reason)]
    'pm': [('Sick', 2, 19, 1, None, 'Flu'),
           ('Annual', 4, 7, 3, None, 'School holidays with the kids'),
           ('Annual', 7, 6, 5, None, 'Family holiday in the Drakensberg'),
           ('Annual', 12, 14, 5, 'Approved', 'Year-end break')],
    'dentist': [('Annual', 3, 23, 4, None, 'Visiting family in Limpopo'),
                ('Sick', 5, 12, 1, None, 'Migraine'),
                ('Annual', 6, 22, 5, None, 'Winter holiday'),
                ('Sick', 8, 27, 1, None, 'Stomach bug'),
                ('Family Responsibility', 9, 8, 1, None, 'Child sick at home'),
                ('Annual', 10, 19, 3, 'Approved', 'Long weekend away')],
    'billing1': [('Annual', 1, 26, 3, None, 'Moving house'),
                 ('Sick', 3, 4, 1, None, 'Doctor said to rest'),
                 ('Annual', 4, 20, 5, None, 'Holiday'),
                 ('Annual', 7, 13, 4, None, 'Wedding in the family'),
                 ('Sick', 9, 15, 1, None, 'Flu'),
                 ('Annual', 10, 26, 2, 'Pending', 'Personal matters')],
    'billing2': [('Sick', 6, 10, 1, None, 'Tooth abscess'),
                 ('Annual', 8, 17, 3, None, 'Rest and recharge')],
    'reception': [('Annual', 1, 19, 5, None, 'Holiday in Durban'),
                  ('Annual', 3, 30, 4, None, 'Easter with family'),
                  ('Sick', 5, 4, 1, None, 'Flu'),
                  ('Annual', 6, 29, 5, None, 'School holidays'),
                  ('Annual', 8, 24, 2, 'Rejected', 'Short trip'),
                  ('Annual', 9, 21, 5, None, 'Heritage week away')],
    'da1': [('Annual', 2, 16, 3, None, 'Rest and recharge'),
            ('Sick', 3, 16, 1, None, 'Fever'),
            ('Family Responsibility', 4, 28, 1, None, 'Funeral of an uncle'),
            ('Annual', 5, 25, 4, None, 'Holiday'),
            ('Sick', 7, 21, 2, None, 'Bronchitis'),
            ('Annual', 8, 3, 5, None, 'Family holiday'),
            ('Annual', 11, 9, 3, 'Pending', 'Graduation ceremony')],
    'da2': [('Annual', 1, 12, 4, None, 'Late holiday'),
            ('Annual', 6, 15, 5, None, 'Youth Day week away'),
            ('Sick', 8, 11, 3, None, 'Chest infection'),
            ('Annual', 12, 14, 4, 'Rejected', 'Year-end trip')],
    'da3': [('Sick', 2, 9, 1, None, 'Sore throat'),
            ('Sick', 6, 1, 1, None, 'Flu'),
            ('Family Responsibility', 9, 14, 2, None, 'Mother in hospital'),
            ('Annual', 10, 12, 5, 'Pending', 'First holiday this year')],
    'cleaner': [('Sick', 1, 28, 1, None, 'Back pain'),
                ('Annual', 4, 14, 2, None, 'Family visit'),
                ('Annual', 7, 27, 5, None, 'Holiday at home'),
                ('Annual', 10, 6, 2, 'Approved', 'Personal')],
}
APPROVAL_NOTES = ['', '', '', 'Enjoy the break!', 'Approved - cover arranged.', 'Approved.']
REJECTION_NOTES = {
    'Short trip': 'Sorry - two people are already off that week. Please pick another date.',
    'Year-end trip': 'Year-end leave is already fully allocated. Let\'s look at January.',
}


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def make_logo():
    from PIL import Image, ImageDraw, ImageFont

    def font(names, size):
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    img = Image.new('RGB', (760, 240), '#0E3B4A')
    draw = ImageDraw.Draw(img)
    # a simple droplet-and-wave mark
    draw.ellipse((40, 52, 176, 188), fill='#2BA6A0')
    draw.polygon([(108, 22), (64, 96), (152, 96)], fill='#2BA6A0')
    draw.arc((62, 92, 154, 160), 200, 340, fill='white', width=9)
    draw.text((208, 56), 'Brightwater', font=font(['segoeuib.ttf', 'arialbd.ttf'], 74),
              fill='white')
    draw.text((212, 148), 'D E N T A L   S T U D I O', font=font(['segoeui.ttf', 'arial.ttf'], 30),
              fill='#9ED8D3')
    img.save(demo_env.LOGO_PATH)


def create_people():
    people = {}
    for key, username, name, role, started in STAFF:
        first = username
        user = User(username=username, full_name=name, role=role, status='Active',
                    email=f'{first}@{EMAIL_DOMAIN}', phone=f'082 555 {rng.randint(1000, 9999)}',
                    start_date=started, created_at=at(max(started, START - timedelta(days=30)), 9))
        user.set_password(PASSWORD)
        db.session.add(user)
        people[key] = user
    db.session.commit()
    assert people['owner'].id == 1   # app code assumes user 1 is the owner
    return people


def create_kpis():
    by_role = {}
    for role, categories in KPI_DEFINITIONS.items():
        by_role[role] = []
        for name, data in categories.items():
            category = KPICategory(name=name, role=role, weight=data['weight'], is_active=True)
            db.session.add(category)
            db.session.flush()
            for kpi_name in data['kpis']:
                kpi = RoleKPI(category_id=category.id, name=kpi_name, role=role, is_active=True)
                db.session.add(kpi)
                by_role[role].append(kpi)
    db.session.commit()
    return by_role


def plan_leave(people):
    """All leave rows, plus the days each practitioner is away."""
    away = defaultdict(set)
    rows = []
    for key, items in LEAVE_PLAN.items():
        user = people[key]
        for kind, month, day, length, future_status, reason in items:
            try:
                start = date(START.year, month, day)
            except ValueError:
                continue
            if start < START:
                continue
            start = next_open(start)
            end = weekday_span(start, length)
            if start <= TODAY:
                status = 'Rejected' if future_status == 'Rejected' else 'Approved'
            else:
                status = future_status or 'Approved'
            if kind == 'Sick':
                created = at(start, 7, rng.randint(5, 55))
            else:
                created = at(start - timedelta(days=rng.randint(10, 35)), rng.randint(8, 16),
                             rng.randint(0, 59))
                created = min(created, at(TODAY - timedelta(days=rng.randint(1, 6)), 10,
                                          rng.randint(0, 59)))
            approver = people['owner'] if key == 'pm' else people['pm']
            decided = None
            if status != 'Pending':
                decided = created + timedelta(days=rng.randint(0, 3), hours=rng.randint(1, 6))
                decided = min(decided, datetime.combine(TODAY, time(8, 30)))
            notes = ''
            if status == 'Rejected':
                notes = REJECTION_NOTES.get(reason, 'Not possible on these dates.')
            elif status == 'Approved':
                notes = {'Sick': 'Get well soon.',
                         'Family Responsibility': 'Take the time you need.'}.get(
                    kind) or rng.choice(APPROVAL_NOTES)
            rows.append(LeaveRequest(
                staff_id=user.id, leave_type=kind, start_date=start, end_date=end,
                reason=reason, status=status, created_at=created,
                approved_by=approver.id if decided else None,
                approval_notes=notes or None, approved_at=decided))
            if status == 'Approved':
                d = start
                while d <= end:
                    away[key].add(d)
                    d += timedelta(days=1)
    return rows, away


def create_leave(people, rows):
    db.session.add_all(rows)
    db.session.flush()
    for leave in rows:
        if leave.status == 'Pending':
            staff = db.session.get(User, leave.staff_id)
            for manager in (people['owner'], people['pm']):
                if manager.id == leave.staff_id:
                    continue
                db.session.add(Notification(
                    user_id=manager.id, title='New Leave Request',
                    message=(f'{staff.full_name} has requested {leave.leave_type} leave from '
                             f'{leave.start_date.strftime("%d %b %Y")} to '
                             f'{leave.end_date.strftime("%d %b %Y")}'),
                    notification_type='leave_request',
                    link=f'/leave/{leave.id}/approve', created_at=leave.created_at))
            continue
        db.session.add(PerformanceEvent(
            staff_id=leave.staff_id, event_type='Leave',
            event_description=(f'{leave.leave_type} leave {leave.status.lower()}: '
                               f'{leave.start_date} to {leave.end_date}'),
            event_data={'leave_id': leave.id, 'leave_type': leave.leave_type,
                        'status': leave.status, 'start_date': leave.start_date.isoformat(),
                        'end_date': leave.end_date.isoformat()},
            created_by=leave.approved_by, created_at=leave.approved_at))
    db.session.commit()


# KPI ability per person: chance of meeting a KPI, and a month-by-month nudge
KPI_PROFILE = {
    'da1': 0.86, 'pm': 0.85, 'dentist': 0.85, 'reception': 0.83,
    'cleaner': 0.82, 'da2': 0.78, 'da3': 0.74,
}
KPI_MISSED_NOTES = [
    'Late on two mornings this month.', 'Sterilisation log incomplete on two days.',
    'Two patient files not updated on time.', 'Missed one team meeting.',
    'Follow-up calls not logged consistently.', 'Room set-up slow on busy days.',
]
MONTH_NAMES = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July',
               'August', 'September', 'October', 'November', 'December']


def create_kpi_scores(people, kpis_by_role):
    months = []
    m = date(START.year, START.month, 1)
    while m <= TODAY:
        months.append((m.month, m.year))
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)

    for key, base in KPI_PROFILE.items():
        user = people[key]
        role = 'Dentist' if user.role == 'Practice Manager' else user.role
        kpis = kpis_by_role[role]
        weak = set(rng.sample(range(len(kpis)), k=max(2, len(kpis) // 5)))
        scorer = people['owner'] if key == 'pm' else people['pm']
        previous_low = False
        for index, (month, year) in enumerate(months):
            ability = base + rng.uniform(-0.09, 0.09) + index * 0.004
            if key == 'da3' and index == 3:
                ability = 0.64        # one rough month, recovered the next
            if previous_low:
                ability = max(ability, 0.74)
            ability = min(ability, 0.96)
            target_met = round(ability * len(kpis))
            # misses fall on this person's weaker KPIs first
            order = sorted(range(len(kpis)),
                           key=lambda i: (i not in weak, rng.random()))
            missed = set(order[:len(kpis) - target_met])
            if (month, year) == (TODAY.month, TODAY.year):
                scored_at = at(TODAY, 9, 15)
            else:
                nxt = date(year + (month == 12), month % 12 + 1, 1)
                scored_at = at(nxt + timedelta(days=rng.randint(1, 4)), 10, rng.randint(0, 59))
                scored_at = min(scored_at, at(TODAY, 9))
            for i, kpi in enumerate(kpis):
                met = 0 if i in missed else 1
                db.session.add(KPIScore(
                    staff_id=user.id, kpi_id=kpi.id, month=month, year=year, score=met,
                    notes=(rng.choice(KPI_MISSED_NOTES) if not met and rng.random() < 0.3 else None),
                    scored_by=scorer.id, scored_at=scored_at))
            met_count = len(kpis) - len(missed)
            pct = met_count / len(kpis) * 100
            previous_low = pct < 70
            db.session.add(PerformanceEvent(
                staff_id=user.id, event_type='KPI_Score',
                event_description=(f'Monthly KPI: {met_count}/{len(kpis)} ({pct:.0f}%) for '
                                   f'{MONTH_NAMES[month]} {year}'),
                event_data={'month': month, 'year': year, 'met': met_count,
                            'total': len(kpis), 'percentage': pct},
                created_by=scorer.id, created_at=scored_at))
    db.session.commit()


# --------------------------------------------------------------------------
# Daily sheets
# --------------------------------------------------------------------------

def make_patients(n=520):
    patients, used = [], set()
    while len(patients) < n:
        first, last = rng.choice(FIRST_NAMES), rng.choice(SURNAMES)
        if (first, last) in used:
            continue
        used.add((first, last))
        weights = [w for _n, w, _d in MEDICAL_AIDS]
        aid = rng.choices([n_ for n_, _w, _d in MEDICAL_AIDS], weights=weights)[0]
        patients.append({
            'name': f'{last} {first}' if rng.random() < 0.6 else f'{first} {last}',
            'file_no': f'{last[0].upper()}W{rng.randint(10, 4999):04d}',
            'computer_no': str(rng.randint(20000, 48999)),
            'aid': aid,
        })
    return patients


SEASON = {1: 1.12, 2: 0.95, 3: 1.0, 4: 0.9, 5: 1.0, 6: 0.94, 7: 1.06, 8: 1.0,
          9: 1.05, 10: 1.08, 11: 1.1, 12: 0.82}


def plan_sheets(people, away):
    patients = make_patients()
    regulars = patients[:140]          # come back more often
    pending_claims = defaultdict(list)  # aid -> [(due, amount)]
    last_paid = {}
    receipt = 4100
    sheets = []

    day = START
    week_index = 0
    while day < TODAY:
        if not is_open(day):
            day += timedelta(days=1)
            continue
        week_index = (day - START).days // 7
        saturday = day.weekday() == 5
        factor = SEASON[day.month] * (1 + 0.012 * ((day - START).days / 30))
        if day.weekday() in (0, 4):
            factor *= 1.12

        on_duty = []
        if saturday:
            on_duty = ['owner' if week_index % 2 == 0 else 'dentist']
        else:
            on_duty = [k for k, p in PRACTITIONERS.items()
                       if day.weekday() in p['weekdays'] and day not in away[k]]

        billing = []
        for key in on_duty:
            user = people[key]
            mean = 3.2 if saturday else PRACTITIONERS[key]['per_day'] * factor
            count = max(1, int(round(rng.gauss(mean, mean * 0.25))))
            entries = []
            for _ in range(count):
                patient = rng.choice(regulars) if rng.random() < 0.35 else rng.choice(patients)
                weights = [w for w, _l, _h in TREATMENTS]
                _w, low, high = rng.choices(TREATMENTS, weights=weights)[0]
                billed = price(low, high)
                entry = {'computer_no': patient['computer_no'], 'file_no': patient['file_no'],
                         'patient_name': patient['name'], 'medical_aid': patient['aid'],
                         'amount_billed': billed, 'card_paid': 0, 'card_bank': 'FNB',
                         'eft_paid': 0, 'eft_bank': 'FNB', 'credit_note': 0,
                         'credit_note_reason': '', 'journal': 0, 'journal_reason': '',
                         'receipt_no': ''}
                if patient['aid'] == 'Private':
                    r = rng.random()
                    if r < 0.66:
                        entry['card_paid'] = billed
                    elif r < 0.92:
                        entry['eft_paid'] = billed
                    elif r < 0.96:
                        part = round(billed * rng.uniform(0.3, 0.6), 1)
                        entry['card_paid'], entry['eft_paid'] = part, round(billed - part, 1)
                    # else: on account, pays later
                else:
                    copay = 0
                    if rng.random() < 0.33:
                        copay = round(billed * rng.uniform(0.1, 0.3), 1)
                        entry['card_paid'] = copay
                    pending_claims[patient['aid']].append(
                        (day + timedelta(days=rng.randint(9, 28)), billed - copay))
                entry['card_bank'] = rng.choice(['FNB', 'Capitec'])
                entry['eft_bank'] = 'FNB' if rng.random() < 0.6 else 'Capitec'
                if entry['card_paid'] or entry['eft_paid']:
                    if rng.random() < 0.85:
                        receipt += 1
                        entry['receipt_no'] = str(receipt)
                if rng.random() < 0.015:
                    entry['journal'] = round(min(billed, rng.uniform(60, 650)), 1)
                    entry['journal_reason'] = rng.choice(JOURNAL_REASONS)
                entries.append(entry)

                # Now and then an invoice is reversed and billed again
                if rng.random() < 0.025:
                    reason = rng.choice(CREDIT_NOTE_REASONS)
                    reversal = dict(entry, card_paid=0, eft_paid=0, receipt_no='',
                                    journal=0, journal_reason='',
                                    credit_note=billed, credit_note_reason=reason)
                    entries.insert(len(entries) - 1, reversal)
            billing.append({'key': key, 'entries': entries})

        # A wrong-practitioner reversal is re-billed under someone else
        if len(billing) > 1:
            for group in billing:
                for e in list(group['entries']):
                    if e['credit_note_reason'] == 'Wrong practitioner':
                        other = rng.choice([g for g in billing if g is not group])
                        moved = [x for x in group['entries']
                                 if x is not e and x['patient_name'] == e['patient_name']
                                 and not x['credit_note']]
                        for x in moved[:1]:
                            group['entries'].remove(x)
                            other['entries'].append(x)

        # Medical aid remittances (ERA) for claims that have fallen due
        era = []
        for aid, _share, pay_day in MEDICAL_AIDS:
            if pay_day is None:
                continue
            due = [c for c in pending_claims[aid] if c[0] <= day]
            overdue = (day - last_paid.get(aid, START)).days >= 9
            if due and (day.weekday() == pay_day or overdue):
                claimed = sum(a for _d, a in due)
                paid = round(claimed * rng.uniform(0.93, 1.0), 2)
                pending_claims[aid] = [c for c in pending_claims[aid] if c[0] > day]
                last_paid[aid] = day
                era.append({'batch_number': f'{aid[:3].upper()}{rng.randint(100000, 999999)}',
                            'medical_aid_name': aid, 'payment_date': day.isoformat(),
                            'amount_paid': money(paid)})

        expenses, notes = 0, ''
        if rng.random() < 0.38:
            what, low, high = rng.choice(EXPENSES)
            expenses = round(rng.uniform(low, high), 2)
            notes = f'Expenses: {what} (R{expenses:,.2f})'

        sheets.append({'date': day, 'billing': billing, 'era': era,
                       'expenses': expenses, 'notes': notes})
        day += timedelta(days=1)
    return sheets


def post_sheets(app, people, sheets):
    client = app.test_client()
    preparers = defaultdict(list)
    for sheet in sheets:
        late_starter = people['billing2']
        use_second = (sheet['date'] >= late_starter.start_date
                      and (sheet['date'].weekday() == 5 or rng.random() < 0.3))
        preparers['billing2' if use_second else 'billing1'].append(sheet)

    for key, batch in preparers.items():
        user = people[key]
        client.get('/logout')
        resp = client.post('/login', data={'username': user.username, 'password': PASSWORD})
        assert resp.status_code == 302, f'login failed for {user.username}'
        for sheet in batch:
            billing_data = [{
                'provider_name': people[g['key']].full_name,
                'provider_id': people[g['key']].id,
                'entries': [{k: (money(v) if isinstance(v, float) else (str(v) if v else ''))
                             for k, v in e.items()} for e in g['entries']],
            } for g in sheet['billing']]
            iso = sheet['date'].isoformat()
            resp = client.post(f'/reconciliation/new/{iso}', data={
                'date': iso, 'notes': sheet['notes'], 'expenses': money(sheet['expenses']),
                'billing_data': json.dumps(billing_data), 'era_data': json.dumps(sheet['era']),
            })
            assert resp.status_code == 302 and '/reconciliation/view/' in resp.headers['Location'], \
                f'sheet {iso} was not saved ({resp.status_code})'
    client.get('/logout')

    # Sheets are captured at close of business on the day, not today
    for rec in DailyReconciliation.query.all():
        stamp = at(rec.date, 17, rng.randint(5, 55))
        rec.prepared_at = rec.created_at = rec.updated_at = stamp
        for log in AuditLog.query.filter_by(entity_type='DailyReconciliation', entity_id=rec.id):
            log.created_at = stamp
    db.session.commit()


def create_patient_flow(people, sheets):
    for sheet in sheets:
        seen = {e['patient_name'] for g in sheet['billing'] for e in g['entries']}
        treated = len(seen)
        no_shows = min(3, max(0, int(rng.gauss(1.0, 1.0))))
        flow = PatientFlow(
            date=sheet['date'], treated=treated,
            walk_ins=min(treated, max(0, int(rng.gauss(1.4, 1.0)))),
            no_shows=no_shows,
            cancellations=min(3, max(0, int(rng.gauss(0.9, 0.9)))),
            reschedules=min(3, max(0, int(rng.gauss(0.8, 0.8)))),
            notes=('Load-shedding from 10:00 to 12:00, two patients moved.'
                   if rng.random() < 0.03 else None),
            recorded_by=people['reception'].id,
            created_at=at(sheet['date'], 16, rng.randint(30, 59)))
        db.session.add(flow)
    db.session.commit()


def create_dashboard_content(people):
    owner, pm = people['owner'], people['pm']
    tasks = [
        ('Review the September turnover report', 'owner', 2, 'To Do'),
        ('Sign off year-end leave roster', 'owner', 5, 'To Do'),
        ('Order composite and bonding agent', 'da1', 2, 'To Do'),
        ('Service the autoclave - book technician', 'pm', 5, 'In Progress'),
        ('Update patient recall list for November', 'reception', 7, 'To Do'),
        ('Deep clean surgery 2 after renovation', 'cleaner', -1, 'To Do'),
        ('Chase outstanding Bonitas claims older than 60 days', 'billing1', 3, 'In Progress'),
        ('Check stock of local anaesthetic cartridges', 'da2', 1, 'To Do'),
        ('Prepare monthly turnover report', 'billing1', 6, 'To Do'),
        ('File signed consent forms', 'da3', -3, 'Done'),
    ]
    for title, key, due_in, status in tasks:
        db.session.add(Task(title=title, assigned_to=people[key].id,
                            due_date=TODAY + timedelta(days=due_in), status=status,
                            created_by=pm.id, created_at=at(TODAY - timedelta(days=4), 9)))
    announcements = [
        ('Staff meeting on Friday at 07:30',
         'Short meeting before the first patient: year-end leave roster and new sterilisation '
         'checklist. Coffee is on the practice.', 'Important', 2),
        ('New intraoral camera in Surgery 1',
         'Dr. Molefe will show everyone how to use it during lunch on Wednesday.', 'Normal', 6),
        ('Reminder: submit leave on StaffTrack',
         'Please apply for all leave on StaffTrack so balances stay correct - no more paper forms.',
         'Normal', 15),
    ]
    for title, content, priority, ago in announcements:
        db.session.add(Announcement(title=title, content=content, priority=priority,
                                    is_active=True, created_by=owner.id,
                                    created_at=at(TODAY - timedelta(days=ago), 8, 15)))
    db.session.commit()


def main():
    if os.path.exists(demo_env.DB_PATH):
        try:
            os.remove(demo_env.DB_PATH)
        except PermissionError:
            raise SystemExit('The demo database is in use. Stop run_demo.py first, '
                             'then run this again.')
    app = create_app()
    app.config['WTF_CSRF_ENABLED'] = False
    demo_env.assert_demo_database(app)

    with app.app_context():
        db.create_all()
        make_logo()
        people = create_people()
        kpis = create_kpis()
        leave_rows, away = plan_leave(people)
        create_leave(people, leave_rows)
        create_kpi_scores(people, kpis)
        sheets = plan_sheets(people, away)
        post_sheets(app, people, sheets)
        create_patient_flow(people, sheets)
        create_dashboard_content(people)

        print(f'Demo practice: {demo_env.PRACTICE_NAME}')
        print(f'Data from {START:%d/%m/%Y} to {TODAY - timedelta(days=1):%d/%m/%Y}')
        print(f'  staff            {User.query.count()}')
        print(f'  leave requests   {LeaveRequest.query.count()}')
        print(f'  KPI scores       {KPIScore.query.count()}')
        print(f'  daily sheets     {DailyReconciliation.query.count()}')
        print(f'Database: {demo_env.DB_PATH}')
        print(f'Log in as "demo" (owner) or any first name, password "{PASSWORD}".')


if __name__ == '__main__':
    main()
