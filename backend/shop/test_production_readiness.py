import io
import json
from datetime import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from .models import Category, OpeningHour, Product, Restaurant, User
from .production_readiness import backup_status, database_status, probe_smtp, probe_url, production_report
from .public_details import public_details, public_email, public_phone, public_url


COMPLETE = {
    'SECRET_KEY': 'must-never-serialize-a-django-secret-of-at-least-fifty-characters-fixture-only',
    'DEBUG': False, 'DEMO_MODE': False, 'PAYMENT_MODE': 'on_site',
    'FRONTEND_URL': 'https://restaurant.fr', 'ALLOWED_HOSTS': ['restaurant.fr'],
    'CSRF_TRUSTED_ORIGINS': ['https://restaurant.fr'], 'SECURE_SSL_REDIRECT': True,
    'SESSION_COOKIE_SECURE': True, 'CSRF_COOKIE_SECURE': True,
    'STC_CONTACT_PHONE': '+33 1 23 45 67 89', 'STC_CONTACT_EMAIL': 'bonjour@restaurant.fr',
    'STC_LEGAL_NOTICE_URL': 'https://restaurant.fr/mentions-legales',
    'STC_PRIVACY_URL': 'https://restaurant.fr/confidentialite',
    'STC_TERMS_URL': 'https://restaurant.fr/conditions', 'STC_CONTENT_APPROVED': True,
    'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend', 'EMAIL_HOST': 'smtp.restaurant.fr',
    'EMAIL_PORT': 587, 'EMAIL_HOST_USER': 'private-fixture-user', 'EMAIL_HOST_PASSWORD': 'private-fixture-password',
    'EMAIL_USE_TLS': True, 'DEFAULT_FROM_EMAIL': 'Restaurant <bonjour@restaurant.fr>',
    'ORDER_NOTIFICATION_EMAILS': ['equipe@restaurant.fr'],
}


