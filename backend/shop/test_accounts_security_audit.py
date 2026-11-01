"""Independent regression checks for account sessions and the customer directory."""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from .models import Order, Restaurant


User = get_user_model()
PASSWORD = 'Independent-Account-QA-82!'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountSessionBoundaryAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            'independent-owner@example.invalid', PASSWORD, first_name='Compte initial')
        cls.other = User.objects.create_user(
            'independent-other@example.invalid', PASSWORD, first_name='Autre compte', phone='0698765432')

    def setUp(self):
        cache.clear()
        self.browser = self.session(self.owner)

    def session(self, user):
        browser = APIClient(enforce_csrf_checks=True)
        browser.force_login(user)
        browser.get('/api/auth/csrf/')
        browser.credentials(HTTP_X_CSRFTOKEN=browser.cookies['csrftoken'].value)
        return browser

    def assert_private(self, response, status):
        self.assertEqual(response.status_code, status, response.content)
        directives = set(response.get('Cache-Control', '').split(', '))
        self.assertTrue({'private', 'no-store', 'no-cache', 'max-age=0'} <= directives)

    def test_deactivating_an_account_revokes_an_existing_session_immediately(self):
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        response = self.browser.get('/api/auth/me/')
        self.assert_private(response, 200)
        self.assertEqual(response.json(), {'user': None})
        response = self.browser.patch('/api/auth/me/', {'name': 'Intrusion'}, format='json')
        self.assert_private(response, 403)
        self.assertNotContains(response, self.owner.email, status_code=403)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.first_name, 'Compte initial')

    def test_password_change_invalidates_old_sessions_without_profile_mutation(self):
        self.owner.set_password('Replacement-Credentials-63!')
        self.owner.save(update_fields=['password'])
        response = self.browser.patch('/api/auth/me/', {'phone': '0612345678'}, format='json')
        self.assert_private(response, 403)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.phone, '')
        self.assertEqual(self.browser.get('/api/auth/me/').json(), {'user': None})

    def test_deleted_accounts_do_not_leave_a_writable_authenticated_session(self):
        self.owner.delete()
        response = self.browser.patch('/api/auth/me/', {'name': 'Compte recréé'}, format='json')
        self.assert_private(response, 403)
        self.assertFalse(User.objects.filter(email='independent-owner@example.invalid').exists())

    def test_interleaved_partial_updates_preserve_other_fields_and_account_identity(self):
        second_browser = self.session(self.owner)
        self.assert_private(self.browser.patch('/api/auth/me/', {'name': 'Nom actualisé'}, format='json'), 200)
        # A tab opened before the first edit may only submit its own changed field.
        response = second_browser.patch(
            f'/api/auth/me/?user_id={self.other.pk}', {'phone': '0612345678'}, format='json')
        self.assert_private(response, 200)
        self.assertEqual(response.json()['user']['name'], 'Nom actualisé')
        self.assertEqual(response.json()['user']['id'], self.owner.pk)
        self.owner.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual((self.owner.first_name, self.owner.phone), ('Nom actualisé', '0612345678'))
        self.assertEqual((self.other.first_name, self.other.phone), ('Autre compte', '0698765432'))

    def test_nested_malformed_json_and_unsupported_media_are_private_atomic_errors(self):
        for field in ['name', 'phone']:
            for value in [True, False, {}, [], {'is_staff': True}, ['0612345678']]:
                with self.subTest(field=field, value=value):
                    response = self.browser.patch('/api/auth/me/', {field: value}, format='json')
                    self.assert_private(response, 400)
        self.assert_private(self.browser.patch(
            '/api/auth/me/', '{"name":', content_type='application/json'), 400)
        self.assert_private(self.browser.patch(
            '/api/auth/me/', 'name=Intrusion', content_type='application/octet-stream'), 415)
        self.assert_private(self.browser.put('/api/auth/me/', {'name': 'Intrusion'}, format='json'), 405)
        self.owner.refresh_from_db()
        self.assertEqual((self.owner.first_name, self.owner.phone), ('Compte initial', ''))


