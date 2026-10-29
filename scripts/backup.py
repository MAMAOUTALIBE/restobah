#!/usr/bin/env python3
"""Consistent private database backup; never prints database contents."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--postgres', action='store_true', help='Back up PostgreSQL from the local Docker Compose service')
    args = parser.parse_args()
    directory = ROOT / 'backups'
    directory.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if args.postgres:
        output = directory / f'stc-{stamp}.dump'
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                subprocess.run(['docker', 'compose', 'exec', '-T', 'db', 'pg_dump', '-U', 'stc', '-d', 'stc', '--format=custom'], cwd=ROOT, stdout=stream, check=True)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    else:
        source = ROOT / 'backend/db.sqlite3'
        if not source.exists():
            parser.error('Aucune base SQLite locale à sauvegarder.')
        output = directory / f'stc-{stamp}.sqlite3'
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as current, sqlite3.connect(output) as backup:
            current.backup(backup)
        with sqlite3.connect(output) as check:
            if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('La vérification de la sauvegarde a échoué.')
    print(f'Sauvegarde privée créée : {output.relative_to(ROOT)}')

if __name__ == '__main__':
    main()
