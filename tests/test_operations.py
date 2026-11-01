"""Operations tests use temporary files and subprocess doubles, never a real instance."""
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parent.parent


def load_script(name):
    spec = importlib.util.spec_from_file_location('stc_ops_' + name, REPO / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load_script('backup')
package = load_script('package')


def nested_archive(name):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as archive:
        content = b'synthetic-private-fixture'
        info = tarfile.TarInfo(name)
        info.mode = 0o600
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return data.getvalue()


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='stc-ops-unit-')
        self.root = Path(self.directory.name)
        (self.root / 'backend').mkdir()
        (self.root / '.runtime').mkdir()
        (self.root / '.env').write_text('SYNTHETIC_PRIVATE_CONFIG=not-real\n')
        (self.root / '.runtime' / 'credentials.txt').write_text('synthetic-private-access')
        (self.root / 'compose.yaml').write_text('services: {}\n')
        self.output = self.root / 'backups'
        backup.private_directory(self.output)
        self.overrides = [patch.object(backup, 'ROOT', self.root), patch.object(package, 'ROOT', self.root)]
        for override in self.overrides:
            override.start()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(lambda: [override.stop() for override in reversed(self.overrides)])

    def fake_dump(self, _compose, path):
        with backup.private_output(path) as stream:
            stream.write(b'synthetic-pg-dump')

    def fake_run(self, command, *, output=None, **_kwargs):
        kind = command[-1]
        output.write(nested_archive('media/fixture.txt' if kind == 'media' else 'runtime/fixture.txt'))

    def full(self, project='stc', keep=7):
        with patch.object(backup, 'postgres_dump', self.fake_dump), patch.object(backup, 'run', self.fake_run):
            return backup.full_backup(self.output, ['docker', 'compose'], project, keep)

    def test_sqlite_is_consistent_private_and_not_overwritten(self):
        source = self.root / 'backend/db.sqlite3'
        with sqlite3.connect(source) as db:
            db.execute('create table proof (value text)')
            db.execute("insert into proof values ('synthetic')")
        first = backup.database_backup(self.output, False, None)
        second = backup.database_backup(self.output, False, None)
        self.assertNotEqual(first, second)
        self.assertEqual(first.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        with sqlite3.connect(first) as db:
            self.assertEqual(db.execute('pragma integrity_check').fetchone(), ('ok',))
            self.assertEqual(db.execute('select value from proof').fetchone(), ('synthetic',))
        self.assertFalse(list(self.output.glob('.stc-db-staging-*')))

    def test_corrupt_sqlite_never_publishes_an_empty_or_partial_backup(self):
        (self.root / 'backend/db.sqlite3').write_bytes(b'broken sqlite fixture')
        existing = self.output / 'existing.sqlite3'
        existing.write_bytes(b'keep-this-file')
        with self.assertRaises(sqlite3.DatabaseError):
            backup.database_backup(self.output, False, None)
        self.assertEqual(list(self.output.iterdir()), [existing])
        self.assertEqual(existing.read_bytes(), b'keep-this-file')

    def test_symlinked_sqlite_is_refused(self):
        (self.root / 'backend/db.sqlite3').symlink_to(self.root / '.env')
        with self.assertRaises(ValueError):
            backup.database_backup(self.output, False, None)
        self.assertFalse(list(self.output.iterdir()))

    def test_backup_permissions_remain_private_under_a_restrictive_umask(self):
        with sqlite3.connect(self.root / 'backend/db.sqlite3') as db:
            db.execute('create table synthetic (value text)')
        previous = os.umask(0o777)
        try:
            path = backup.database_backup(self.output, False, None)
        finally:
            os.umask(previous)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_full_bundle_has_manifest_hashes_and_private_host_files(self):
        deploy = self.root / '.runtime/deployments'
        deploy.mkdir()
        (deploy / 'do-not-recurse.txt').write_text('not part of runtime access backup')
        path = self.full()
        manifest = backup.verify_bundle(path, 'stc')
        self.assertEqual(manifest['kind'], backup.KIND)
        self.assertEqual(set(manifest['files']), set(backup.PAYLOADS))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        checksum = Path(str(path) + '.sha256')
        self.assertEqual(checksum.stat().st_mode & 0o777, 0o600)
        self.assertEqual(checksum.read_text().split()[0], backup.sha256(path))
        with tarfile.open(path) as archive:
            self.assertTrue(all(item.mode == 0o600 for item in archive.getmembers()))
            with tarfile.open(fileobj=archive.extractfile('host-private.tar.gz'), mode='r:gz') as private:
                self.assertEqual(set(private.getnames()), {'environment.env', 'host-runtime/credentials.txt'})
        self.assertFalse(list(self.output.glob('.stc-full-staging-*')))

    def rewrite(self, path, *, corrupt_payload=False, old=False):
        with tarfile.open(path) as archive:
            files = {item.name: archive.extractfile(item).read() for item in archive.getmembers()}
        if corrupt_payload:
            files['database.dump'] += b'tamper'
        if old:
            manifest = json.loads(files['manifest.json'])
            manifest['created_at'] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            files['manifest.json'] = json.dumps(manifest).encode()
        with tarfile.open(path, 'w:gz') as archive:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.mode = 0o600
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))

    def test_manifest_detects_modified_payload_and_freshness_does_not_trust_it(self):
        path = self.full()
        self.rewrite(path, corrupt_payload=True)
        with self.assertRaises(ValueError):
            backup.verify_bundle(path, 'stc')
        with self.assertRaises(RuntimeError):
            backup.check_freshness(self.output, 'stc', 26)

    def test_internal_traversal_is_refused_even_with_matching_payload_hash(self):
        path = self.full()
        with tarfile.open(path) as archive:
            files = {item.name: archive.extractfile(item).read() for item in archive.getmembers()}
        files['media.tar.gz'] = nested_archive('../escape.txt')
        manifest = json.loads(files['manifest.json'])
        manifest['files']['media.tar.gz'] = {'bytes': len(files['media.tar.gz']), 'sha256': hashlib.sha256(files['media.tar.gz']).hexdigest()}
        files['manifest.json'] = json.dumps(manifest).encode()
        with tarfile.open(path, 'w:gz') as archive:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        with self.assertRaises(ValueError):
            backup.verify_bundle(path, 'stc')

    def test_truncated_archives_are_not_considered_fresh(self):
        path = self.full()
        data = path.read_bytes()
        path.write_bytes(data[:max(10, len(data)//2)])
        with self.assertRaises(RuntimeError):
            backup.check_freshness(self.output, 'stc', 26)

    def test_freshness_uses_manifest_date_and_requires_a_valid_bundle(self):
        with self.assertRaises(RuntimeError):
            backup.check_freshness(self.output, 'stc', 26)
        path = self.full()
        with contextlib.redirect_stdout(io.StringIO()) as log:
            backup.check_freshness(self.output, 'stc', 26)
        self.assertEqual(json.loads(log.getvalue())['status'], 'ok')
        self.rewrite(path, old=True)
        with self.assertRaises(RuntimeError):
            backup.check_freshness(self.output, 'stc', 26)

    def test_retention_is_limited_to_valid_bundles_of_the_same_project(self):
        manual = self.output / 'manual.dump'
        manual.write_bytes(b'preserve')
        unknown = self.output / 'stc-full-unknown.tar.gz'
        unknown.write_bytes(b'not our archive')
        other = self.full(project='other', keep=1)
        old = self.full(keep=2)
        self.full(keep=2)
        self.full(keep=2)
        self.assertFalse(old.exists())
        self.assertFalse(Path(str(old) + '.sha256').exists())
        self.assertEqual(len(backup.complete_backups(self.output, 'stc')), 2)
        self.assertTrue(manual.exists() and unknown.exists() and other.exists())

    def test_failure_cleans_full_staging_and_preserves_the_previous_backup(self):
        previous = self.full()
        def fail(_compose, path):
            path.write_bytes(b'partial')
            raise RuntimeError('simulated failure')
        with patch.object(backup, 'postgres_dump', fail), self.assertRaises(RuntimeError):
            backup.full_backup(self.output, ['docker'], 'stc', 7)
        self.assertTrue(previous.exists())
        self.assertFalse(list(self.output.glob('.stc-full-staging-*')))
        self.assertEqual(len(list(self.output.glob('*.tar.gz'))), 1)

    def test_private_symlink_fails_without_publishing(self):
        (self.root / '.runtime/linked.txt').symlink_to(self.root / '.env')
        with self.assertRaises(ValueError):
            self.full()
        self.assertFalse(list(self.output.iterdir()))

    def test_lock_rejects_a_second_simultaneous_backup(self):
        with backup.backup_lock(self.output, 'stc'):
            with self.assertRaises(RuntimeError):
                with backup.backup_lock(self.output, 'stc'):
                    self.fail('Second backup must not acquire the lock')

    def test_freshness_cli_never_calls_docker(self):
        self.full()
        with patch.object(backup.subprocess, 'run') as execute, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(backup.main(['--check-freshness', '26']), 0)
        execute.assert_not_called()

    def test_package_contains_vps_config_and_rejects_private_files_and_links(self):
        for name in ('compose.production.yaml', 'compose.vps.yaml', '.env.example', '.env.production.example'):
            (self.root / name).write_text('public synthetic fixture')
        for directory in package.DIRECTORIES:
            (self.root / directory).mkdir(exist_ok=True)
        private = self.root / 'backend/.private-emails'
        private.mkdir()
        (private / 'message.txt').write_text('PRIVATE')
        (self.root / 'backend/db.sqlite3').write_text('PRIVATE')
        (self.root / 'public/innocent.txt').symlink_to(self.root / '.env')
        (self.root / 'public/linked-directory').symlink_to(private, target_is_directory=True)
        (self.root / 'deploy/tls').mkdir()
        (self.root / 'deploy/tls/private.key').write_text('PRIVATE')
        (self.root / 'deploy/secret.pem').write_text('PRIVATE')
        screenshots = self.root / 'screenshots'
        screenshots.mkdir()
        approved_screenshots = ('crm-carte-1280.png', 'crm-carte-390.png',
                                'crm-commandes-390.png', 'crm-restaurant-320.png')
        for name in approved_screenshots:
            (screenshots / name).write_bytes(b'public synthetic screenshot fixture')
        (screenshots / 'private-arbitrary.png').write_bytes(b'PRIVATE')
        (screenshots / 'audit-mobile-1-accueil.png').symlink_to(self.root / '.env')
        with contextlib.redirect_stdout(io.StringIO()):
            package.main()
        path = self.root / 'artifacts/STC-livraison.zip'
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            self.assertIn('STC/compose.vps.yaml', names)
            self.assertIn('STC/compose.production.yaml', names)
            self.assertIn('STC/.env.production.example', names)
            for name in approved_screenshots:
                self.assertIn('STC/screenshots/' + name, names)
            self.assertNotIn('STC/screenshots/private-arbitrary.png', names)
            self.assertNotIn('STC/screenshots/audit-mobile-1-accueil.png', names)
            self.assertFalse(any(part in name for name in names for part in ('innocent', 'linked-directory', 'private', '.pem', 'db.sqlite3')))
            self.assertNotIn('STC/.env', names)
        expected = (self.root / 'artifacts/STC-livraison.sha256').read_text().split()[0]
        self.assertEqual(expected, backup.sha256(path))


class ConnectionPolicyTests(unittest.TestCase):
    def test_development_and_tests_disable_persistence_production_is_bounded(self):
        python = REPO / 'backend/.venv/bin/python'
        self.assertTrue(python.is_file(), 'Install backend requirements before this test.')
        with tempfile.TemporaryDirectory(prefix='stc-settings-policy-') as directory:
            root = Path(directory)
            config = root / 'backend/config'
            config.mkdir(parents=True)
            fixture = config / 'settings.py'
            shutil.copy2(REPO / 'backend/config/settings.py', fixture)
            script = "import importlib.util,json,sys;sys.argv=['audit',*sys.argv[1:]];s=importlib.util.spec_from_file_location('isolated_settings',sys.argv[-1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.DATABASES['default']['CONN_MAX_AGE'])"
            for debug, explicit, testing, expected in [('1', None, False, 0), ('1', '120', False, 0), ('0', None, False, 60), ('0', '0', False, 0), ('0', '120', False, 120), ('0', '120', True, 0)]:
                with self.subTest(debug=debug, explicit=explicit, testing=testing):
                    env = {**os.environ, 'DJANGO_DEBUG': debug, 'DJANGO_SECRET_KEY': 'settings-policy-synthetic-secret',
                           'DATABASE_URL': 'sqlite:///:memory:', 'STC_DEMO_MODE': '1', 'STC_PAYMENT_MODE': 'on_site',
                           'STRIPE_SECRET_KEY': '', 'STRIPE_WEBHOOK_SECRET': '',
                           'STC_EMAIL_FILE_PATH': str(root / 'emails'), 'STC_RUNTIME_DIR': str(root / 'runtime')}
                    env.pop('DJANGO_DB_CONN_MAX_AGE', None)
                    if explicit is not None:
                        env['DJANGO_DB_CONN_MAX_AGE'] = explicit
                    result = subprocess.run([str(python), '-c', script, *(['test'] if testing else []), str(fixture)], env=env, cwd=root, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(int(result.stdout.strip()), expected)


if __name__ == '__main__':
    unittest.main()
