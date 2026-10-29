#!/usr/bin/env python3
"""Package reviewable source/build artifacts, excluding all runtime/customer data."""
from pathlib import Path
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parent.parent
FILES = ['README.md','API_CONTRACT.md','package.json','package-lock.json','index.html','tsconfig.json','vite.config.ts','eslint.config.js','playwright.config.ts','.gitignore','.dockerignore','.env.example','.env.production.example','compose.yaml','compose.production.yaml']
DIRECTORIES = ['src','public','backend','scripts','deploy','docs','tests','.github','dist']
EXCLUDED_PARTS = {'.venv','__pycache__','.private-emails','private_emails','media','staticfiles','.runtime'}
EXCLUDED_NAMES = {'.env','.dev-secret','db.sqlite3','db.sqlite3-shm','db.sqlite3-wal'}

def included(path):
    return not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts) and path.name not in EXCLUDED_NAMES and not path.name.startswith('db.sqlite3') and not (path.name.startswith('.env') and path.name not in {'.env.example','.env.production.example'}) and path.suffix not in {'.pyc','.pyo','.log'}

def main():
    directory = ROOT/'artifacts'
    directory.mkdir(exist_ok=True)
    output = directory/'STC-livraison.zip'
    paths = {ROOT/name for name in FILES if (ROOT/name).is_file()}
    for name in DIRECTORIES:
        paths.update(path for path in (ROOT/name).rglob('*') if path.is_file() and included(path))
    for name in ['audit-mobile-1-accueil.png','audit-mobile-5-suivi.png','audit-tablet-1-accueil.png','audit-desktop-1-accueil.png','audit-mobile-6-compte-erreur.png']:
        path = ROOT/'screenshots'/name
        if path.is_file():
            paths.add(path)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path,Path('STC')/path.relative_to(ROOT))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (directory/'STC-livraison.sha256').write_text(f'{digest}  STC-livraison.zip\n')
    print(f'{len(paths)} fichiers livrés ; archive {output.stat().st_size/1024/1024:.1f} Mo. Secrets, bases clients et fichiers privés exclus.')

if __name__ == '__main__':
    main()
