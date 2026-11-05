import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # SECRET_KEY is required - generate one with: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set. Add SECRET_KEY to your environment variables on Render.")

    # Use Supabase PostgreSQL (from .env) or fallback to SQLite for local development
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'stafftrack.db')
    # Neon and most hosts hand out plain postgresql:// addresses, which
    # SQLAlchemy reads as the psycopg2 driver. This app uses psycopg 3.
    for _prefix in ('postgres://', 'postgresql://'):
        if SQLALCHEMY_DATABASE_URI.startswith(_prefix):
            SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg://' + SQLALCHEMY_DATABASE_URI[len(_prefix):]
            break
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # PostgreSQL connection pool settings for Supabase.
    # `prepare_threshold=None` disables server-side prepared statements, required when
    # using Supabase's transaction pooler (port 6543) which doesn't keep client-side
    # statement state across pooled connections. Only applied when we're on Postgres.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    if SQLALCHEMY_DATABASE_URI.startswith('postgresql'):
        SQLALCHEMY_ENGINE_OPTIONS['connect_args'] = {'prepare_threshold': None}

    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads', 'sop_documents')
    # Uploads (sick notes, SOP documents) are capped at 4MB each in their own
    # routes. Vercel refuses any request over 4.5MB before it reaches the
    # app, so the per-file limit stays below that. This hard cap sits just
    # above it so an oversized file still reaches our validator and gets a
    # friendly message rather than a bare 413 page.
    MAX_CONTENT_LENGTH = int(4.4 * 1024 * 1024)

    # Running on Vercel (it sets VERCEL=1): no writable disk, and nothing
    # may keep running after a response has been sent.
    ON_VERCEL = bool(os.environ.get('VERCEL'))

    # Set on the old host after a move, e.g. https://smilez.vernonfamily.solutions,
    # to send every visitor to the new address instead of serving the app.
    REDIRECT_TO = (os.environ.get('REDIRECT_TO') or '').rstrip('/')
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}

    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    # HTTPS-only cookies (Render uses HTTPS by default)
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Email settings (Flask-Mail)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@stafftrack.com')

    # Enable/disable email notifications
    MAIL_ENABLED = os.environ.get('MAIL_ENABLED', 'false').lower() == 'true'

    # The practice this deployment serves, printed on the login page and on
    # every PDF. PRACTICE_LOGO optionally points the PDF letterhead at a
    # different logo file; 'none' leaves the letterhead without one.
    PRACTICE_NAME = os.environ.get('PRACTICE_NAME', 'Smilez Dental Surgery')
    PRACTICE_LOGO = os.environ.get('PRACTICE_LOGO')
