"""Private API responses stay out of caches, including rejected requests."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from .models import Address, Category, Favorite, OnSitePaymentEvent, Order, Product, Restaurant
from .onsite_payments import record_payment
from .views import csrf_failure


@override_settings(DEMO_MODE=True, PAYMENT_MODE='simulation', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PrivateAPICacheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.customer = users.objects.create_user('cache-owner@example.invalid', 'Cache-Only-9x!Strong')
        cls.other = users.objects.create_user('cache-other@example.invalid', 'Cache-Other-9x!Strong')
        Restaurant.objects.create(pk=1, delivery_enabled=False)
        category = Category.objects.create(name='Recettes cache')
        cls.product = Product.objects.create(name='Recette publique', category=category,
                                             description='Description publique.', price=Decimal('9.50'))
        Address.objects.create(user=cls.customer, label='Adresse privée', name='Client du test',
                               phone='0612345678', address='1 rue du test', postal='75011', city='Paris')
        cls.order = Order.objects.create(user=cls.customer, scope='cache-test',
                                        idempotency_key='private-cache-order', payload_hash='f' * 64,
                                        mode='À emporter', subtotal=Decimal('9.50'), total=Decimal('9.50'),
                                        customer={'name': 'Client du test', 'email': cls.customer.email,
                                                  'phone': '0612345678'})

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf(self, client=None):
        client = client or self.client
        response = client.get('/api/auth/csrf/')
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        return response

    def assert_private_json(self, response, status=200):
        self.assertEqual(response.status_code, status)
        self.assertTrue(response['Content-Type'].startswith('application/json'))
        directives = {part.strip() for part in response.get('Cache-Control', '').split(',')}
        self.assertTrue({'private', 'no-store', 'no-cache', 'must-revalidate', 'max-age=0'} <= directives)
        self.assertIn('Expires', response)

    def test_authenticated_private_reads_are_not_cacheable(self):
        self.client.force_login(self.customer)
        for path in ('/api/auth/csrf/', '/api/auth/me/', '/api/orders/',
                     f'/api/orders/{self.order.pk}/', '/api/addresses/', '/api/favorites/'):
            with self.subTest(path=path):
                self.assert_private_json(self.client.get(path))
        self.assertEqual(self.client.get('/api/auth/me/').json()['user']['email'], self.customer.email)
        self.assertEqual(self.client.get('/api/orders/').json()[0]['customer']['email'], self.customer.email)

    def test_anonymous_reads_and_permission_errors_are_not_cacheable(self):
        for path in ('/api/auth/csrf/', '/api/auth/me/'):
            with self.subTest(path=path):
                self.assert_private_json(self.client.get(path))
        self.assertEqual(self.client.get('/api/auth/me/').json(), {'user': None})
        for path in ('/api/orders/', '/api/addresses/', '/api/favorites/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assert_private_json(response, 403)
                self.assertNotIn(self.customer.email, response.content.decode())

    def test_guest_tracking_and_unknown_order_errors_remain_private(self):
        base = f'/api/orders/{self.order.pk}/'
        guest = self.client.get(base, {'token': self.order.access_token})
        self.assert_private_json(guest)
        self.assertNotIn('customer', guest.json())
        self.assertNotIn('accessToken', guest.json())
        for path, params in ((base, {}), (base, {'token': 'wrong'}), ('/api/orders/STC-UNKNOWN/', {})):
            with self.subTest(path=path, params=params):
                response = self.client.get(path, params)
                self.assert_private_json(response, 404)
                self.assertEqual(response.json(), {'detail': 'Commande introuvable.'})
        self.client.force_login(self.other)
        self.assert_private_json(self.client.get(base), 404)

    def test_csrf_rejections_before_dispatch_keep_exact_json_and_no_store(self):
        expected = {'detail': 'Session de sécurité expirée. Actualisez la page et réessayez.'}
        for path in ('/api/auth/login/', '/api/auth/register/', '/api/auth/logout/',
                     '/api/orders/', '/api/addresses/'):
            with self.subTest(path=path):
                response = self.client.post(path, {'password': 'not-rendered'}, format='json')
                self.assert_private_json(response, 403)
                self.assertEqual(response.json(), expected)
        self.csrf()
        denied = self.client.post('/api/auth/login/', {}, format='json', HTTP_ORIGIN='https://forbidden.example')
        self.assert_private_json(denied, 403)
        self.assertEqual(denied.json(), expected)
        response = csrf_failure(RequestFactory().post('/api/orders/'), reason='PRIVATE-REASON')
        self.assert_private_json(response, 403)
        self.assertJSONEqual(response.content, expected)

    def test_login_success_failure_logout_and_validation_errors_are_private(self):
        self.csrf()
        invalid = self.client.post('/api/auth/login/', {'email': self.customer.email, 'password': 'incorrect'}, format='json')
        self.assert_private_json(invalid, 403)
        self.assertEqual(invalid.json(), {'detail': 'Adresse e-mail ou mot de passe incorrect.'})
        logged_in = self.client.post('/api/auth/login/', {'email': self.customer.email, 'password': 'Cache-Only-9x!Strong'}, format='json')
        self.assert_private_json(logged_in)
        self.assertEqual(logged_in.json()['user']['email'], self.customer.email)
        self.csrf()  # Authentication rotates the CSRF secret.
        malformed = self.client.post('/api/addresses/', {}, format='json')
        self.assert_private_json(malformed, 400)
        denied = self.client.post('/api/auth/delete-account/', {'password': 'incorrect'}, format='json')
        self.assert_private_json(denied, 400)
        logout = self.client.post('/api/auth/logout/', {}, format='json')
        self.assert_private_json(logout)
        self.assertEqual(logout.json(), {'detail': 'Vous êtes déconnecté.'})

    def test_auth_throttles_method_errors_and_payment_failures_are_private(self):
        self.csrf()
        with patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'auth': '1/hour'}):
            first = self.client.post('/api/auth/password-reset/', {'email': 'unknown@example.invalid'}, format='json')
            second = self.client.post('/api/auth/password-reset/', {'email': 'unknown@example.invalid'}, format='json')
        self.assert_private_json(first)
        self.assert_private_json(second, 429)
        self.assertIn('Retry-After', second)
        self.assert_private_json(self.client.get('/api/auth/login/'), 405)
        payment = self.client.post(f'/api/orders/{self.order.pk}/payment/', {}, format='json')
        self.assert_private_json(payment, 503)

    def test_password_reset_errors_and_favorite_validation_remain_private(self):
        self.csrf()
        invalid_reset = self.client.post('/api/auth/password-reset-confirm/', {
            'uid': 'invalid', 'token': 'invalid', 'password': 'Reset-Only-9x!Strong',
        }, format='json')
        self.assert_private_json(invalid_reset, 400)
        self.client.force_login(self.customer)
        self.csrf()
        favorites = self.client.put('/api/favorites/', {'productIds': ['not-an-integer']}, format='json')
        self.assert_private_json(favorites, 400)

    def test_former_staff_with_financial_history_cannot_self_delete(self):
        # Record a real operation through the service while this account is staff,
        # then revoke that role before exercising the public account endpoint.
        self.customer.is_staff = True
        self.customer.save(update_fields=['is_staff'])
        self.customer.user_permissions.set(Permission.objects.filter(content_type__app_label='shop',
            codename__in=['view_order', 'change_order', 'record_onsite_payment']))
        order = Order.objects.create(user=self.customer, scope='protected-account',
            idempotency_key='protected-account-order', payload_hash='e' * 64, mode='À emporter',
            payment_method='on_site', payment_status='due', demo_mode=False,
            subtotal=Decimal('9.50'), total=Decimal('9.50'), customer={})
        record_payment(order.pk, self.customer, 'collected',
                       expected_status='confirmed', expected_payment_status='due')
        self.customer.is_staff = False
        self.customer.save(update_fields=['is_staff'])
        favorite = Favorite.objects.create(user=self.customer, product=self.product)
        self.client.force_login(self.customer)
        before = {
            'user': get_user_model().objects.filter(pk=self.customer.pk).values().get(),
            'addresses': list(Address.objects.filter(user=self.customer).values()),
            'favorite': Favorite.objects.filter(pk=favorite.pk).values().get(),
            'orders': list(Order.objects.filter(user=self.customer).order_by('pk').values()),
            'events': list(OnSitePaymentEvent.objects.filter(actor=self.customer).values()),
        }
        self.client.raise_request_exception = False
        self.assert_private_json(self.client.post('/api/auth/delete-account/',
            {'password': 'Cache-Only-9x!Strong'}, format='json'), 403)
        self.csrf()
        response = self.client.post('/api/auth/delete-account/',
            {'password': 'Cache-Only-9x!Strong'}, format='json')
        self.assert_private_json(response, 400)
        message = 'Ce compte ne peut pas être supprimé. Contactez le restaurant.'
        self.assertEqual(response.json(), {'detail': message, 'errors': [message]})
        self.assertEqual(get_user_model().objects.filter(pk=self.customer.pk).values().get(), before['user'])
        self.assertEqual(list(Address.objects.filter(user=self.customer).values()), before['addresses'])
        self.assertEqual(Favorite.objects.filter(pk=favorite.pk).values().get(), before['favorite'])
        self.assertEqual(list(Order.objects.filter(user=self.customer).order_by('pk').values()), before['orders'])
        self.assertEqual(list(OnSitePaymentEvent.objects.filter(actor=self.customer).values()), before['events'])
        self.assertEqual(self.client.get('/api/auth/me/').json()['user']['id'], self.customer.pk)

    def test_public_catalog_health_categories_and_restaurant_keep_existing_cache_policy(self):
        for path in ('/api/products/', '/api/categories/', '/api/restaurant/', '/api/health/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response['Content-Type'].startswith('application/json'))
                self.assertNotIn('Cache-Control', response)
        self.assertEqual(self.client.get('/api/products/').json()[0]['name'], self.product.name)
