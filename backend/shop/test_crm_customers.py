"""Read-only customer CRM acceptance, on Django's disposable test database."""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Order, Restaurant, User


@override_settings(DEMO_MODE=True, PAYMENT_MODE='simulation')
class CRMCustomerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Restaurant.objects.create(pk=1, delivery_enabled=False)
        cls.manager = User.objects.create_superuser('customer-manager@example.com', 'Isolated-QA-29!')
        cls.staff = User.objects.create_user('customer-reader@example.com', is_staff=True)
        cls.customer = User.objects.create_user('camille@example.com', first_name='Camille Client', phone='0612345678')
        cls.other = User.objects.create_user('other@example.com', first_name='Autre client')

    def setUp(self):
        self.client.force_login(self.manager)

    def url(self, route='customers', pk=None):
        return reverse(f'crm:{route}', args=[] if pk is None else [pk])

    def grant(self, user, *codenames):
        user.user_permissions.set(Permission.objects.filter(content_type__app_label='shop', codename__in=codenames))
        self.client.force_login(User.objects.get(pk=user.pk))

    def order(self, user=None, *, payment='paid', method='on_site', status='completed', amount='10.00', demo=False, phone='0699999999'):
        return Order.objects.create(
            user=user, scope='crm-customer-test', idempotency_key=uuid.uuid4().hex, payload_hash='a' * 64,
            mode='À emporter', status=status, payment_status=payment, payment_method=method,
            demo_mode=demo, subtotal=Decimal(amount), total=Decimal(amount),
            customer={'name': 'Contact de commande', 'email': self.customer.email, 'phone': phone},
        )

    def test_both_customer_and_order_permission_are_required(self):
        pages = [self.url(), self.url('customer_detail', self.customer.pk)]
        self.client.logout()
        for url in pages:
            self.assertEqual(self.client.get(url).status_code, 302)
        for permissions in [(), ('view_order',), ('view_customer',), ('view_restaurant', 'view_order')]:
            self.grant(self.staff, *permissions)
            for url in pages:
                with self.subTest(permissions=permissions, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertNotContains(response, self.customer.email, status_code=403)
        self.grant(self.staff, 'view_order', 'view_customer')
        for url in pages:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(self.url('restaurant')).status_code, 403)

    def test_nonstaff_and_inactive_operators_cannot_read_clients(self):
        self.grant(self.customer, 'view_customer', 'view_order')
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.staff.is_active = False
        self.staff.save(update_fields=['is_active'])
        self.grant(self.staff, 'view_customer', 'view_order')
        self.assertIn(self.client.get(self.url()).status_code, [302, 403])

    def test_pages_are_read_only_and_private_even_when_missing(self):
        for url in [self.url(), self.url('customer_detail', self.customer.pk), self.url('customer_detail', 99999999)]:
            response = self.client.get(url)
            self.assertIn('private', response.headers.get('Cache-Control', ''))
            self.assertIn('no-store', response.headers.get('Cache-Control', ''))
            self.assertEqual(self.client.post(url, {'phone': '0600000000'}).status_code, 405)
            self.assertEqual(self.client.delete(url).status_code, 405)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.phone, '0612345678')

    def test_only_customer_accounts_are_listed_and_staff_targets_are_hidden(self):
        anomalous = User.objects.create_user('super-without-staff@example.com', is_superuser=True, is_staff=False)
        response = self.client.get(self.url())
        self.assertSetEqual({user.pk for user in response.context['customers']}, {self.customer.pk, self.other.pk})
        for user in [self.manager, self.staff, anomalous]:
            response = self.client.get(self.url('customer_detail', user.pk))
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(user.email, response.content.decode().split('<main', 1)[1])

    def test_real_settlements_exclude_due_cancelled_refunds_demo_and_stripe_test(self):
        paid = self.order(self.customer, amount='100.00')
        self.order(self.customer, payment='due', status='confirmed', amount='20.00')
        self.order(self.customer, payment='refunded', amount='30.00')
        self.order(self.customer, status='cancelled', amount='40.00')
        self.order(self.customer, payment='simulated', method='simulation', demo=True, amount='50.00')
        self.order(self.customer, method='stripe', amount='60.00')
        self.order(self.customer, demo=True, amount='70.00')
        self.order(self.customer, status='cancelled', payment='simulated', method='simulation', demo=True, amount='80.00')
        self.order(self.other, amount='90.00')
        guest = self.order(amount='200.00')
        response = self.client.get(self.url('customer_detail', self.customer.pk))
        account = response.context['customer_account']
        self.assertEqual(account.crm_paid_total, Decimal('100.00'))
        self.assertEqual(account.crm_simulated_total, Decimal('180.00'))
        self.assertEqual(account.crm_order_count, 8)
        self.assertContains(response, 'Montant réglé sur place')
        self.assertContains(response, 'Simulation et test')
        self.assertContains(response, 'Paiement test')
        ids = {order.pk for order in response.context['customer_orders']}
        self.assertIn(paid.pk, ids)
        self.assertNotIn(guest.pk, ids)
        listed = self.client.get(self.url(), {'q': self.customer.email}).context['customers'][0]
        self.assertEqual(listed.crm_paid_total, Decimal('100.00'))

    @override_settings(DEMO_MODE=False, PAYMENT_MODE='on_site')
    def test_test_payments_never_become_real_revenue_when_demo_is_disabled(self):
        self.order(self.customer, method='stripe', amount='99.00')
        self.order(self.customer, method='simulation', payment='simulated', demo=True)
        response = self.client.get(self.url('customer_detail', self.customer.pk))
        self.assertEqual(response.context['customer_account'].crm_paid_total, Decimal('0.00'))
        self.assertNotContains(response, 'Simulation et test')
        self.assertContains(response, 'Paiement test')

    def test_order_identity_is_only_the_account_fk_never_unverified_contact(self):
        linked = self.order(self.customer)
        other = self.order(self.other)
        guest = self.order()
        response = self.client.get(self.url('customer_detail', self.customer.pk))
        self.assertEqual([order.pk for order in response.context['customer_orders']], [linked.pk])
        self.assertNotContains(response, guest.pk)
        self.assertNotContains(response, other.pk)
        guest.refresh_from_db()
        self.assertIsNone(guest.user_id)

    def test_phone_prefers_profile_and_marks_order_snapshot_fallback(self):
        order = self.order(self.customer)
        response = self.client.get(self.url('customer_detail', self.customer.pk))
        self.assertEqual(response.context['customer_phone'], '0612345678')
        self.assertFalse(response.context['phone_from_order'])
        self.customer.phone = ''
        self.customer.save(update_fields=['phone'])
        response = self.client.get(self.url('customer_detail', self.customer.pk))
        self.assertEqual(response.context['customer_phone'], '0699999999')
        self.assertTrue(response.context['phone_from_order'])
        self.assertContains(response, 'Téléphone de la dernière commande')
        self.assertContains(response, f'Fourni pour la commande {order.pk}')
        order.customer = {'phone': 123}
        order.save(update_fields=['customer'])
        response = self.client.get(self.url('customer_detail', self.customer.pk))
        self.assertEqual(response.context['customer_phone'], '')
        self.assertContains(response, 'Non renseigné')

    def test_search_matches_name_email_phone_and_escapes_untrusted_text(self):
        for query in ['Camille', 'CAMILLE@EXAMPLE.COM', '0612345678']:
            with self.subTest(query=query):
                response = self.client.get(self.url(), {'q': query})
                self.assertEqual([user.pk for user in response.context['customers']], [self.customer.pk])
        payload = '<script>alert("client")</script>'
        self.customer.first_name = payload
        self.customer.save(update_fields=['first_name'])
        response = self.client.get(self.url(), {'q': payload})
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, payload)
        response = self.client.get(self.url('customer_detail', self.customer.pk))
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, payload)
        response = self.client.get(self.url(), {'q': "' OR 1=1 --"})
        self.assertEqual(response.context['page_obj'].paginator.count, 0)

    def test_client_pagination_bounds_search_and_preserves_context(self):
        User.objects.bulk_create([User(email=f'page-{i}@example.com', first_name=f'Page Client {i:02}') for i in range(24)])
        response = self.client.get(self.url(), {'q': 'Page Client', 'page': 2})
        self.assertEqual(response.context['page_obj'].paginator.count, 24)
        self.assertEqual(len(response.context['customers']), 4)
        self.assertContains(response, 'customer_page=2')
        self.assertEqual(self.client.get(self.url(), {'page': 'Infinity'}).context['page_obj'].number, 1)
        self.assertEqual(self.client.get(self.url(), {'page': '9' * 200}).context['page_obj'].number, 2)
        self.assertEqual(len(self.client.get(self.url(), {'q': 'x' * 200}).context['q']), 140)

    def test_phone_search_ignores_separators_in_both_stored_value_and_query(self):
        for stored, query in [
            ('06 12 34 56 78', '0612345678'),
            ('06-12-34-56-78', '06.12.34.56.78'),
            ('(06)12.34 56-78', '06 12 34 56 78'),
            ('0612345678', '(06) 12-34.56 78'),
            ('+33 (6) 12.34-56.78', '+33612345678'),
            ('33612345678', '+33 (6)12 34 56 78'),
            ('06\u00a012\u202f34 56 78', '0612345678'),
        ]:
            with self.subTest(stored=stored, query=query):
                self.customer.phone = stored
                self.customer.save(update_fields=['phone'])
                response = self.client.get(self.url(), {'q': query})
                self.assertEqual([user.pk for user in response.context['customers']], [self.customer.pk])
                self.assertEqual(response.context['q'], query)
                self.assertContains(response, stored)
                self.customer.refresh_from_db()
                self.assertEqual(self.customer.phone, stored)

    def test_phone_normalization_does_not_broaden_names_or_email_searches(self):
        self.other.first_name = 'Client-0612345678'
        self.other.last_name = 'B612'
        self.other.email = 'contact0612345678@example.com'
        self.other.save(update_fields=['first_name', 'last_name', 'email'])
        for query in [self.other.first_name, 'B612', self.other.email]:
            with self.subTest(query=query):
                response = self.client.get(self.url(), {'q': query})
                self.assertEqual([user.pk for user in response.context['customers']], [self.other.pk])
        response = self.client.get(self.url(), {'q': '+ (-.)'})
        self.assertEqual(response.context['page_obj'].paginator.count, 0)

    def test_order_history_is_paginated_and_last_order_uses_date(self):
        oldest = self.order(self.customer)
        Order.objects.filter(pk=oldest.pk).update(date=timezone.now() - timedelta(days=2))
        for _ in range(21):
            self.order(self.customer)
        response = self.client.get(self.url('customer_detail', self.customer.pk), {'page': 2, 'q': 'Camille & Cie', 'customer_page': 3})
        self.assertEqual(response.context['page_obj'].paginator.count, 22)
        self.assertEqual(len(response.context['customer_orders']), 2)
        self.assertIn(oldest.pk, [order.pk for order in response.context['customer_orders']])
        self.assertNotEqual(response.context['customer_account'].crm_last_order_at.date(), (timezone.now() - timedelta(days=2)).date())
        self.assertIn('q=Camille+%26+Cie', response.context['customer_list_url'])
        self.assertIn('page=3', response.context['customer_list_url'])

    def test_four_main_sections_and_customer_permission_aware_navigation(self):
        self.grant(self.staff, 'view_customer', 'view_order')
        response = self.client.get(self.url())
        self.assertContains(response, f'href="{self.url()}" aria-current="page"')
        self.assertContains(response, 'aria-label="Rubriques de Mon restaurant"')
        self.assertNotContains(response, '>Réglages</a>')
        self.grant(self.staff, 'view_restaurant', 'view_order')
        response = self.client.get(self.url('restaurant'))
        self.assertNotContains(response, '>Clients</a>')
        self.assertFalse(response.context['permissions']['view_customers'])

    def test_order_cards_link_to_client_only_with_both_permissions(self):
        linked = self.order(self.customer)
        self.order()
        self.grant(self.staff, 'view_order')
        response = self.client.get(self.url('orders'), {'status': 'all'})
        self.assertNotContains(response, 'Voir la fiche client')
        self.grant(self.staff, 'view_order', 'view_customer')
        response = self.client.get(self.url('orders'), {'status': 'all'})
        self.assertContains(response, f'href="{self.url("customer_detail", linked.user_id)}"')
        self.assertContains(response, 'Voir la fiche client', count=1)
