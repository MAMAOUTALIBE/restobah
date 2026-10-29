#!/usr/bin/env python3
"""Idempotent local setup. Does not print secrets or replace existing data."""
from pathlib import Path
import os
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)

def main():
    env_file = ROOT / '.env'
    if not env_file.exists():
        text = (ROOT / '.env.example').read_text()
        text = text.replace('DJANGO_SECRET_KEY=\n', f'DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n')
        text = text.replace('POSTGRES_PASSWORD=\n', f'POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n')
        # Let Django choose an absolute SQLite path in local development.
        text = '\n'.join(line for line in text.splitlines() if not line.startswith('DATABASE_URL=')) + '\n'
        fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(text)
        print('.env créé (permissions privées).')
    python = ROOT / 'backend/.venv/bin/python'
    if not python.exists():
        interpreter = shutil.which('python3.13') or sys.executable
        run(interpreter, '-m', 'venv', str(ROOT / 'backend/.venv'))
    run(str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'backend/requirements.txt'))
    run('npm', 'ci')
    run(str(python), 'backend/manage.py', 'migrate', '--noinput')
    run(str(python), 'backend/manage.py', 'seed_demo')
    run(str(python), 'backend/manage.py', 'dev_admin')
    print('Installation terminée. Lancez npm run dev:all.')

if __name__ == '__main__':
    main()
