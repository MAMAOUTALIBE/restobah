"""CSRF recovery is read-only and uses only Django's temporary test database."""
import json
from decimal import Decimal

from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from .crm_forms import ProductForm
from .models import Category, Product
from .views import csrf_failure


JSON_ERROR = {'detail': 'Session de sécurité expirée. Actualisez la page et réessayez.'}


class CRMCSRFFailureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_superuser(
            'gerant-prive@example.com', 'MotDePassePrive-9x!'
        )
        cls.category = Category.objects.create(name='Recettes du test')
        cls.product = Product.objects.create(
            name='Recette conservée', category=cls.category,
            description='Description conservée.', price=Decimal('8.90'),
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def assert_private_html_error(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('no-cache', response['Cache-Control'])
        self.assertContains(response, 'Votre demande n’a pas été enregistrée', status_code=403)
        self.assertNotContains(response, '<form', status_code=403)
        self.assertNotContains(response, 'crm-sidebar', status_code=403)
        self.assertNotContains(response, '<script', status_code=403)

    def test_login_missing_csrf_returns_private_html_without_creating_a_session_login(self):
        response = self.client.post(reverse('crm:login'), {
            'username': self.manager.email, 'password': 'MotDePassePrive-9x!',
        })
        self.assert_private_html_error(response)
        self.assertContains(response, f'href="{reverse("crm:login")}"', status_code=403)
        self.assertNotContains(response, self.manager.email, status_code=403)
        self.assertNotContains(response, 'MotDePassePrive-9x!', status_code=403)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_valid_product_creation_without_csrf_cannot_write_and_offers_a_get_form(self):
        self.client.force_login(self.manager)
        payload = {
            'name': 'Plat privé non enregistré', 'category': str(self.category.pk),
            'description': 'Description privée non enregistrée.', 'price': '12,50',
            'available': 'on', 'allergens_text': '',
        }
        self.assertTrue(ProductForm(payload).is_valid())
        before = list(Product.objects.values())
        response = self.client.post(reverse('crm:product_add'), payload)
        self.assert_private_html_error(response)
        self.assertEqual(list(Product.objects.values()), before)
        self.assertNotContains(response, payload['name'], status_code=403)
        self.assertNotContains(response, payload['description'], status_code=403)
        self.assertContains(response, f'href="{reverse("crm:product_add")}"', status_code=403)
        self.assertEqual(self.client.get(reverse('crm:product_add')).status_code, 200)

    def test_valid_edit_with_missing_csrf_preserves_the_recipe(self):
        self.client.force_login(self.manager)
        edit_url = reverse('crm:product_edit', args=[self.product.pk])
        current = self.client.get(edit_url)
        payload = {
            'name': 'Modification privée refusée', 'category': str(self.category.pk),
            'description': 'Autre description.', 'price': '19,90', 'available': 'on',
            'allergens_text': '', 'revision': current.context['form'].initial['revision'],
        }
        self.assertTrue(ProductForm(payload, instance=Product.objects.get(pk=self.product.pk)).is_valid())
        response = self.client.post(edit_url, payload)
        self.assert_private_html_error(response)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Recette conservée')
        self.assertEqual(self.product.price, Decimal('8.90'))
        self.assertContains(response, f'href="{edit_url}"', status_code=403)

    def test_mutation_routes_only_offer_known_get_destinations(self):
        self.client.force_login(self.manager)
        cases = [
            ('logout', [], 'dashboard', []),
            ('product_availability', [self.product.pk], 'menu', []),
            ('order_status', ['STC-PRIVATE'], 'orders', []),
            ('restaurant', [], 'restaurant', []),
            ('closure_add', [], 'restaurant', []),
            ('closure_delete', [123456], 'restaurant', []),
        ]
        for source, source_args, destination, destination_args in cases:
            with self.subTest(source=source):
                response = self.client.post(reverse(f'crm:{source}', args=source_args), {
                    'next': 'https://externe.example/secret',
                }, HTTP_REFERER='https://externe.example/autre-secret')
                self.assert_private_html_error(response)
                target = reverse(f'crm:{destination}', args=destination_args)
                self.assertContains(response, f'href="{target}"', status_code=403)
                self.assertNotContains(response, 'externe.example', status_code=403)
                self.assertEqual(self.client.get(target).status_code, 200)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.manager.pk))

    def test_wrong_origin_with_a_valid_token_also_gets_private_html(self):
        self.client.get(reverse('crm:login'))
        token = self.client.cookies['csrftoken'].value
        response = self.client.post(reverse('crm:login'), {
            'username': self.manager.email, 'password': 'MotDePassePrive-9x!',
            'csrfmiddlewaretoken': token,
        }, HTTP_ORIGIN='https://origine-interdite.example')
        self.assert_private_html_error(response)
        self.assertNotContains(response, token, status_code=403)
        self.assertNotContains(response, 'origine-interdite.example', status_code=403)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_https_referer_rejections_with_valid_tokens_get_private_html(self):
        for referer in ('https://externe.example/REFERER-SECRET', 'REFERER-MALFORMED-SECRET', ''):
            with self.subTest(referer=referer):
                client = Client(enforce_csrf_checks=True)
                client.get(reverse('crm:login'), secure=True)
                token = client.cookies['csrftoken'].value
                response = client.post(reverse('crm:login'), {
                    'username': self.manager.email, 'password': 'MotDePassePrive-9x!',
                    'csrfmiddlewaretoken': token,
                }, secure=True, HTTP_REFERER=referer)
                self.assert_private_html_error(response)
                for secret in (token, self.manager.email, 'MotDePassePrive-9x!', 'REFERER-SECRET', 'REFERER-MALFORMED-SECRET'):
                    self.assertNotContains(response, secret, status_code=403)
                self.assertNotIn(SESSION_KEY, client.session)

    def test_reason_body_and_query_are_never_rendered_and_fallback_never_replays_post(self):
        for path in ('/crm', '/crm/inconnu/?next=https://externe.example/QUERY-SECRET'):
            with self.subTest(path=path):
                request = RequestFactory().post(path, {
                    'password': 'POST-SECRET', 'customer': 'PRIVATE-CUSTOMER',
                }, HTTP_REFERER='https://externe.example/REFERER-SECRET')
                with self.assertNumQueries(0):
                    response = csrf_failure(request, reason='REASON-SECRET <script>danger()</script>')
                self.assert_private_html_error(response)
                self.assertContains(response, f'href="{reverse("crm:dashboard")}"', status_code=403)
                for secret in ('POST-SECRET', 'PRIVATE-CUSTOMER', 'REASON-SECRET', 'QUERY-SECRET', 'REFERER-SECRET', 'externe.example'):
                    self.assertNotContains(response, secret, status_code=403)

    def test_api_and_admin_keep_the_exact_json_error(self):
        for path in ('/api/auth/login/', '/admin/login/'):
            with self.subTest(path=path):
                response = self.client.post(path, {'password': 'PRIVATE-API-PASSWORD'})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response['Content-Type'], 'application/json')
                self.assertEqual(response.json(), JSON_ERROR)

    def test_similar_prefixes_are_not_crm_pages(self):
        for path in ('/crm-other/', '/crmx/', '/other/crm/', '/CRM/connexion/'):
            with self.subTest(path=path):
                response = csrf_failure(RequestFactory().post(path), reason='PRIVATE-REASON')
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response['Content-Type'], 'application/json')
                self.assertEqual(json.loads(response.content), JSON_ERROR)
