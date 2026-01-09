"""
StaffTrack - Staff Accountability System
Main entry point for the application.
"""

from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash
import os

app = create_app()


def init_db():
    """Initialize the database and create Super Admin if not exists."""
    with app.app_context():
        # Create all tables
        db.create_all()

        # Check if admin user exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                full_name='Dr. Buleni',
                role='Super Admin',
                email='admin@stafftrack.local',
                status='Active'
            )
            db.session.add(admin)
            db.session.commit()
            print("=" * 50)
            print("Super Admin account created!")
            print("Username: admin")
            print("Password: admin123")
            print("IMPORTANT: Change this password immediately!")
            print("=" * 50)
        else:
            print("Database already initialized.")


if __name__ == '__main__':
    # Ensure instance folder exists
    os.makedirs('instance', exist_ok=True)
    os.makedirs('uploads/sop_documents', exist_ok=True)

    # Initialize database
    init_db()

    # Run the application
    print("\n" + "=" * 50)
    print("StaffTrack is starting...")
    print("Access the application at: http://127.0.0.1:5000")
    print("=" * 50 + "\n")

    app.run(debug=True, host='127.0.0.1', port=5000)
