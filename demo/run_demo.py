"""Serve the demo copy of StaffTrack on http://127.0.0.1:5050.

Runs against instance/demo/demo.db only - build it first with
`python demo/seed_demo.py`. The live database is never touched.
"""
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_env  # noqa: E402  must run before anything imports app

demo_env.configure()
warnings.filterwarnings('ignore', message='.*Decimal objects natively.*')

if not os.path.exists(demo_env.DB_PATH):
    raise SystemExit('No demo database yet. Run: python demo/seed_demo.py')

from app import create_app  # noqa: E402

app = create_app()
demo_env.assert_demo_database(app)

if __name__ == '__main__':
    print(f'{demo_env.PRACTICE_NAME} (demo) - http://127.0.0.1:{demo_env.PORT}')
    print('Log in as "demo" / "demo1234"')
    app.run(host='127.0.0.1', port=demo_env.PORT, debug=False)
