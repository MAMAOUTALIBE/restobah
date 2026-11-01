"""Customer profile authorization, validation and non-destructive migration checks."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import Order


PASSWORD = 'Profile-Test-9x!Strong'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = get_user_model().objects.create_user(
            'profile-owner@example.invalid', PASSWORD, first_name='Camille Martin')
        cls.other = get_user_model().objects.create_user(
            'profile-other@example.invalid', PASSWORD, first_name='Autre client', phone='0698765432')
        cls.order = Order.objects.create(
            user=cls.customer, scope='account-profile', idempotency_key='account-profile-order',
            payload_hash='a' * 64, mode='À emporter', subtotal=Decimal('12.90'), total=Decimal('12.90'),
            customer={'name': 'Camille Martin', 'email': cls.customer.email, 'phone': '0612345678'})

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.customer)
        self.csrf(self.client)

    def csrf(self, client):
        client.get('/api/auth/csrf/')
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)

    def profile(self, data, client=None, **kwargs):
        return (client or self.client).patch('/api/auth/me/', data, format='json', **kwargs)

    def assert_private(self, response, status=200):
        self.assertEqual(response.status_code, status, response.content)
        directives = {part.strip() for part in response.get('Cache-Control', '').split(',')}
        self.assertTrue({'private', 'no-store', 'no-cache', 'max-age=0', 'must-revalidate'} <= directives)

    def test_profile_update_persists_without_password_or_session_change(self):
        session_key = self.client.session.session_key
        original_password = self.customer.password
        response = self.profile({'name': '  Camille Dupont  ', 'phone': '+33 6 12 34 56 78'})
        self.assert_private(response)
        expected = {'id': self.customer.pk, 'name': 'Camille Dupont',
                    'email': self.customer.email, 'phone': '+33 6 12 34 56 78'}
        self.assertEqual(response.json(), {'user': expected})
        self.assertEqual(self.client.get('/api/auth/me/').json(), {'user': expected})
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, 'Camille Dupont')
        self.assertEqual(self.customer.phone, '+33 6 12 34 56 78')
        self.assertEqual(self.customer.password, original_password)
        self.assertTrue(self.customer.check_password(PASSWORD))
        self.assertEqual(self.client.session.session_key, session_key)
        another_session = APIClient(enforce_csrf_checks=True)
        self.csrf(another_session)
        login = another_session.post('/api/auth/login/', {
            'email': self.customer.email, 'password': PASSWORD,
        }, format='json')
        self.assert_private(login)
        self.assertEqual(login.json(), {'user': expected})

    def test_partial_updates_keep_other_fields_and_allow_removing_phone(self):
        self.assert_private(self.profile({'phone': '0612345678'}))
        self.assert_private(self.profile({'name': 'Nouveau nom'}))
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.first_name, self.customer.phone), ('Nouveau nom', '0612345678'))
        self.assert_private(self.profile({'phone': ''}))
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.first_name, self.customer.phone), ('Nouveau nom', ''))

    def test_anonymous_read_stays_available_but_update_requires_login(self):
        visitor = APIClient(enforce_csrf_checks=True)
        self.csrf(visitor)
        response = visitor.get('/api/auth/me/')
        self.assert_private(response)
        self.assertEqual(response.json(), {'user': None})
        self.assert_private(self.profile({'name': 'Intrus'}, visitor), 403)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, 'Camille Martin')

    def test_updates_require_csrf_and_trusted_origin(self):
        missing_csrf = APIClient(enforce_csrf_checks=True)
        missing_csrf.force_login(self.customer)
        self.assert_private(self.profile({'name': 'Intrus'}, missing_csrf), 403)
        self.client.credentials(HTTP_X_CSRFTOKEN='invalid')
        self.assert_private(self.profile({'name': 'Intrus'}), 403)
        self.csrf(self.client)
        self.assert_private(self.profile({'name': 'Intrus'}, HTTP_ORIGIN='https://untrusted.invalid'), 403)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, 'Camille Martin')

    def test_profile_input_errors_are_private_and_do_not_partially_save(self):
        invalid_values = [
            {'name': ''}, {'name': ' '}, {'name': 'A'}, {'name': 'A' * 101}, {'name': None},
            {'phone': None}, {'phone': '123456789'}, {'phone': '1234567890123456'},
            {'phone': '0612abc678'}, {'phone': '+33/612345678'}, {'phone': '++++++++++'},
            {'phone': '٠٦١٢٣٤٥٦٧٨'}, {'phone': '0' + ' ' * 23 + '6'},
            {'name': 'Nom valide', 'phone': 'court'},
        ]
        for data in invalid_values:
            with self.subTest(data=data):
                self.assert_private(self.profile(data), 400)
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.first_name, self.customer.phone), ('Camille Martin', ''))

    def test_phone_accepts_address_formats_and_digit_boundaries(self):
        for phone in ['0612345678', '06.12.34.56.78', '(06) 12-34-56-78', '+123456789012345']:
            with self.subTest(phone=phone):
                response = self.profile({'phone': phone})
                self.assert_private(response)
                self.assertEqual(response.json()['user']['phone'], phone)

    def test_unknown_fields_cannot_change_identity_credentials_or_privileges(self):
        original_password = self.customer.password
        for key, value in [
            ('id', self.other.pk), ('user', self.other.pk), ('user_id', self.other.pk),
            ('email', 'attacker@example.invalid'), ('is_staff', True), ('is_superuser', True),
            ('is_active', False), ('password', 'Injected-password-4!'), ('groups', [1]),
            ('user_permissions', [1]), ('first_name', 'Injected'), ('last_name', 'Injected'),
        ]:
            with self.subTest(field=key):
                self.assert_private(self.profile({'name': 'Nouveau nom', 'phone': '0612345678', key: value}), 400)
        self.customer.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual((self.customer.first_name, self.customer.phone, self.customer.email),
                         ('Camille Martin', '', 'profile-owner@example.invalid'))
        self.assertEqual(self.customer.password, original_password)
        self.assertFalse(self.customer.is_staff)
        self.assertFalse(self.customer.is_superuser)
        self.assertTrue(self.customer.is_active)
        self.assertFalse(self.customer.groups.exists())
        self.assertFalse(self.customer.user_permissions.exists())
        self.assertEqual((self.other.first_name, self.other.phone), ('Autre client', '0698765432'))

    def test_non_object_json_is_rejected_without_mutation(self):
        for data in [[], ['name', 'phone'], 'name', 123, True]:
            with self.subTest(data=data):
                self.assert_private(self.profile(data), 400)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, 'Camille Martin')

    def test_auth_forms_also_reject_non_object_json_without_server_error(self):
        visitor = APIClient(enforce_csrf_checks=True)
        self.csrf(visitor)
        for path in ['/api/auth/register/', '/api/auth/login/', '/api/auth/password-reset/']:
            with self.subTest(path=path):
                self.assert_private(visitor.post(path, ['invalid'], format='json'), 400)

    def test_profile_changes_keep_order_contacts_and_account_ownership(self):
        before = Order.objects.filter(pk=self.order.pk).values().get()
        self.assert_private(self.profile({'name': 'Camille Dupont', 'phone': '0600000000'}))
        self.assertEqual(Order.objects.filter(pk=self.order.pk).values().get(), before)
        own_orders = self.client.get('/api/orders/')
        self.assertEqual([order['id'] for order in own_orders.json()], [self.order.pk])
        self.assertEqual(own_orders.json()[0]['customer'], before['customer'])
        other_session = APIClient(enforce_csrf_checks=True)
        other_session.force_login(self.other)
        self.csrf(other_session)
        self.assert_private(self.profile({'phone': '0611111111'}, other_session))
        self.assertEqual(other_session.get('/api/orders/').json(), [])
        self.customer.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual((self.customer.phone, self.other.phone), ('0600000000', '0611111111'))

    def test_registration_keeps_three_fields_and_optional_phone_default(self):
        visitor = APIClient(enforce_csrf_checks=True)
        self.csrf(visitor)
        payload = {'name': 'Nouveau client', 'email': 'NEW-client@example.invalid', 'password': PASSWORD}
        response = visitor.post('/api/auth/register/', payload, format='json')
        self.assert_private(response, 201)
        created = get_user_model().objects.get(pk=response.json()['user']['id'])
        self.assertEqual(response.json()['user']['phone'], '')
        self.assertEqual(created.phone, '')
        self.assertEqual(created.email, 'new-client@example.invalid')
        self.assertTrue(created.check_password(PASSWORD))
        self.assertFalse(created.is_staff)
        self.assertFalse(created.has_perm('shop.view_customer'))
        self.csrf(visitor)
        extra_phone = visitor.post('/api/auth/register/', {
            **payload, 'email': 'new-phone@example.invalid', 'phone': '0612345678',
        }, format='json')
        self.assert_private(extra_phone, 400)
        self.assertFalse(get_user_model().objects.filter(email='new-phone@example.invalid').exists())

    def test_registration_still_rejects_short_password(self):
        visitor = APIClient(enforce_csrf_checks=True)
        self.csrf(visitor)
        response = visitor.post('/api/auth/register/', {
            'name': 'Nouveau client', 'email': 'short@example.invalid', 'password': 'Ab3!xY7?z',
        }, format='json')
        self.assert_private(response, 400)
        self.assertFalse(get_user_model().objects.filter(email='short@example.invalid').exists())

    def test_customer_permission_exists_but_is_not_granted_automatically(self):
        permission = Permission.objects.get(content_type__app_label='shop', codename='view_customer')
        self.assertEqual(permission.content_type.model, 'user')
        self.assertFalse(self.customer.has_perm('shop.view_customer'))
        self.customer.is_staff = True
        self.customer.save(update_fields=['is_staff'])
        actor = get_user_model().objects.get(pk=self.customer.pk)
        self.assertFalse(actor.has_perm('shop.view_customer'))
        actor.user_permissions.add(permission)
        self.assertTrue(get_user_model().objects.get(pk=actor.pk).has_perm('shop.view_customer'))


class AccountProfileMigrationTests(TransactionTestCase):
    migrate_from = [('shop', '0006_onsite_payments')]
    migrate_to = [('shop', '0007_account_profile')]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.old_apps = executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_migration_keeps_existing_users_passwords_orders_and_saved_addresses(self):
        old_user = self.old_apps.get_model('shop', 'User')
        password_hash = make_password(PASSWORD)
        owner = old_user.objects.create(email='legacy@example.invalid', password=password_hash,
                                        first_name='Ancien client', is_active=True)
        self.old_apps.get_model('shop', 'Address').objects.create(
            user=owner, label='Maison', name='Ancien client', phone='0612345678',
            address='1 rue du test', postal='75011', city='Paris')
        order = self.old_apps.get_model('shop', 'Order').objects.create(
            user=owner, scope='legacy-profile', idempotency_key='legacy-profile-order', payload_hash='b' * 64,
            mode='À emporter', subtotal=Decimal('9.50'), total=Decimal('9.50'),
            customer={'name': 'Ancien client', 'email': owner.email, 'phone': '0612345678'})
        self.old_apps.get_model('shop', 'OrderLine').objects.create(
            order=order, name='Ancien plat', quantity=1, unit_price=Decimal('9.50'),
            total=Decimal('9.50'), choices=['Sauce maison'])
        self.old_apps.get_model('shop', 'OrderHistory').objects.create(order=order, status='confirmed')
        names = ['User', 'Address', 'Order', 'OrderLine', 'OrderHistory']
        fields = {name: [field.attname for field in self.old_apps.get_model('shop', name)._meta.concrete_fields]
                  for name in names}
        before = {name: list(self.old_apps.get_model('shop', name).objects.order_by('pk').values(*fields[name]))
                  for name in names}
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        after = {name: list(apps.get_model('shop', name).objects.order_by('pk').values(*fields[name]))
                 for name in names}
        self.assertEqual(before, after)
        migrated = apps.get_model('shop', 'User').objects.get(pk=owner.pk)
        self.assertEqual(migrated.phone, '')
        self.assertEqual(migrated.password, password_hash)
        self.assertTrue(check_password(PASSWORD, migrated.password))
        self.assertIn(('view_customer', 'Consulter les clients'), migrated._meta.permissions)
        self.assertFalse(migrated.user_permissions.exists())
        # A previous backend can still INSERT during the rolling deployment.
        legacy_insert = old_user.objects.create(email='legacy-insert@example.invalid', password=password_hash)
        self.assertEqual(apps.get_model('shop', 'User').objects.get(pk=legacy_insert.pk).phone, '')