@override_settings(DEMO_MODE=True, PAYMENT_MODE='simulation')
class CustomerDirectorySecurityScaleAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Restaurant.objects.create(pk=1, delivery_enabled=False)
        cls.customer = User.objects.create_user(
            'directory-customer@example.invalid', first_name='Client indépendant')
        cls.operator = User.objects.create_user('directory-operator@example.invalid', is_staff=True)
        cls.group = Group.objects.create(name='Independent customer readers')
        cls.group.permissions.set(Permission.objects.filter(
            content_type__app_label='shop', codename__in=['view_customer', 'view_order']))
        cls.operator.groups.add(cls.group)

    def setUp(self):
        self.client.force_login(self.operator)

    def detail_url(self):
        return reverse('crm:customer_detail', args=[self.customer.pk])

    def order(self):
        return Order.objects.create(
            user=self.customer, scope='independent-directory-audit', idempotency_key=uuid.uuid4().hex,
            payload_hash='f' * 64, mode='À emporter', status='completed',
            payment_method='on_site', payment_status='paid', demo_mode=False,
            subtotal=Decimal('0.01'), total=Decimal('0.01'),
            customer={'name': 'Client indépendant', 'email': self.customer.email, 'phone': '0612345678'})

    def assert_denied_without_customer_data(self):
        for path in [reverse('crm:customers'), self.detail_url()]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 403)
                self.assertNotContains(response, self.customer.email, status_code=403)
                self.assertIn('no-store', response['Cache-Control'])

    def test_group_permission_revocation_applies_to_an_existing_operator_session(self):
        self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        self.group.permissions.remove(Permission.objects.get(
            content_type__app_label='shop', codename='view_customer'))
        self.assert_denied_without_customer_data()

    def test_staff_demotion_applies_to_an_existing_operator_session(self):
        self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        User.objects.filter(pk=self.operator.pk).update(is_staff=False)
        self.assert_denied_without_customer_data()

    def test_directory_query_count_is_bounded_with_twenty_customers(self):
        with CaptureQueriesContext(connection) as small:
            response = self.client.get(reverse('crm:customers'))
        self.assertEqual(response.status_code, 200)
        User.objects.bulk_create([
            User(email=f'independent-scale-{i}@example.invalid', first_name=f'Client {i:02}')
            for i in range(19)
        ])
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(reverse('crm:customers'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['customers']), 20)
        self.assertEqual(len(large), len(small), 'Directory introduced per-customer database queries')

    def test_history_query_count_is_bounded_and_decimal_totals_stay_exact(self):
        self.order()
        with CaptureQueriesContext(connection) as small:
            response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        for _ in range(19):
            self.order()
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['customer_orders']), 20)
        self.assertEqual(response.context['customer_account'].crm_paid_total, Decimal('0.20'))
        self.assertEqual(len(large), len(small), 'History introduced per-order database queries')


@override_settings(DEBUG=True, FRONTEND_URL='http://localhost:5173',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountRecoverySecurityAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('recovery-owner@example.invalid', PASSWORD)
        cls.other = User.objects.create_user('recovery-other@example.invalid', PASSWORD)

    def setUp(self):
        cache.clear()
        self.visitor = self.browser()

    def browser(self, user=None):
        browser = APIClient(enforce_csrf_checks=True)
        if user is not None:
            browser.force_login(user)
        browser.get('/api/auth/csrf/')
        browser.credentials(HTTP_X_CSRFTOKEN=browser.cookies['csrftoken'].value)
        return browser

    def payload(self, user, token=None):
        return {
            'uid': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': token or default_token_generator.make_token(user),
            'password': 'Recovery-Replacement-67!x',
        }

    def test_a_forged_host_does_not_change_the_recovery_destination(self):
        with override_settings(ALLOWED_HOSTS=['testserver', 'attacker.fr']):
            response = self.visitor.post('/api/auth/password-reset/', {'email': self.owner.email},
                                         format='json', HTTP_HOST='attacker.fr')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertNotIn('attacker.fr', body)
        link = next(line for line in body.splitlines() if line.startswith('http'))
        self.assertEqual(urlsplit(link).netloc, 'localhost:5173')
        self.assertEqual(set(parse_qs(urlsplit(link).query)), {'reset_uid', 'reset_token'})

    def test_a_valid_token_cannot_be_retargeted_to_another_account(self):
        owner_token = default_token_generator.make_token(self.owner)
        response = self.visitor.post('/api/auth/password-reset-confirm/',
                                     self.payload(self.other, owner_token), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('no-store', response['Cache-Control'])
        for account in [self.owner, self.other]:
            account.refresh_from_db()
            self.assertTrue(account.check_password(PASSWORD))
        self.assertEqual(self.visitor.post('/api/auth/password-reset-confirm/',
                         self.payload(self.owner, owner_token), format='json').status_code, 200)

    @override_settings(PASSWORD_RESET_TIMEOUT=60)
    def test_expired_tokens_are_rejected_without_changing_the_password(self):
        issued_at = datetime(2026, 11, 1, 12, 0, 0)
        with patch.object(default_token_generator, '_now', return_value=issued_at):
            token = default_token_generator.make_token(self.owner)
        with patch.object(default_token_generator, '_now', return_value=issued_at + timedelta(seconds=61)):
            response = self.visitor.post('/api/auth/password-reset-confirm/',
                                         self.payload(self.owner, token), format='json')
        self.assertEqual(response.status_code, 400)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password(PASSWORD))

    def test_reset_invalidates_existing_owner_sessions_but_not_other_accounts(self):
        owner_browser = self.browser(self.owner)
        second_owner_browser = self.browser(self.owner)
        other_browser = self.browser(self.other)
        response = self.visitor.post('/api/auth/password-reset-confirm/', self.payload(self.owner), format='json')
        self.assertEqual(response.status_code, 200)
        for browser in [owner_browser, second_owner_browser]:
            self.assertEqual(browser.get('/api/auth/me/').json(), {'user': None})
            self.assertEqual(browser.patch('/api/auth/me/', {'name': 'Old session'}, format='json').status_code, 403)
        self.assertEqual(other_browser.get('/api/auth/me/').json()['user']['id'], self.other.pk)

    def test_inactive_unusable_and_unknown_accounts_share_the_same_reset_response(self):
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.other.set_unusable_password()
        self.other.save(update_fields=['password'])
        responses = [self.visitor.post('/api/auth/password-reset/', {'email': address}, format='json')
                     for address in [self.owner.email, self.other.email, 'missing-recovery@example.invalid']]
        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        self.assertTrue(all(response.json() == responses[0].json() for response in responses))
        self.assertTrue(all('no-store' in response['Cache-Control'] for response in responses))
        self.assertEqual(len(mail.outbox), 0)
