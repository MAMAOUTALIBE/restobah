"""Audit regressions; all writes belong to Django's disposable test database."""
import uuid
from datetime import datetime, time
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django import forms
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, Closure, OpeningHour, Order, OrderHistory, Product, Restaurant


class ActionForms(HTMLParser):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.current = None
        self.forms = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.current = {} if attrs.get('action') == self.action else None
        if tag == 'input' and self.current is not None and attrs.get('name'):
            self.current[attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form' and self.current is not None:
            self.forms.append(self.current)
            self.current = None


def form_values(form):
    result = {}
    for name, field in form.fields.items():
        value = form[name].value()
        if isinstance(field, forms.BooleanField):
            if value:
                result[name] = 'on'
        elif value is not None:
            result[name] = str(value)
    return result


@override_settings(DEMO_MODE=True, PAYMENT_MODE='simulation')
class CRMAuditRegressions(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_superuser('audit-manager@example.com', 'Isolated-Audit-9x!')
        cls.restaurant = Restaurant.objects.create(pk=1, delivery_enabled=False)
        cls.category = Category.objects.create(name='Recettes audit')
        cls.product = Product.objects.create(name='Recette audit', category=cls.category,
                                             description='Recette du test.', price=Decimal('8.90'))

    def setUp(self):
        self.client.force_login(self.manager)

    def make_orders(self, name='Alice Audit & Cie'):
        for index in range(31):
            order = Order.objects.create(
                scope='audit-test', idempotency_key=uuid.uuid4().hex, payload_hash='a' * 64,
                mode='À emporter', status='confirmed', payment_status='simulated',
                subtotal=Decimal('8.90'), total=Decimal('8.90'),
                customer={'name': name, 'phone': f'060000{index:04d}'},
            )
            OrderHistory.objects.create(order=order, status='confirmed')
        return Order.objects.create(
            scope='audit-test', idempotency_key=uuid.uuid4().hex, payload_hash='b' * 64,
            mode='À emporter', status='confirmed', payment_status='simulated',
            subtotal=Decimal('8.90'), total=Decimal('8.90'), customer={'name': 'Bob hors recherche'},
        )

    def action_from(self, response, order, target):
        action = reverse('crm:order_status', args=[order.pk])
        parser = ActionForms(action)
        parser.feed(response.content.decode())
        return action, next(data for data in parser.forms if data.get('status') == target)

    def test_order_action_and_conflict_keep_the_rendered_search_and_page(self):
        outsider = self.make_orders()
        response = self.client.get(reverse('crm:orders'), {'status': 'all', 'q': 'Alice Audit & Cie', 'page': '2'})
        target = response.context['orders'][0]
        action, data = self.action_from(response, target, 'preparing')
        submitted = self.client.post(action, data)
        self.assertEqual(submitted.status_code, 302)
        query = parse_qs(urlsplit(submitted.url).query)
        self.assertEqual(query.get('q'), ['Alice Audit & Cie'])
        self.assertEqual(query.get('page'), ['2'])
        current = self.client.get(submitted.url)
        self.assertEqual(current.context['q'], 'Alice Audit & Cie')
        self.assertEqual(current.context['page_obj'].number, 2)
        self.assertNotIn(outsider.pk, [order.pk for order in current.context['orders']])
        conflict = self.client.post(action, data)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.context['q'], 'Alice Audit & Cie')
        self.assertEqual(conflict.context['page_obj'].number, 2)
        self.assertNotIn(outsider.pk, [order.pk for order in conflict.context['orders']])
        self.assertEqual(OrderHistory.objects.filter(order=target).count(), 2)

    def test_both_actions_keep_search_and_clamp_a_page_that_becomes_empty(self):
        self.make_orders()
        response = self.client.get(reverse('crm:orders'), {'status': 'confirmed', 'q': 'Alice Audit & Cie', 'page': '2'})
        target = response.context['orders'][0]
        action, data = self.action_from(response, target, 'cancelled')
        self.assertEqual(data.get('return_q'), 'Alice Audit & Cie')
        self.assertEqual(data.get('return_page'), '2')
        submitted = self.client.post(action, data)
        query = parse_qs(urlsplit(submitted.url).query)
        self.assertEqual(query['status'], ['confirmed'])
        self.assertEqual(query['q'], ['Alice Audit & Cie'])
        self.assertEqual(query['page'], ['1'])
        current = self.client.get(submitted.url)
        self.assertEqual(current.context['page_obj'].number, 1)
        self.assertEqual(current.context['page_obj'].paginator.count, 30)

    def test_order_return_fields_are_bounded_and_cannot_choose_an_external_target(self):
        self.make_orders()
        target = Order.objects.filter(customer__name='Alice Audit & Cie').first()
        response = self.client.post(reverse('crm:order_status', args=[target.pk]), {
            'status': 'preparing', 'expected_status': 'confirmed',
            'return_filter': 'https://outside.example/redirect', 'return_q': 'a' * 1000,
            'return_page': 'https://outside.example/page', 'next': 'https://outside.example/',
        })
        self.assertEqual(response.status_code, 302)
        target_url = urlsplit(response.url)
        self.assertEqual(target_url.path, reverse('crm:orders'))
        self.assertEqual(target_url.netloc, '')
        query = parse_qs(target_url.query)
        self.assertEqual(query['status'], ['active'])
        self.assertEqual(query['q'], ['a' * 140])
        self.assertEqual(query['page'], ['1'])

    def restaurant_payload(self):
        response = self.client.get(reverse('crm:restaurant'))
        data = form_values(response.context['form'])
        data.update({'hours-TOTAL_FORMS': '0', 'hours-INITIAL_FORMS': '0',
                     'hours-MIN_NUM_FORMS': '0', 'hours-MAX_NUM_FORMS': '35'})
        return data

    def test_invalid_restaurant_form_keeps_the_saved_badge_and_the_unsaved_draft(self):
        data = self.restaurant_payload()
        data.pop('ordering_enabled', None)
        data['delivery_fee'] = 'montant invalide'
        data['name'] = 'Brouillon conservé'
        response = self.client.post(reverse('crm:restaurant'), data)
        self.restaurant.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.restaurant.ordering_enabled)
        self.assertTrue(response.context['ordering_enabled'])
        self.assertFalse(response.context['form']['ordering_enabled'].value())
        self.assertEqual(response.context['form']['name'].value(), 'Brouillon conservé')
        self.assertIn('delivery_fee', response.context['form'].errors)
        self.assertNotContains(response, 'Commandes en pause')

    def test_invalid_hours_do_not_announce_an_unsaved_reopening(self):
        Restaurant.objects.filter(pk=1).update(ordering_enabled=False)
        data = self.restaurant_payload()
        data['ordering_enabled'] = 'on'
        data['hours-TOTAL_FORMS'] = '1'
        data.update({'hours-0-weekday': '0', 'hours-0-opens': '12:00', 'hours-0-closes': '12:00'})
        response = self.client.post(reverse('crm:restaurant'), data)
        self.restaurant.refresh_from_db()
        self.assertFalse(self.restaurant.ordering_enabled)
        self.assertFalse(response.context['ordering_enabled'])
        self.assertTrue(response.context['form']['ordering_enabled'].value())
        self.assertTrue(response.context['opening_formset'].errors)
        self.assertContains(response, 'Commandes en pause')

    def test_malformed_category_queries_do_not_crash_or_leave_an_invalid_selection(self):
        for category in ('²', '١', '1' * 5000, str(2**63), '-1', 'invalid'):
            with self.subTest(category=category[:30]):
                response = self.client.get(reverse('crm:menu'), {'category': category})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['category_filter'], '')
                self.assertEqual([product.pk for product in response.context['products']], [self.product.pk])

    def test_valid_category_filter_still_selects_the_expected_dishes(self):
        other = Category.objects.create(name='Autre catégorie')
        Product.objects.create(name='Autre plat', category=other, description='Autre recette.', price=Decimal('3.00'))
        response = self.client.get(reverse('crm:menu'), {'category': str(self.category.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['category_filter'], str(self.category.pk))
        self.assertEqual([product.pk for product in response.context['products']], [self.product.pk])

    def test_availability_success_and_conflict_keep_the_rendered_menu_filters(self):
        response = self.client.get(reverse('crm:menu'), {'q': 'Recette audit', 'category': self.category.pk})
        action = reverse('crm:product_availability', args=[self.product.pk])
        parser = ActionForms(action)
        parser.feed(response.content.decode())
        data = parser.forms[0]
        self.assertEqual(data['return_q'], 'Recette audit')
        self.assertEqual(data['return_category'], str(self.category.pk))
        submitted = self.client.post(action, data)
        self.assertEqual(submitted.status_code, 302)
        query = parse_qs(urlsplit(submitted.url).query)
        self.assertEqual(query, {'q': ['Recette audit'], 'category': [str(self.category.pk)]})
        conflict = self.client.post(action, data)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.context['q'], 'Recette audit')
        self.assertEqual(conflict.context['category_filter'], str(self.category.pk))
        self.product.refresh_from_db()
        self.assertFalse(self.product.available)


@override_settings(DEMO_MODE=False, PAYMENT_MODE='simulation')
class OvernightSummaryAuditTests(TestCase):
    def setUp(self):
        self.restaurant = Restaurant.objects.create(pk=1, delivery_enabled=False)

    def public_at(self, at):
        with patch('django.utils.timezone.now', return_value=at):
            response = self.client.get('/api/restaurant/')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def night_service(self):
        OpeningHour.objects.create(restaurant=self.restaurant, weekday=6, opens=time(18), closes=time(2))

    def test_open_continuation_is_shown_instead_of_closed_today(self):
        self.night_service()
        data = self.public_at(datetime(2026, 11, 2, 1, tzinfo=ZoneInfo('Europe/Paris')))
        self.assertTrue(data['isOpen'])
        self.assertIn('02h00', data['hours'])
        self.assertNotEqual(data['hours'], 'Fermé')

    def test_continuation_keeps_the_current_days_planned_services_visible(self):
        self.night_service()
        OpeningHour.objects.create(restaurant=self.restaurant, weekday=0, opens=time(12), closes=time(14))
        data = self.public_at(datetime(2026, 11, 2, 1, tzinfo=ZoneInfo('Europe/Paris')))
        self.assertTrue(data['isOpen'])
        self.assertIn('02h00', data['hours'])
        self.assertIn('12h00 – 14h00', data['hours'])

    def test_exact_closing_boundary_has_no_continuation(self):
        self.night_service()
        data = self.public_at(datetime(2026, 11, 2, 2, tzinfo=ZoneInfo('Europe/Paris')))
        self.assertFalse(data['isOpen'])
        self.assertEqual(data['hours'], 'Fermé')

    def test_a_closure_on_either_service_day_or_current_day_blocks_continuation(self):
        self.night_service()
        at = datetime(2026, 11, 2, 1, tzinfo=ZoneInfo('Europe/Paris'))
        for date in ('2026-11-01', '2026-11-02'):
            with self.subTest(date=date):
                Closure.objects.all().delete()
                Closure.objects.create(restaurant=self.restaurant, date=date)
                data = self.public_at(at)
                self.assertFalse(data['isOpen'])
                self.assertNotIn('02h00', data['hours'])

    def test_dst_repeated_hour_keeps_the_same_local_service_summary(self):
        OpeningHour.objects.create(restaurant=self.restaurant, weekday=5, opens=time(18), closes=time(3))
        for fold in (0, 1):
            with self.subTest(fold=fold):
                data = self.public_at(datetime(2026, 10, 25, 2, 30, tzinfo=ZoneInfo('Europe/Paris'), fold=fold))
                self.assertTrue(data['isOpen'])
                self.assertIn('03h00', data['hours'])

    def test_uniform_week_remains_compact(self):
        for day in range(7):
            OpeningHour.objects.create(restaurant=self.restaurant, weekday=day, opens=time(18), closes=time(2))
        data = self.public_at(datetime(2026, 11, 2, 1, tzinfo=ZoneInfo('Europe/Paris')))
        self.assertEqual((data['days'], data['hours']), ('Tous les jours', '18h00 – 02h00'))
