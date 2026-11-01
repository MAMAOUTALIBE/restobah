"""Opt-in real backup/restore and volume persistence, always on a disposable project."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('stc_backup_docker_test', REPO / 'scripts/backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


@unittest.skipUnless(os.getenv('STC_RUN_DOCKER_TESTS') == '1', 'Opt-in: disposable Docker project only')
class DockerOperationsTests(unittest.TestCase):
    def test_private_volumes_recreate_and_full_backup_restores(self):
        project = 'stc-ops-test-' + secrets.token_hex(5)
        image = os.getenv('STC_OPS_BACKEND_IMAGE', 'stc-backend')
        image_id = subprocess.check_output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], text=True).strip()
        with tempfile.TemporaryDirectory(prefix='stc-ops-docker-') as directory:
            root = Path(directory)
            root.chmod(0o700)
            for name in ('compose.yaml', 'compose.vps.yaml', 'compose.production.yaml'):
                shutil.copy2(REPO / name, root / name)
            (root / '.env').write_text('\n'.join([
                'POSTGRES_PASSWORD=synthetic-ops-only', 'DJANGO_SECRET_KEY=synthetic-ops-only',
                'DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend',
                'DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost',
                'FRONTEND_URL=http://localhost', 'STC_DOMAIN=audit.example.invalid',
                'STC_DEMO_MODE=1', 'STC_PAYMENT_MODE=simulation',
            ]) + '\n')
            (root / '.env').chmod(0o600)
            (root / '.runtime').mkdir(mode=0o700)
            (root / '.runtime/credentials.txt').write_text('synthetic-access')
            media_config = root / 'ops-media.conf'
            media_config.write_text('server { listen 80; location /media/ { alias /media/; } }\n')
            (root / 'ops.override.json').write_text(json.dumps({'services': {
                'backend': {
                    'image': image_id, 'pull_policy': 'never', 'entrypoint': [], 'command': ['sleep', 'infinity'],
                    'healthcheck': {'disable': True},
                },
                'ops-media': {
                    'image': 'nginx:1.28-alpine', 'pull_policy': 'never',
                    'volumes': ['stc-media:/media:ro', {
                        'type': 'bind', 'source': str(media_config.resolve()),
                        'target': '/etc/nginx/conf.d/default.conf', 'read_only': True,
                    }],
                    'healthcheck': {
                        'test': ['CMD', 'wget', '-q', '--spider', 'http://127.0.0.1/media/products/ops-fixture.txt'],
                        'interval': '1s', 'timeout': '2s', 'retries': 20,
                    },
                },
            }}))
            compose = ['docker', 'compose', '--project-directory', str(root), '--project-name', project,
                       '-f', str(root / 'compose.yaml'), '-f', str(root / 'ops.override.json')]
            def execute(arguments, **kwargs):
                try:
                    return subprocess.run(compose + arguments, cwd=root, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, check=True, timeout=120, **kwargs)
                except subprocess.CalledProcessError as error:
                    raise AssertionError(error.stderr.decode(errors='replace')) from error
            try:
                for override in ('compose.vps.yaml', 'compose.production.yaml'):
                    config = subprocess.run(['docker', 'compose', '--project-directory', str(root), '--project-name', project,
                                             '-f', str(root / 'compose.yaml'), '-f', str(root / override),
                                             'config', '--format', 'json'], cwd=root, capture_output=True, text=True, check=True)
                    services = json.loads(config.stdout)['services']
                    targets = {entry['target'] for entry in services['backend']['volumes']}
                    self.assertTrue({'/app/.runtime', '/app/.private-emails'}.issubset(targets))
                    frontend_targets = {entry['target'] for entry in services['frontend']['volumes']}
                    self.assertFalse({'/app/.runtime', '/app/.private-emails'} & frontend_targets)

                execute(['up', '-d', '--no-build', '--no-deps', '--wait', '--wait-timeout', '90', 'db', 'backend'])
                first = execute(['ps', '-q', 'backend']).stdout.decode().strip()
                write = """import os
from pathlib import Path
os.umask(0o077)
for directory in ('/app/media','/app/.runtime','/app/.private-emails'):
    path=Path(directory)
    assert path.stat().st_uid==10001,(directory,'uid',path.stat().st_uid)
    if '/app/media'!=directory: assert path.stat().st_mode&0o777==0o700,(directory,'mode',oct(path.stat().st_mode&0o777))
    marker=path/'ops-fixture.txt';marker.write_text('synthetic-marker');os.chmod(marker,0o644 if directory=='/app/media' else 0o600)
    if directory=='/app/media':
        nested=path/'products';nested.mkdir(mode=0o755);nested.chmod(0o755)
        photo=nested/'ops-fixture.txt';photo.write_text('synthetic-photo');photo.chmod(0o644)
