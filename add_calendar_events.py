"""
Script to add South African public holidays and awareness days to the calendar.
Run with: python add_calendar_events.py
"""

from datetime import date
from app import create_app, db
from app.models import CalendarEvent, User

# South African Public Holidays 2025
# Fixed holidays (same date every year)
SA_PUBLIC_HOLIDAYS = [
    # Fixed dates
    (date(2025, 1, 1), "New Year's Day", "Holiday"),
    (date(2025, 3, 21), "Human Rights Day", "Holiday"),
    (date(2025, 4, 27), "Freedom Day", "Holiday"),
    (date(2025, 5, 1), "Workers' Day", "Holiday"),
    (date(2025, 6, 16), "Youth Day", "Holiday"),
    (date(2025, 8, 9), "National Women's Day", "Holiday"),
    (date(2025, 9, 24), "Heritage Day", "Holiday"),
    (date(2025, 12, 16), "Day of Reconciliation", "Holiday"),
    (date(2025, 12, 25), "Christmas Day", "Holiday"),
    (date(2025, 12, 26), "Day of Goodwill", "Holiday"),

    # Moveable holidays for 2025 (based on Easter)
    # Easter Sunday 2025 is April 20
    (date(2025, 4, 18), "Good Friday", "Holiday"),
    (date(2025, 4, 21), "Family Day (Easter Monday)", "Holiday"),
]

# Awareness Days and Special Days
AWARENESS_DAYS = [
    # January
    (date(2025, 1, 4), "World Braille Day", "Awareness Day"),

    # February
    (date(2025, 2, 4), "World Cancer Day", "Awareness Day"),
    (date(2025, 2, 13), "World Radio Day", "Awareness Day"),
    (date(2025, 2, 14), "Valentine's Day", "Awareness Day"),
    (date(2025, 2, 21), "Armed Forces Day (South Africa)", "Awareness Day"),

    # March
    (date(2025, 3, 6), "National Dentist Day", "Awareness Day"),
    (date(2025, 3, 8), "International Women's Day", "Awareness Day"),
    (date(2025, 3, 13), "World Kidney Day", "Awareness Day"),  # 2nd Thursday of March 2025
    (date(2025, 3, 20), "World Oral Health Day", "Awareness Day"),

    # April
    (date(2025, 4, 1), "April Fool's Day", "Awareness Day"),
    (date(2025, 4, 7), "World Health Day", "Awareness Day"),
    (date(2025, 4, 22), "Earth Day", "Awareness Day"),
    (date(2025, 4, 25), "World Malaria Day", "Awareness Day"),

    # May
    (date(2025, 5, 11), "Mother's Day", "Awareness Day"),  # 2nd Sunday of May 2025
    (date(2025, 5, 14), "Receptionists Day", "Awareness Day"),  # Practice's own day
    (date(2025, 5, 25), "Africa Day", "Awareness Day"),

    # June
    (date(2025, 6, 15), "Father's Day", "Awareness Day"),  # 3rd Sunday of June 2025

    # July
    (date(2025, 7, 18), "Nelson Mandela Day", "Awareness Day"),

    # August
    (date(2025, 8, 19), "World Humanitarian Day", "Awareness Day"),
    (date(2025, 8, 19), "World Photography Day", "Awareness Day"),
    (date(2025, 8, 22), "Tooth Fairy Day", "Awareness Day"),

    # September
    (date(2025, 9, 17), "World Patient Safety Day", "Awareness Day"),
    (date(2025, 9, 21), "International Day of Peace", "Awareness Day"),

    # October
    (date(2025, 10, 1), "Breast Cancer Awareness Day", "Awareness Day"),  # Start of Breast Cancer Awareness Month
    (date(2025, 10, 1), "International Coffee Day", "Awareness Day"),
    (date(2025, 10, 10), "World Mental Health Day", "Awareness Day"),
    (date(2025, 10, 16), "Bosses Day", "Awareness Day"),
    (date(2025, 10, 24), "World Polio Day", "Awareness Day"),

    # November
    (date(2025, 11, 1), "National Brush Day", "Awareness Day"),
    (date(2025, 11, 14), "World Diabetes Day", "Awareness Day"),
    (date(2025, 11, 19), "International Men's Day", "Awareness Day"),

    # December
    (date(2025, 12, 1), "World AIDS Day", "Awareness Day"),
    (date(2025, 12, 3), "International Day of People with Disabilities", "Awareness Day"),
]


def add_events():
    """Add all events to the calendar."""
    app = create_app()

    with app.app_context():
        # Get a user to set as creator (Super Admin or first user)
        admin = User.query.filter_by(role='Super Admin').first()
        if not admin:
            admin = User.query.first()

        if not admin:
            print("ERROR: No users found in database. Please create a user first.")
            return

        print(f"Using {admin.full_name} as event creator\n")

        added_count = 0
        skipped_count = 0

        # Add public holidays
        print("=" * 50)
        print("ADDING SOUTH AFRICAN PUBLIC HOLIDAYS")
        print("=" * 50)

        for event_date, title, event_type in SA_PUBLIC_HOLIDAYS:
            # Check if already exists
            existing = CalendarEvent.query.filter_by(
                title=title,
                event_date=event_date
            ).first()

            if existing:
                print(f"  SKIP: {title} ({event_date}) - already exists")
                skipped_count += 1
                continue

            event = CalendarEvent(
                title=title,
                description=f"South African Public Holiday",
                event_date=event_date,
                event_type=event_type,
                is_recurring=False,  # Holidays can shift, so not recurring
                created_by=admin.id
            )
            db.session.add(event)
            print(f"  ADD:  {title} - {event_date.strftime('%d %B %Y')}")
            added_count += 1

        # Add awareness days
        print("\n" + "=" * 50)
        print("ADDING AWARENESS DAYS & SPECIAL DAYS")
        print("=" * 50)

        for event_date, title, event_type in AWARENESS_DAYS:
            # Check if already exists
            existing = CalendarEvent.query.filter_by(
                title=title,
                event_date=event_date
            ).first()

            if existing:
                print(f"  SKIP: {title} ({event_date}) - already exists")
                skipped_count += 1
                continue

            # Some days are always on the same date, mark as recurring
            # Days that depend on weekdays (like Mother's Day) are not recurring
            non_recurring_days = [
                "Mother's Day", "Father's Day", "World Kidney Day"
            ]
            is_recurring = title not in non_recurring_days

            event = CalendarEvent(
                title=title,
                description=f"Awareness Day / Special Day",
                event_date=event_date,
                event_type=event_type,
                is_recurring=is_recurring,
                created_by=admin.id
            )
            db.session.add(event)
            recurring_note = " (recurring)" if is_recurring else ""
            print(f"  ADD:  {title} - {event_date.strftime('%d %B %Y')}{recurring_note}")
            added_count += 1

        # Commit all changes
        db.session.commit()

        print("\n" + "=" * 50)
        print(f"SUMMARY: Added {added_count} events, skipped {skipped_count} existing")
        print("=" * 50)


if __name__ == "__main__":
    add_events()
