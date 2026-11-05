"""Vercel entry point. Vercel serves the WSGI app named `app` in this file."""
import os
import sys

# The project root, so `import app` finds the application package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

app = create_app()