@override_settings(**COMPLETE)
class ProductionReadinessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restaurant = Restaurant.objects.create(pk=1, name='Restaurant de recette', address='1 place du Test', city='Lyon', delivery_enabled=False)
        OpeningHour.objects.create(restaurant=cls.restaurant, weekday=0, opens=time(12), closes=time(14))
        category = Category.objects.create(name='Recettes')
        Product.objects.create(name='Plat de recette', category=category, price='12.50', description='Description de recette')
        cls.manager = User.objects.create_user('camille@restaurant.fr', 'fixture-password', first_name='Camille', last_name='Martin', is_staff=True)
        cls.manager.user_permissions.add(*Permission.objects.filter(content_type__app_label='shop', codename__in=['view_order', 'change_order', 'record_onsite_payment']))

    def report(self, **kwargs):
        # PostgreSQL availability and backup files are mocked here. Actual DB reads
        # (catalogue, schedule, staff permissions) use the isolated test database.
        with patch('shop.production_readiness.database_status', return_value=[{'id': 'database', 'status': 'pass', 'message': 'Fixture PostgreSQL.'}]), \
             patch('shop.production_readiness.backup_status', return_value=True):
            return production_report(**kwargs)

    def test_complete_configuration_passes_without_claiming_external_acceptance(self):
        report = self.report()
        self.assertTrue(report['configurationReady'])
        self.assertNotIn('productionReady', report)
        self.assertEqual(set(report['externalChecks'].values()), {'not_checked'})
        self.assertTrue(report['limitations'])

    def test_missing_client_data_and_approval_are_blockers(self):
        with override_settings(STC_CONTACT_PHONE='', STC_CONTACT_EMAIL='', STC_CONTENT_APPROVED=False,
                               STC_LEGAL_NOTICE_URL='', STC_PRIVACY_URL='', STC_TERMS_URL=''):
            report = self.report()
        blockers = {row['id'] for row in report['checks'] if row['status'] == 'blocker'}
        self.assertFalse(report['configurationReady'])
        self.assertTrue({'contactPhone', 'contactEmail', 'legalNoticeUrl', 'privacyUrl', 'termsUrl', 'content_approved'} <= blockers)

    def test_demo_mode_bad_hosts_and_unencrypted_smtp_are_blockers(self):
        with override_settings(DEBUG=True, DEMO_MODE=True, PAYMENT_MODE='simulation', ALLOWED_HOSTS=['*'], EMAIL_USE_TLS=False, SECRET_KEY='REPLACE_WITH_A_RANDOM_SECRET'):
            report = self.report()
        blockers = {row['id'] for row in report['checks'] if row['status'] == 'blocker'}
        self.assertTrue({'debug', 'demo', 'payment_mode', 'https_hosts', 'smtp_config', 'secret_key'} <= blockers)

    def test_exact_public_domain_allows_only_the_three_internal_health_aliases(self):
        for hosts in (['restaurant.fr'], ['restaurant.fr', 'backend'],
                      ['restaurant.fr', 'localhost'], ['restaurant.fr', '127.0.0.1'],
                      ['restaurant.fr', 'backend', 'localhost', '127.0.0.1']):
            with self.subTest(hosts=hosts), override_settings(ALLOWED_HOSTS=hosts):
                result = next(row for row in self.report()['checks'] if row['id'] == 'https_hosts')
                self.assertEqual(result['status'], 'pass')

    def test_hosts_reject_missing_public_domain_wildcards_and_any_other_alias(self):
        rejected = (
            ['backend', 'localhost', '127.0.0.1'], ['another.fr', 'backend'],
            ['restaurant.fr', '*'], ['restaurant.fr', '*.restaurant.fr'],
            ['restaurant.fr', '.restaurant.fr'], ['restaurant.fr', 'another.fr'],
            ['restaurant.fr', 'www.restaurant.fr'], ['restaurant.fr', 'untrusted-internal'],
            ['restaurant.fr', '10.0.0.1'], ['restaurant.fr', '127.0.0.2'],
            ['restaurant.fr', '::1'], ['restaurant.fr', 'host.docker.internal'],
            ['restaurant.fr', 'backend.evil.fr'], ['restaurant.fr', 'localhost.evil.fr'],
        )
        for hosts in rejected:
            with self.subTest(hosts=hosts), override_settings(ALLOWED_HOSTS=hosts):
                result = next(row for row in self.report()['checks'] if row['id'] == 'https_hosts')
                self.assertEqual(result['status'], 'blocker')

    def test_shared_demo_account_detected_without_printing_identity(self):
        User.objects.create_user('demo.crm@stc.example', 'private-demo-password', is_staff=True)
        report = self.report()
        self.assertFalse(report['configurationReady'])
        self.assertEqual(next(row for row in report['checks'] if row['id'] == 'shared_demo_staff')['status'], 'blocker')
        self.assertNotIn('demo.crm@stc.example', json.dumps(report))

    def test_financial_permission_requires_nominal_active_staff(self):
        for field, value in [('last_name', ''), ('is_active', False), ('is_staff', False)]:
            with self.subTest(field=field):
                User.objects.filter(pk=self.manager.pk).update(**{field: value})
                self.assertEqual(next(row for row in self.report()['checks'] if row['id'] == 'financial_staff')['status'], 'blocker')
                User.objects.filter(pk=self.manager.pk).update(last_name='Martin', is_active=True, is_staff=True)
        self.manager.user_permissions.remove(Permission.objects.get(content_type__app_label='shop', codename='record_onsite_payment'))
        self.assertEqual(next(row for row in self.report()['checks'] if row['id'] == 'financial_staff')['status'], 'blocker')

    def test_database_failure_does_not_leak_connection_secrets(self):
        with patch('shop.production_readiness.database_status', side_effect=RuntimeError('postgres://private-user:private-password@private-host/db')), \
             patch('shop.production_readiness.backup_status', return_value=True):
            report = production_report()
        text = json.dumps(report)
        self.assertFalse(report['configurationReady'])
        self.assertNotIn('private-password', text)
        self.assertNotIn('private-user', text)
        self.assertNotIn('private-host', text)

    def test_optional_probes_are_explicit_and_do_not_send_email(self):
        with patch('shop.production_readiness.probe_url', return_value=True) as url, \
             patch('shop.production_readiness.probe_smtp', return_value=True) as smtp:
            report = self.report(check_urls=True, smtp_check=True)
        self.assertTrue(report['configurationReady'])
        self.assertEqual(url.call_count, 4)
        smtp.assert_called_once()
        self.assertEqual(report['externalChecks']['https'], 'pass')
        self.assertEqual(report['externalChecks']['smtpConnection'], 'pass')
        self.assertEqual(report['externalChecks']['emailDelivery'], 'not_checked')
        self.assertEqual(report['externalChecks']['offsiteBackup'], 'not_checked')

    def test_probe_failure_is_generic_and_blocks(self):
        with patch('shop.production_readiness.probe_url', return_value=False), \
             patch('shop.production_readiness.probe_smtp', side_effect=RuntimeError('private-fixture-password')):
            report = self.report(check_urls=True, smtp_check=True)
        self.assertFalse(report['configurationReady'])
        self.assertNotIn('private-fixture-password', json.dumps(report))

    def test_command_json_is_read_only_and_exits_nonzero_on_blockers(self):
        output = io.StringIO()
        with override_settings(STC_CONTENT_APPROVED=False), patch('shop.production_readiness.backup_status', return_value=True), CaptureQueriesContext(connection) as queries:
            with self.assertRaises(CommandError):
                call_command('check_production', as_json=True, stdout=output)
        report = json.loads(output.getvalue())
        self.assertFalse(report['configurationReady'])
        self.assertTrue(any(row['id'] == 'content_approved' and row['status'] == 'blocker' for row in report['checks']))
        for query in queries:
            self.assertNotRegex(query['sql'].lstrip().upper(), r'^(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b')

    def test_command_success_and_failure_keep_json_machine_readable(self):
        for ready in (True, False):
            output = io.StringIO()
            payload = {'configurationReady': ready, 'checks': [], 'externalChecks': {}, 'limitations': []}
            with patch('shop.management.commands.check_production.production_report', return_value=payload):
                if ready:
                    call_command('check_production', as_json=True, stdout=output)
                else:
                    with self.assertRaises(CommandError):
                        call_command('check_production', as_json=True, stdout=output)
            self.assertEqual(json.loads(output.getvalue()), payload)

    def test_command_rejects_invalid_backup_options_before_subprocess(self):
        for kwargs in ({'backup_project': '--invalid'}, {'backup_max_age': float('nan')}, {'backup_max_age': 0}):
            with self.subTest(kwargs=kwargs), patch('shop.management.commands.check_production.production_report') as report:
                with self.assertRaises(CommandError):
                    call_command('check_production', **kwargs)
                report.assert_not_called()

    def test_configuration_and_public_api_never_expose_private_settings(self):
        details = public_details()
        self.assertEqual(set(details), {'contactPhone', 'contactEmail', 'legalNoticeUrl', 'privacyUrl', 'termsUrl'})
        response = self.client.get('/api/restaurant/', secure=True, HTTP_HOST='restaurant.fr')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['contactEmail'], COMPLETE['STC_CONTACT_EMAIL'])
        serialized = json.dumps(response.json()) + json.dumps(self.report())
        for secret in ('private-fixture-user', 'private-fixture-password', COMPLETE['SECRET_KEY']):
            self.assertNotIn(secret, serialized)
        self.assertNotIn('STC_CONTENT_APPROVED', response.json())
        self.assertNotIn('contentApproved', response.json())

    def test_empty_database_does_not_create_restaurant_or_other_data(self):
        Product.objects.all().delete()
        OpeningHour.objects.all().delete()
        Restaurant.objects.all().delete()
        before = (Restaurant.objects.count(), Product.objects.count(), User.objects.count())
        self.assertFalse(self.report()['configurationReady'])
        self.assertEqual(before, (Restaurant.objects.count(), Product.objects.count(), User.objects.count()))

    def test_migration_check_uses_plan_and_never_runs_migrate(self):
        executor = MagicMock()
        executor.migration_plan.return_value = [('migration', False)]
        with patch('shop.production_readiness.MigrationExecutor', return_value=executor):
            rows = database_status()
        self.assertEqual(next(row for row in rows if row['id'] == 'migrations')['status'], 'blocker')
        executor.migrate.assert_not_called()

    def test_backup_probe_consumes_only_cli_success_and_redacts_errors(self):
        with patch('shop.production_readiness.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='{"status":"ok","backup":"private-name"}')) as run:
            self.assertTrue(backup_status(Path('/private-backups'), 'stc', 26))
        args = run.call_args.args[0]
        self.assertIn('--check-freshness', args)
        self.assertNotIn('--full', args)
        for result in (SimpleNamespace(returncode=1, stdout='private-password'), SimpleNamespace(returncode=0, stdout='[]'), SimpleNamespace(returncode=0, stdout='broken')):
            with patch('shop.production_readiness.subprocess.run', return_value=result):
                self.assertFalse(backup_status(Path('/private-backups'), 'stc', 26))

    def test_smtp_probe_opens_and_closes_without_sending(self):
        backend = MagicMock()
        backend.open.return_value = True
        with patch('shop.production_readiness.get_connection', return_value=backend):
            self.assertTrue(probe_smtp())
        backend.open.assert_called_once()
        backend.close.assert_called_once()
        backend.send_messages.assert_not_called()

    def test_url_probe_refuses_private_addresses_redirects_and_invalid_schemes(self):
        with patch('shop.production_readiness.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]), \
             patch('shop.production_readiness.build_opener') as opener:
            self.assertFalse(probe_url('https://restaurant.fr/mentions'))
            opener.assert_not_called()
        for value in ('javascript:alert(1)', 'http://restaurant.fr/', 'https://127.0.0.1/', 'https://user:secret@restaurant.fr/'):
            with self.subTest(value=value), patch('shop.production_readiness.socket.getaddrinfo') as dns:
                self.assertFalse(probe_url(value))
                dns.assert_not_called()


class PublicDetailsValidationTests(TestCase):
    def test_invalid_document_urls_and_placeholder_domains_are_hidden(self):
        for value in ('javascript:alert(1)', 'data:text/plain,test', 'http://restaurant.fr/', '//restaurant.fr/legal',
                      'https://restaurant.fr:8443/', 'https://user:private-password@restaurant.fr/', 'https://localhost/',
                      'https://127.0.0.1/', 'https://10.0.0.1/', 'https://restaurant.example.com/', 'https://restaurant.fr/\nsecret'):
            with self.subTest(value=value):
                self.assertEqual(public_url(value), '')
        self.assertEqual(public_url('https://restaurant.fr/mentions-legales'), 'https://restaurant.fr/mentions-legales')

    def test_invalid_phone_and_email_are_hidden(self):
        for value in ('javascript:12345678', '06\n12345678', '12', '1234567890123456'):
            self.assertEqual(public_phone(value), '')
        for value in ('hello@example.com', 'a@localhost', 'a@restaurant.fr?body=private', 'a@restaurant.fr\nBcc:b@restaurant.fr'):
            self.assertEqual(public_email(value), '')

    @override_settings(STC_LEGAL_NOTICE_URL='javascript:alert(1)', STC_CONTACT_EMAIL='bad', STC_CONTACT_PHONE='bad')
    def test_public_details_omits_invalid_values(self):
        self.assertEqual(public_details()['legalNoticeUrl'], '')
        self.assertEqual(public_details()['contactEmail'], '')
        self.assertEqual(public_details()['contactPhone'], '')
