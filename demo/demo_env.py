"""Environment for the demo copy of StaffTrack.

The demo runs against its own SQLite file, never the live database. This
module must be imported before anything from `app`, because config.py reads
the environment once at import time and .env would otherwise point it at
Supabase (load_dotenv never overrides a variable that is already set).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(ROOT, 'instance', 'demo')
DB_PATH = os.path.join(DEMO_DIR, 'demo.db')
LOGO_PATH = os.path.join(DEMO_DIR, 'demo-logo.png')

PRACTICE_NAME = 'Brightwater Dental Studio'
PORT = 5050


def configure():
    os.makedirs(DEMO_DIR, exist_ok=True)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    os.environ['DATABASE_URL'] = 'sqlite:///' + DB_PATH.replace('\\', '/')
    os.environ['PRACTICE_NAME'] = PRACTICE_NAME
    os.environ['PRACTICE_LOGO'] = LOGO_PATH
    os.environ['MAIL_ENABLED'] = 'false'
    # Served over plain http on localhost, so the session cookie must not be
    # marked secure or the browser drops it and login never sticks.
    os.environ['FLASK_ENV'] = 'development'


def assert_demo_database(app):
    """Refuse to continue unless the app is pointed at the demo file."""
    from app import db
    with app.app_context():
        url = str(db.engine.url)
    if not url.startswith('sqlite') or not url.replace('\\', '/').endswith('/instance/demo/demo.db'):
        raise SystemExit(f'Refusing to run: database is {url!r}, not the demo file.')
