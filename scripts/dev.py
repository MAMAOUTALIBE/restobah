#!/usr/bin/env python3
"""Launch both local servers and stop children cleanly on Ctrl+C."""
from pathlib import Path
import os
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent

def main():
    python = ROOT / 'backend/.venv/bin/python'
    if not python.exists():
        sys.exit('Exécutez python3 scripts/setup.py avant de démarrer.')
    for port in (8000, 5173):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                sys.exit(f'Le port {port} est déjà utilisé. Arrêtez le serveur existant avant npm run dev:all.')
    children = []
    def stop(*_):
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        children.append(subprocess.Popen([str(python), 'backend/manage.py', 'runserver', '127.0.0.1:8000', '--noreload'], cwd=ROOT, start_new_session=True))
        children.append(subprocess.Popen(['npm', 'run', 'dev'], cwd=ROOT, start_new_session=True))
        print('STC : http://localhost:5173 · Administration : http://localhost:5173/admin/', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        if any(child.returncode for child in children if child.poll() is not None):
            sys.exit(1)
    finally:
        stop()

if __name__ == '__main__':
    main()