"""
                execute(['exec', '-T', 'backend', 'python', '-c', write])
                execute(['exec', '-T', 'db', 'psql', '-U', 'stc', '-d', 'stc', '-c',
                         "CREATE TABLE ops_fixture (id integer primary key, value text); INSERT INTO ops_fixture VALUES (1,'synthetic-row');"])
                execute(['up', '-d', '--no-build', '--no-deps', '--force-recreate', '--wait', 'backend'])
                second = execute(['ps', '-q', 'backend']).stdout.decode().strip()
                self.assertNotEqual(first, second)
                read = """from pathlib import Path
for directory in ('/app/media','/app/.runtime','/app/.private-emails'):
    path=Path(directory);marker=path/'ops-fixture.txt'
    assert marker.read_text()=='synthetic-marker' and marker.stat().st_mode&0o777==(0o644 if directory=='/app/media' else 0o600)
    if '/app/media'!=directory: assert path.stat().st_mode&0o777==0o700
    assert path.stat().st_uid==10001
print('PRIVATE_PERSISTENCE_PASS')
"""
                self.assertIn(b'PRIVATE_PERSISTENCE_PASS', execute(['exec', '-T', 'backend', 'python', '-c', read]).stdout)
                with patch.object(backup, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(backup.main(['--postgres', '--full', '--project-name', project,
                                                  '--compose-file', 'compose.yaml', '--compose-file', 'ops.override.json']), 0)
                    self.assertEqual(backup.main(['--project-name', project, '--check-freshness', '26']), 0)
                bundles = list((root / 'backups').glob('*.tar.gz'))
                self.assertEqual(len(bundles), 1)
                manifest = backup.verify_bundle(bundles[0], project)
                self.assertEqual(set(manifest['files']), set(backup.PAYLOADS))
                self.assertEqual(bundles[0].stat().st_mode & 0o777, 0o600)
                # The release precheck reads host backups through a one-off, read-only
                # root mount; the public application keeps running as UID 10001.
                audit_container = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
                                   '--user', '0', '--mount',
                                   f'type=bind,src={(root / "backups").resolve()},dst=/audit-backups,readonly']
                cli = subprocess.run(audit_container + [image_id, 'python', '/app/scripts/backup.py',
                                     '--directory', '/audit-backups', '--project-name', project,
                                     '--check-freshness', '26'], capture_output=True, text=True, timeout=90)
                self.assertEqual(cli.returncode, 0, cli.stderr)
                self.assertEqual(json.loads(cli.stdout)['status'], 'ok')
                precheck = subprocess.run(audit_container + ['--tmpfs', '/tmp:rw,nosuid,noexec,size=32m',
                    '-e', 'DATABASE_URL=sqlite:///:memory:', '-e', 'DJANGO_DEBUG=0',
                    '-e', 'DJANGO_SECRET_KEY=synthetic-private-precheck-secret-never-print-in-report',
                    '-e', 'STC_EMAIL_FILE_PATH=/tmp/emails', '-e', 'STC_DEMO_MODE=1',
                    '-e', 'STC_PAYMENT_MODE=simulation', image_id, 'python', 'manage.py', 'check_production',
                    '--json', '--backup-directory', '/audit-backups', '--backup-project', project],
                    capture_output=True, text=True, timeout=90)
                # No client setup is supplied: the command must report blockers and
                # still validate the real backup via the helper packaged in the image.
                self.assertEqual(precheck.returncode, 1, precheck.stderr)
                report = json.loads(precheck.stdout)
                self.assertFalse(report['configurationReady'])
                self.assertEqual(next(check for check in report['checks']
                                      if check['id'] == 'backup_freshness')['status'], 'pass')
                self.assertEqual(report['externalChecks']['emailDelivery'], 'not_checked')
                for private in ('synthetic-ops-only', 'synthetic-access',
                                'synthetic-private-precheck-secret-never-print-in-report'):
                    self.assertNotIn(private, precheck.stdout + precheck.stderr)
                execute(['exec', '-T', 'db', 'createdb', '-U', 'stc', 'restore_fixture'])
                with tarfile.open(bundles[0]) as archive:
                    with archive.extractfile('database.dump') as dump:
                        execute(['exec', '-T', 'db', 'pg_restore', '-U', 'stc', '-d', 'restore_fixture',
                                 '--no-owner', '--exit-on-error'], input=dump.read())
                    for name, markers in [('media.tar.gz', ['media/ops-fixture.txt', 'media/products/ops-fixture.txt']),
                                          ('container-private.tar.gz', ['runtime/ops-fixture.txt', 'emails/ops-fixture.txt'])]:
                        with tarfile.open(fileobj=archive.extractfile(name), mode='r:gz') as files:
                            for marker in markers:
                                self.assertEqual(files.extractfile(marker).read(),
                                                 b'synthetic-photo' if '/products/' in marker else b'synthetic-marker')
                                self.assertEqual(files.getmember(marker).mode, 0o600)
                        # Actually restore files after removing the originals. Archives stay
                        # private; only public photos regain permissions readable by nginx.
                        restore = """import os,sys,tarfile
