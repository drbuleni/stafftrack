"""Back up a StaffTrack database to a dated folder.

    python tools/backup_database.py                  # the database in DATABASE_URL
    python tools/backup_database.py NEON_DATABASE_URL

Writes into Documents/StaffTrack Backups/<date>/:
- <name>_public.dump   all app tables, restorable with pg_restore
- <name>_public.sql    the same as plain SQL
- <name>_full.dump     every schema, as a spare
- fingerprint_<name>.json  row counts per table and money totals per
  month, for checking that a copy matches the original

Read-only: safe to run while the practice is using the system. The output
holds patient data, so it stays on this laptop.
"""
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime

import psycopg
from dotenv import load_dotenv

PG_BIN = r'C:/Program Files/PostgreSQL/18/bin'
BACKUP_ROOT = os.path.join(os.path.expanduser('~'), 'Documents', 'StaffTrack Backups')


def connection_url(var):
    url = os.environ.get(var)
    if not url:
        raise SystemExit(f'{var} is not set in .env')
    return url.replace('postgresql+psycopg://', 'postgresql://')


def dump_url(url):
    # pg_dump needs a session connection; Supabase's transaction pooler
    # (port 6543) can break it, its session pooler is on 5432.
    return url.replace('.pooler.supabase.com:6543/', '.pooler.supabase.com:5432/')


def run_dump(url, args, path, attempts=3):
    for attempt in range(1, attempts + 1):
        started = time.time()
        result = subprocess.run([f'{PG_BIN}/pg_dump.exe', *args, '-f', path, '-d', url],
                                capture_output=True, text=True)
        if result.returncode == 0:
            print(f'  {os.path.basename(path)}: {os.path.getsize(path) / 1024:,.0f} KB '
                  f'in {time.time() - started:.0f}s')
            return True
        error = (result.stderr or '').replace(url, '<db>').strip().splitlines()
        print(f'  {os.path.basename(path)}: attempt {attempt} failed: {error[-1] if error else "?"}')
        time.sleep(5)
    return False


def table_count(path):
    result = subprocess.run([f'{PG_BIN}/pg_restore.exe', '--list', path],
                            capture_output=True, text=True)
    return sum(1 for line in result.stdout.splitlines() if 'TABLE DATA public' in line)


def fingerprint(url):
    fp = {'taken_at': datetime.now().isoformat(timespec='seconds'), 'tables': {},
          'monthly_money': {}, 'checks': {}}
    with psycopg.connect(url, prepare_threshold=None, connect_timeout=60) as conn:
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        for (table,) in cur.fetchall():
            cur.execute(f'SELECT COUNT(*) FROM public."{table}"')
            fp['tables'][table] = cur.fetchone()[0]
        cur.execute("""SELECT to_char(date, 'YYYY-MM'), COUNT(*), SUM(goodx_production),
                              SUM(card_fnb + card_capitec), SUM(eft_received),
                              SUM(medical_aid_payments), SUM(refunds_expenses), SUM(total_money_in)
                       FROM daily_reconciliations GROUP BY 1 ORDER BY 1""")
        for month, sheets, billed, card, eft, era, expenses, money_in in cur.fetchall():
            fp['monthly_money'][month] = {
                'sheets': sheets, 'billed': str(billed), 'card': str(card), 'eft': str(eft),
                'era': str(era), 'expenses': str(expenses), 'money_in': str(money_in)}
        checks = {
            'billing_lines_amount_billed': 'SELECT SUM(amount_billed) FROM reconciliation_billing_entries',
            'era_lines_amount_paid': 'SELECT SUM(amount_paid) FROM reconciliation_era_payments',
            'sick_note_bytes': 'SELECT COALESCE(SUM(octet_length(data)), 0) FROM leave_documents',
            'approved_leave_requests': "SELECT COUNT(*) FROM leave_requests WHERE status = 'Approved'",
            'kpi_scores_met': 'SELECT SUM(score) FROM kpi_scores',
            'turnover_sections_gross': 'SELECT SUM(gross_turnover) FROM turnover_report_sections',
            'latest_sheet_date': 'SELECT MAX(date)::text FROM daily_reconciliations',
            'latest_audit_entry': 'SELECT MAX(created_at)::text FROM audit_log',
        }
        for key, sql in checks.items():
            cur.execute(sql)
            fp['checks'][key] = str(cur.fetchone()[0])
    return fp


def main():
    load_dotenv()
    var = sys.argv[1] if len(sys.argv) > 1 else 'DATABASE_URL'
    name = 'neon' if 'NEON' in var else 'supabase'
    url = connection_url(var)
    folder = os.path.join(BACKUP_ROOT, date.today().isoformat())
    os.makedirs(folder, exist_ok=True)
    print(f'Backing up {var} into {folder}')

    common = ['-n', 'public', '--no-owner', '--no-privileges']
    ok = run_dump(dump_url(url), ['-Fc', *common], os.path.join(folder, f'{name}_public.dump'))
    ok &= run_dump(dump_url(url), common, os.path.join(folder, f'{name}_public.sql'))
    ok &= run_dump(dump_url(url), ['-Fc', '--no-owner', '--no-privileges'],
                   os.path.join(folder, f'{name}_full.dump'))
    tables = table_count(os.path.join(folder, f'{name}_public.dump')) if ok else 0

    fp = fingerprint(url)
    with open(os.path.join(folder, f'fingerprint_{name}.json'), 'w') as fh:
        json.dump(fp, fh, indent=1)
    print(f'  fingerprint: {len(fp["tables"])} tables, {sum(fp["tables"].values()):,} rows, '
          f'latest sheet {fp["checks"]["latest_sheet_date"]}')
    if not ok or tables != len(fp['tables']):
        raise SystemExit(f'BACKUP INCOMPLETE: {tables} tables in the dump, '
                         f'{len(fp["tables"])} in the database')
    print(f'Backup complete: all {tables} tables.')


if __name__ == '__main__':
    main()
