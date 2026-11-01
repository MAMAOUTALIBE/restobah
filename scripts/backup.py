#!/usr/bin/env python3
"""Private, atomic database/full backups. Never prints configuration or customer data."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
KIND = 'stc-full-backup'
PAYLOADS = ('database.dump', 'media.tar.gz', 'container-private.tar.gz', 'host-private.tar.gz')


def private_directory(path):
    if path.is_symlink():
        raise ValueError('Le dossier de sauvegarde ne peut pas être un lien symbolique.')
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.chmod(0o700)


@contextmanager
def private_output(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'wb') as output:
        yield output
        output.flush()
        os.fsync(output.fileno())


@contextmanager
def backup_lock(directory, project):
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(directory / f'.stc-backup-{project}.lock', flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Une sauvegarde STC est déjà en cours.') from error
        yield
    finally:
        os.close(fd)


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def publish(source, target):
    # Same filesystem, no overwrite, and no visible empty/partial final file.
    os.link(source, target)
    source.unlink()


def run(command, *, output=None, source=None, timeout=600):
    result = subprocess.run(command, cwd=ROOT, stdout=output or subprocess.DEVNULL,
                            stdin=source, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        # stderr can contain environment-dependent details; keep public logs minimal.
        raise RuntimeError('La commande de sauvegarde a échoué (code '
                           + str(result.returncode) + '). Vérifiez les services STC.')


def compose_command(args):
    command = ['docker', 'compose', '--project-directory', str(ROOT),
               '--project-name', args.project_name]
    for name in args.compose_file or ['compose.yaml']:
        path = Path(name)
        path = path if path.is_absolute() else ROOT / path
        if not path.is_file():
            raise ValueError('Un fichier Compose demandé est absent.')
        command.extend(['-f', str(path)])
    return command


def postgres_dump(compose, path):
    with private_output(path) as output:
        run(compose + ['exec', '-T', 'db', 'pg_dump', '-U', 'stc', '-d', 'stc',
                       '--format=custom'], output=output)
    if not path.stat().st_size:
        raise RuntimeError('La sauvegarde PostgreSQL est vide.')
    with path.open('rb') as source:
        run(compose + ['exec', '-T', 'db', 'pg_restore', '--list'], source=source)


def sqlite_backup(path):
    source = ROOT / 'backend/db.sqlite3'
    if not source.is_file() or source.is_symlink():
        raise ValueError('Aucune base SQLite locale régulière à sauvegarder.')
    with private_output(path):
        pass
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as current:
        with closing(sqlite3.connect(path)) as backup:
            current.backup(backup)
    with closing(sqlite3.connect(path)) as check:
        if check.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise RuntimeError('La vérification de la sauvegarde SQLite a échoué.')
    with path.open('rb') as output:
        os.fsync(output.fileno())


def database_backup(directory, postgres, compose):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    suffix = '.dump' if postgres else '.sqlite3'
    target = directory / f'stc-{stamp}-{secrets.token_hex(3)}{suffix}'
    with tempfile.TemporaryDirectory(prefix='.stc-db-staging-', dir=directory) as temporary:
        Path(temporary).chmod(0o700)
        source = Path(temporary) / ('database' + suffix)
        if postgres:
            postgres_dump(compose, source)
        else:
            sqlite_backup(source)
        publish(source, target)
    return target


# Runs inside the backend. Paths are fixed by Compose; no configuration in argv.
CONTAINER_ARCHIVE = r'''import sys,tarfile
from pathlib import Path
kind=sys.argv[1]
roots=[('/app/media','media')] if kind=='media' else [('/app/.private-emails','emails'),('/app/.runtime','runtime')]
def add(archive,path,name):
    if path.is_symlink(): raise RuntimeError('Lien symbolique refusé dans la sauvegarde.')
    info=archive.gettarinfo(str(path),arcname=name)
    if not (info.isdir() or info.isfile()): raise RuntimeError('Fichier spécial refusé.')
    info.mode=0o700 if info.isdir() else 0o600
    info.uid=info.gid=0; info.uname=info.gname=''
    if info.isdir():
        archive.addfile(info)
        for child in sorted(path.iterdir()): add(archive,child,name+'/'+child.name)
    else:
        before=path.stat()
        with path.open('rb') as stream: archive.addfile(info,stream)
        after=path.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
            raise RuntimeError('Un fichier a changé pendant la sauvegarde. Réessayez.')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
    for source,name in roots:
        path=Path(source)
        if not path.is_dir(): raise RuntimeError('Dossier de sauvegarde absent.')
        add(archive,path,name)
'''


def safe_tar_info(info):
    info.uid = info.gid = 0
    info.uname = info.gname = ''
    info.mode = 0o700 if info.isdir() else 0o600
    if not (info.isfile() or info.isdir()):
        raise ValueError('Lien ou fichier spécial refusé dans les fichiers privés.')
    return info


def add_private_file(archive, path, name):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Un fichier privé régulier était attendu.')
    before = path.stat()
    archive.add(path, arcname=name, filter=safe_tar_info)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise RuntimeError('Un fichier privé a changé pendant la sauvegarde. Réessayez.')


def host_private_backup(path):
    environment = ROOT / '.env'
    if not environment.is_file() or environment.is_symlink():
        raise ValueError('Le fichier de configuration privé est absent ou est un lien.')
    with private_output(path) as output:
        with tarfile.open(fileobj=output, mode='w:gz') as archive:
            add_private_file(archive, environment, 'environment.env')
            runtime = ROOT / '.runtime'
            if runtime.is_symlink():
                raise ValueError('Le runtime privé ne peut pas être un lien.')
            if runtime.is_dir():
                # Credentials/marker only, never previous release archives or backups.
                for item in sorted(runtime.iterdir()):
                    if item.is_symlink():
                        raise ValueError('Lien refusé dans les fichiers privés du runtime.')
                    if item.is_file():
                        add_private_file(archive, item, 'host-runtime/' + item.name)


def verify_file_archive(source, allowed_roots):
    with tarfile.open(fileobj=source, mode='r:gz') as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if not (member.isfile() or member.isdir()) or path.is_absolute() \
                    or '..' in path.parts or not path.parts or path.parts[0] not in allowed_roots:
                raise ValueError('Chemin ou fichier invalide dans une archive de sauvegarde.')


def verify_bundle(path, project=None):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Sauvegarde complète régulière introuvable.')
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        expected = {'manifest.json', *PAYLOADS}
        if len(members) != len(expected) or {item.name for item in members} != expected \
                or any(not item.isfile() for item in members):
            raise ValueError('Le contenu de la sauvegarde complète est invalide.')
        manifest_member = archive.getmember('manifest.json')
        if manifest_member.size > 1024 * 1024:
            raise ValueError('Le manifeste de sauvegarde est trop grand.')
        with archive.extractfile(manifest_member) as source:
            manifest = json.load(source)
        if not isinstance(manifest, dict) or manifest.get('kind') != KIND or manifest.get('version') != 1 \
                or (project is not None and manifest.get('project') != project):
            raise ValueError('Cette sauvegarde appartient à un autre format ou projet.')
        if not isinstance(manifest.get('files'), dict) or set(manifest['files']) != set(PAYLOADS):
            raise ValueError('La liste des fichiers du manifeste est invalide.')
        created = datetime.fromisoformat(manifest['created_at'])
        if created.tzinfo is None:
            raise ValueError('La date de sauvegarde doit préciser son fuseau.')
        for name in PAYLOADS:
            member = archive.getmember(name)
            metadata = manifest['files'][name]
            if not isinstance(metadata, dict) or type(metadata.get('bytes')) is not int \
                    or not isinstance(metadata.get('sha256'), str) \
                    or not re.fullmatch(r'[0-9a-f]{64}', metadata['sha256']):
                raise ValueError('Les métadonnées du manifeste sont invalides.')
            if member.size != metadata['bytes']:
                raise ValueError('Une taille du manifeste ne correspond pas.')
            with archive.extractfile(member) as source:
                actual = hashlib.file_digest(source, 'sha256').hexdigest()
            if actual != metadata['sha256']:
                raise ValueError('Une empreinte de sauvegarde ne correspond pas.')
        for name, roots in [('media.tar.gz', {'media'}),
                            ('container-private.tar.gz', {'emails', 'runtime'}),
                            ('host-private.tar.gz', {'environment.env', 'host-runtime'})]:
            with archive.extractfile(name) as source:
                verify_file_archive(source, roots)
        return manifest


def complete_backups(directory, project):
    verified = []
    if directory.is_dir():
        for path in directory.glob('stc-full-*.tar.gz'):
            try:
                manifest = verify_bundle(path, project)
                created = datetime.fromisoformat(manifest['created_at'])
                verified.append((created, path))
            except (OSError, EOFError, ValueError, KeyError, TypeError, tarfile.TarError):
                # Never delete an unrecognized/corrupt file or count it as fresh.
                continue
    return sorted(verified, key=lambda item: item[0], reverse=True)


def check_freshness(directory, project, hours):
    backups = complete_backups(directory, project)
    if not backups:
        raise RuntimeError('Aucune sauvegarde complète STC valide trouvée.')
    created, path = backups[0]
    age = (datetime.now(timezone.utc) - created).total_seconds() / 3600
    if age < -0.1 or age > hours:
        raise RuntimeError('La dernière sauvegarde complète STC est trop ancienne ou sa date est invalide.')
    print(json.dumps({'status': 'ok', 'backup': path.name, 'age_hours': round(age, 2)}))


def full_backup(directory, compose, project, keep):
    with tempfile.TemporaryDirectory(prefix='.stc-full-staging-', dir=directory) as temporary:
        staging = Path(temporary)
        staging.chmod(0o700)
        postgres_dump(compose, staging / 'database.dump')
        for kind, name in [('media', 'media.tar.gz'), ('private', 'container-private.tar.gz')]:
            with private_output(staging / name) as output:
                run(compose + ['exec', '-T', 'backend', 'python', '-c',
                               CONTAINER_ARCHIVE, kind], output=output)
            with (staging / name).open('rb') as source:
                verify_file_archive(source, {'media'} if kind == 'media' else {'emails', 'runtime'})
        host_private_backup(staging / 'host-private.tar.gz')
        created = datetime.now(timezone.utc)
        manifest = {'kind': KIND, 'version': 1, 'project': project,
                    'created_at': created.isoformat(),
                    'files': {name: {'bytes': (staging / name).stat().st_size,
                                     'sha256': sha256(staging / name)} for name in PAYLOADS}}
        with private_output(staging / 'manifest.json') as output:
            output.write(json.dumps(manifest, indent=2).encode())
        bundle = staging / 'bundle.tar.gz'
        with private_output(bundle) as output:
            with tarfile.open(fileobj=output, mode='w:gz') as archive:
                for name in ('manifest.json', *PAYLOADS):
                    archive.add(staging / name, arcname=name, filter=safe_tar_info)
        verify_bundle(bundle, project)
        stamp = created.strftime('%Y%m%dT%H%M%S%fZ')
        target = directory / f'stc-full-{project}-{stamp}-{secrets.token_hex(3)}.tar.gz'
        checksum = staging / 'checksum'
        with private_output(checksum) as output:
            output.write(f'{sha256(bundle)}  {target.name}\n'.encode())
        publish(bundle, target)
        try:
            publish(checksum, Path(str(target) + '.sha256'))
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    for _created, old in complete_backups(directory, project)[keep:]:
        old.unlink()
        Path(str(old) + '.sha256').unlink(missing_ok=True)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres', action='store_true', help='Base du service Docker Compose db')
    parser.add_argument('--full', action='store_true', help='PostgreSQL, médias et privés avec manifeste SHA-256')
    parser.add_argument('--compose-file', action='append', help='Fichier Compose ; répéter pour un override')
    parser.add_argument('--project-name', default='stc', help='Projet Compose et propriétaire des sauvegardes')
    parser.add_argument('--directory', type=Path, help='Dossier privé ; défaut : backups/ du projet')
    parser.add_argument('--keep', type=int, default=7, help='Sauvegardes complètes de ce projet conservées')
    parser.add_argument('--check-freshness', type=float, metavar='HEURES', help='Contrôler sans Docker la dernière sauvegarde complète')
    parser.add_argument('--verify', type=Path, metavar='ARCHIVE', help='Vérifier manifeste/empreintes sans restaurer')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', args.project_name):
        parser.error('Le nom du projet Compose est invalide.')
    if args.keep < 1 or args.keep > 365:
        parser.error('--keep doit être compris entre 1 et 365.')
    if args.check_freshness is not None and not 0 < args.check_freshness <= 24 * 366:
        parser.error('--check-freshness doit être un nombre positif d’heures.')
    if args.full and not args.postgres:
        parser.error('--full demande --postgres.')
    directory = args.directory or ROOT / 'backups'
    try:
        if args.verify:
            verify_bundle(args.verify, args.project_name)
            print('Sauvegarde complète STC : manifeste et empreintes vérifiés.')
            return 0
        if args.check_freshness is not None:
            check_freshness(directory, args.project_name, args.check_freshness)
            return 0
        private_directory(directory)
        compose = compose_command(args) if args.postgres else None
        with backup_lock(directory, args.project_name):
            output = full_backup(directory, compose, args.project_name, args.keep) if args.full \
                else database_backup(directory, args.postgres, compose)
        print('Sauvegarde privée créée : ' + str(output))
        return 0
    except (OSError, EOFError, ValueError, KeyError, TypeError, RuntimeError, sqlite3.Error,
            tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, 'Sauvegarde STC refusée : ' + str(error) + '\n')


if __name__ == '__main__':
    def interrupted(_number, _frame):
        raise InterruptedError('La sauvegarde a été interrompue.')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    raise SystemExit(main())