from pathlib import Path,PurePosixPath
public=sys.argv[1]=='media'
roots={'media':Path('/app/media')} if public else {'runtime':Path('/app/.runtime'),'emails':Path('/app/.private-emails')}
for root in roots.values():
    marker=root/'ops-fixture.txt';marker.unlink();assert not marker.exists()
    if public:
        photo=root/'products/ops-fixture.txt';photo.unlink();assert not photo.exists()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as files:
    for member in files:
        parts=PurePosixPath(member.name).parts
        assert parts and parts[0] in roots and '..' not in parts and not member.name.startswith('/')
        target=roots[parts[0]].joinpath(*parts[1:])
        if member.isdir():
            target.mkdir(parents=True,exist_ok=True);target.chmod(0o700)
        else:
            assert member.isfile()
            with files.extractfile(member) as source,target.open('wb') as output:
                output.write(source.read())
            target.chmod(0o600)
        assert target.stat().st_uid==10001
"""
                        execute(['exec', '-T', 'backend', 'python', '-c', restore,
                                 'media' if name == 'media.tar.gz' else 'private'],
                                input=archive.extractfile(name).read())
                    with tarfile.open(fileobj=archive.extractfile('host-private.tar.gz'), mode='r:gz') as files:
                        restored_host = root / 'restored-host'
                        restored_host.mkdir(mode=0o700)
                        previous = os.umask(0o077)
                        try:
                            files.extractall(restored_host, filter='data')
                        finally:
                            os.umask(previous)
                        credentials = restored_host / 'host-runtime/credentials.txt'
                        self.assertEqual(credentials.read_bytes(), b'synthetic-access')
                        self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
                        self.assertEqual((restored_host / 'host-runtime').stat().st_mode & 0o777, 0o700)
                unreadable = execute(['exec', '-T', '--user', '101:101', 'backend', 'python', '-c',
                    "import os;assert not os.access('/app/media/products/ops-fixture.txt',os.R_OK)"])
                self.assertEqual(unreadable.returncode, 0)
                procedure = (REPO / 'docs/BACKUPS.md').read_text().split("backend sh -eu -c '\n", 1)[1].split("\n'", 1)[0]
                # Execute the exact documented permission normalization, inside this
                # disposable project rather than the example/production project.
                execute(['exec', '-T', '--user', '0', 'backend', 'sh', '-eu', '-c', procedure])
                self.assertIn(b'PRIVATE_PERSISTENCE_PASS', execute(['exec', '-T', 'backend', 'python', '-c', read]).stdout)
                backend_write = """import os
from pathlib import Path
assert os.getuid()==10001
assert Path('/app/media/products/ops-fixture.txt').read_text()=='synthetic-photo'
os.umask(0o077)
for name in ('media','.runtime','.private-emails'):
    proof=Path('/app')/name/'write-proof.txt';proof.write_text('synthetic-write');proof.unlink()
"""
                execute(['exec', '-T', 'backend', 'python', '-c', backend_write])
                frontend_read = """import os
from pathlib import Path
assert os.getuid()==101
assert Path('/app/media/ops-fixture.txt').read_text()=='synthetic-marker'
assert Path('/app/media/products/ops-fixture.txt').read_text()=='synthetic-photo'
assert not os.access('/app/media/products',os.W_OK)
assert not os.access('/app/media/products/ops-fixture.txt',os.W_OK)
for root in ('/app/.runtime','/app/.private-emails'):
    try: (Path(root)/'ops-fixture.txt').read_bytes()
    except PermissionError: pass
    else: raise AssertionError('A public worker can read private files')
print('RESTORED_MEDIA_READABLE_AND_PRIVATE_FILES_DENIED_PASS')
"""
                self.assertIn(b'RESTORED_MEDIA_READABLE_AND_PRIVATE_FILES_DENIED_PASS', execute([
                    'exec', '-T', '--user', '101:101', 'backend', 'python', '-c', frontend_read]).stdout)
                execute(['up', '-d', '--no-build', '--no-deps', '--wait', '--wait-timeout', '90', 'ops-media'])
                self.assertEqual(execute(['exec', '-T', 'ops-media', 'id', '-u', 'nginx']).stdout.strip(), b'101')
                served = execute(['exec', '-T', 'backend', 'python', '-c',
                    "import urllib.request;assert urllib.request.urlopen('http://ops-media/media/products/ops-fixture.txt').read()==b'synthetic-photo';print('RESTORED_PHOTO_HTTP_PASS')"])
                self.assertIn(b'RESTORED_PHOTO_HTTP_PASS', served.stdout)
                count = execute(['exec', '-T', 'db', 'psql', '-U', 'stc', '-d', 'restore_fixture',
                                 '-Atc', 'SELECT count(*) FROM ops_fixture']).stdout.decode().strip()
                self.assertEqual(count, '1')
                print('ISOLATED_COMPOSE_PRIVATE_PERSISTENCE_AND_FULL_PG_RESTORE_PASS')
            finally:
                subprocess.run(compose + ['down', '--volumes', '--remove-orphans'], cwd=root,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


if __name__ == '__main__':
    unittest.main()
