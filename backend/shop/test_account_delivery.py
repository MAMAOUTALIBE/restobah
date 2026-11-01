"""Delivery readiness never leaks credentials or claims an e-mail was received."""
import io
import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from .account_links import account_delivery_report, frontend_base_url, password_reset_available, password_reset_link


COMPLETE = {
    'DEBUG': False, 'FRONTEND_URL': 'https://restaurant.fr',
    'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
    'EMAIL_HOST': 'smtp.restaurant.fr', 'EMAIL_PORT': 587,
    'EMAIL_HOST_USER': 'private-fixture-user', 'EMAIL_HOST_PASSWORD': 'must-not-appear-in-output',
    'EMAIL_USE_TLS': True, 'EMAIL_USE_SSL': False,
    'DEFAULT_FROM_EMAIL': 'Restaurant <bonjour@restaurant.fr>',
}


@override_settings(**COMPLETE)
class AccountDeliveryConfigurationTests(SimpleTestCase):
    def test_origin_and_encoded_reset_parameters_are_separate(self):
        link = password_reset_link('uid-value', 'token&unsafe=value')
        self.assertEqual(link, 'https://restaurant.fr/?reset_uid=uid-value&reset_token=token%26unsafe%3Dvalue')
        self.assertTrue(password_reset_available())

    def test_unsafe_origins_never_become_account_links(self):
        rejected = ['http://restaurant.fr', 'javascript:alert(1)', 'https://user:password@restaurant.fr',
                    'https://restaurant.fr/?token=private', 'https://restaurant.fr/#private',
                    'https://restaurant.fr/some-path', 'https://restaurant.fr:8443',
                    'https://127.0.0.1', 'http://localhost:5173', 'https://restaurant.example.com',
                    'https://restaurant.fr\n', 'https://restaurant.fr:99999']
        for value in rejected:
            with self.subTest(value=value), override_settings(FRONTEND_URL=value):
                with self.assertRaises(ValueError):
                    frontend_base_url()
                self.assertFalse(password_reset_available())

    def test_development_and_private_files_do_not_imply_public_delivery(self):
        with override_settings(DEBUG=True, FRONTEND_URL='http://localhost:5191',
                               EMAIL_BACKEND='shop.email_backend.PrivateFileEmailBackend'):
            self.assertTrue(password_reset_available())
            self.assertEqual(frontend_base_url(), 'http://localhost:5191')
        with override_settings(DEBUG=False, FRONTEND_URL='http://localhost:5191',
                               EMAIL_BACKEND='shop.email_backend.PrivateFileEmailBackend'):
            self.assertEqual(frontend_base_url(), 'http://localhost:5191')
            self.assertFalse(password_reset_available())
            self.assertFalse(account_delivery_report()['configurationReady'])

    def test_tls_and_ssl_are_mutually_exclusive(self):
        for tls, ssl in [(False, False), (True, True)]:
            with self.subTest(tls=tls, ssl=ssl), override_settings(EMAIL_USE_TLS=tls, EMAIL_USE_SSL=ssl):
                self.assertFalse(password_reset_available())
                self.assertFalse(account_delivery_report()['configurationReady'])
        with override_settings(EMAIL_USE_TLS=False, EMAIL_USE_SSL=True, EMAIL_PORT=465):
            self.assertTrue(account_delivery_report()['configurationReady'])

    @patch('shop.account_links.probe_smtp')
    @patch('shop.account_links.probe_url')
    def test_default_report_does_not_probe_or_send(self, url, smtp):
        with patch('django.core.mail.send_mail') as send:
            report = account_delivery_report()
            self.assertTrue(report['configurationReady'])
            self.assertEqual(set(report['externalChecks'].values()), {'not_checked'})
            url.assert_not_called()
            smtp.assert_not_called()
            send.assert_not_called()

    @patch('shop.account_links.probe_smtp', return_value=True)
    @patch('shop.account_links.probe_url', return_value=True)
    def test_explicit_probes_do_not_claim_delivery(self, url, smtp):
        report = account_delivery_report(check_url=True, smtp_check=True)
        self.assertTrue(report['configurationReady'])
        self.assertEqual(report['externalChecks'], {'siteHttps': 'pass', 'smtpConnection': 'pass', 'emailDelivery': 'not_checked'})
        url.assert_called_once_with('https://restaurant.fr/')
        smtp.assert_called_once_with()

    @patch('shop.account_links.probe_smtp', side_effect=RuntimeError('must-not-appear-in-output'))
    @patch('shop.account_links.probe_url', return_value=False)
    def test_probe_errors_remain_generic(self, url, smtp):
        report = account_delivery_report(check_url=True, smtp_check=True)
        self.assertFalse(report['configurationReady'])
        output = json.dumps(report)
        self.assertNotIn(settings.EMAIL_HOST_PASSWORD, output)
        self.assertNotIn(settings.EMAIL_HOST_USER, output)
        self.assertEqual(report['externalChecks']['emailDelivery'], 'not_checked')

    def test_command_outputs_read_only_json_and_rejects_missing_configuration(self):
        output = io.StringIO()
        call_command('check_account_delivery', '--json', stdout=output)
        self.assertTrue(json.loads(output.getvalue())['configurationReady'])
        with override_settings(EMAIL_HOST_PASSWORD=''):
            output = io.StringIO()
            with self.assertRaises(CommandError) as rejected:
                call_command('check_account_delivery', '--json', stdout=output)
            self.assertEqual(rejected.exception.returncode, 1)
            self.assertFalse(json.loads(output.getvalue())['configurationReady'])


@override_settings(DEBUG=True, FRONTEND_URL='http://localhost:5173',
                   DEMO_MODE=True, PAYMENT_MODE='simulation',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountDeliveryAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('delivery-test@example.invalid', 'Delivery-Strong!52x7')
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.get('/api/auth/csrf/')
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def test_capabilities_are_anonymous_private_and_do_not_disclose_settings(self):
        response = self.client.get('/api/auth/capabilities/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'passwordResetAvailable': True})
        self.assertIn('no-store', response['Cache-Control'])
        with override_settings(DEBUG=False):
            self.assertEqual(self.client.get('/api/auth/capabilities/').json(), {'passwordResetAvailable': False})
        self.assertEqual(self.client.post('/api/auth/capabilities/', {}, format='json').status_code, 405)

    def test_reset_keeps_generic_contract_when_origin_is_invalid(self):
        with override_settings(FRONTEND_URL='https://evil.fr/?token=bad'), self.assertLogs('shop.accounts', level='ERROR'):
            known = self.client.post('/api/auth/password-reset/', {'email': self.user.email}, format='json')
        unknown = self.client.post('/api/auth/password-reset/', {'email': 'unknown@example.invalid'}, format='json')
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_link_uses_configured_origin_and_remains_single_use(self):
        response = self.client.post('/api/auth/password-reset/', {'email': self.user.email}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('http://localhost:5173/?reset_uid=', mail.outbox[0].body)
        self.assertNotIn('testserver', mail.outbox[0].body)
        from urllib.parse import parse_qs, urlsplit
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith('http'))
        query = parse_qs(urlsplit(link).query)
        payload = {'uid': query['reset_uid'][0], 'token': query['reset_token'][0], 'password': 'Delivery-Changed!78x4'}
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/', payload, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/', payload, format='json').status_code, 400)
