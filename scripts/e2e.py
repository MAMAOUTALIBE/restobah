#!/usr/bin/env python3
"""Run Playwright against an isolated, disposable instance.

The local database, `.runtime/admin-credentials.txt` and the servers started by
`npm run dev:all` are never touched: a temporary SQLite database, runtime
directory and e-mail folder are created, then deleted after the run.
"""
from pathlib import Path
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
API_PORT = int(os.getenv('STC_E2E_API_PORT', '8001'))
WEB_PORT = int(os.getenv('STC_E2E_WEB_PORT', '5174'))

def busy(port):
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1', port)) == 0

def wait(url, seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit(f'Le service {url} ne répond pas.')

def main():
    payment_mode = os.getenv('STC_E2E_PAYMENT_MODE', 'simulation')
    demo_mode = os.getenv('STC_E2E_DEMO_MODE', '1')
    if payment_mode not in {'simulation', 'on_site'} or demo_mode not in {'0', '1'}:
        sys.exit('Recette : STC_E2E_PAYMENT_MODE doit être simulation/on_site et STC_E2E_DEMO_MODE doit être 0/1.')
    if payment_mode == 'simulation' and demo_mode != '1':
        sys.exit('La simulation est réservée au mode démonstration, même sur la base jetable.')
    python = ROOT / 'backend/.venv/bin/python'
    if not python.exists():
        sys.exit('Exécutez python3 scripts/setup.py avant les tests.')
    for port in (API_PORT, WEB_PORT):
        if busy(port):
            sys.exit(f'Le port {port} est déjà utilisé ; choisissez STC_E2E_API_PORT/STC_E2E_WEB_PORT.')
    with tempfile.TemporaryDirectory(prefix='stc-e2e-') as directory:
        base = Path(directory)
        web = f'http://localhost:{WEB_PORT}'
        env = {
            **os.environ,
            # CI may point STC_E2E_DATABASE_URL to a disposable PostgreSQL database.
            'DATABASE_URL': os.getenv('STC_E2E_DATABASE_URL', f'sqlite:///{base / "e2e.sqlite3"}'),
            'DJANGO_DEBUG': '1',
            'STC_DEMO_MODE': demo_mode,
            'STC_PAYMENT_MODE': payment_mode,
            'STRIPE_SECRET_KEY': '',
            'STRIPE_WEBHOOK_SECRET': '',
            'EMAIL_BACKEND': 'shop.email_backend.PrivateFileEmailBackend',
            'STC_EMAIL_FILE_PATH': str(base / 'emails'),
            'STC_RUNTIME_DIR': str(base / 'runtime'),
            'STC_MEDIA_ROOT': str(base / 'media'),
            'FRONTEND_URL': web,
            'DJANGO_CSRF_TRUSTED_ORIGINS': f'{web},http://127.0.0.1:{WEB_PORT}',
            'STC_API_TARGET': f'http://127.0.0.1:{API_PORT}',
            'STC_WEB_PORT': str(WEB_PORT),
            'E2E_BASE_URL': web,
        }
        for command in ('migrate', 'seed_demo', 'dev_admin'):
            subprocess.run([str(python), 'backend/manage.py', command, '--verbosity', '0'], cwd=ROOT, env=env, check=True)
        children = [
            subprocess.Popen([str(python), 'backend/manage.py', 'runserver', f'127.0.0.1:{API_PORT}', '--noreload'], cwd=ROOT, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=open(base / 'backend.log', 'w')),
            subprocess.Popen(['npx', 'vite'], cwd=ROOT, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        ]
        try:
            wait(f'{web}/api/health/')
            # The complete suite changes shared restaurant settings: keep its default run serial.
            arguments = sys.argv[1:] or ['--workers=1']
            result = subprocess.run(['npx', 'playwright', 'test', *arguments], cwd=ROOT, env=env)
            if result.returncode:
                print((base / 'backend.log').read_text()[-4000:], file=sys.stderr)
            return result.returncode
        finally:
            for child in children:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
            for child in children:
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)

if __name__ == '__main__':
    sys.exit(main())
