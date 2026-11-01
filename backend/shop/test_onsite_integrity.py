"""Independent release checks: immutable ledger and real PostgreSQL row locks."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from .models import Category, OnSitePaymentEvent, Order, Product, Restaurant
from .onsite_payments import record_payment


def make_order():
    return Order.objects.create(scope='independent-onsite', idempotency_key=uuid.uuid4().hex,
                                payload_hash='d' * 64, mode='À emporter', payment_method='on_site',
                                payment_status='due', subtotal=Decimal('17.80'), total=Decimal('17.80'),
                                customer={'name': 'Recette indépendante'}, demo_mode=False)


class OnSiteLedgerIntegrityTests(TestCase):
    def setUp(self):
        self.order = make_order()
        self.actor = get_user_model().objects.create_user('ledger-a@example.invalid', 'Release-Test-93!', is_staff=True)
        self.other = get_user_model().objects.create_user('ledger-b@example.invalid', 'Release-Test-93!', is_staff=True)
        self.event = OnSitePaymentEvent.objects.create(order=self.order, actor=self.actor,
                                                       kind='collected', amount=self.order.total)

    def assert_original(self):
        self.event.refresh_from_db()
        self.assertEqual(self.event.amount, Decimal('17.80'))
        self.assertEqual(self.event.actor_id, self.actor.pk)
        self.assertEqual(OnSitePaymentEvent.objects.count(), 1)

    def test_bulk_upsert_cannot_rewrite_an_existing_financial_event(self):
        replacement = OnSitePaymentEvent(order=self.order, actor=self.other, kind='collected', amount=Decimal('0.01'))
        with self.assertRaises(ValidationError):
            OnSitePaymentEvent.objects.bulk_create([replacement], update_conflicts=True,
                                                    update_fields=['amount', 'actor'], unique_fields=['order', 'kind'])
        self.assert_original()

    def test_new_instance_with_existing_pk_cannot_rewrite_a_financial_event(self):
        replacement = OnSitePaymentEvent(pk=self.event.pk, order=self.order, actor=self.other,
                                          kind='collected', amount=Decimal('0.01'), created_at=self.event.created_at)
        with self.assertRaises(ValidationError):
            replacement.save()
        self.assert_original()


@skipUnlessDBFeature('has_select_for_update')
class ConcurrentOnSitePaymentTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.order = make_order()
        self.actors = []
        permissions = list(Permission.objects.filter(content_type__app_label='shop',
                           codename__in=['view_order', 'change_order', 'record_onsite_payment']))
        self.assertEqual(len(permissions), 3)
        for index in range(2):
            actor = get_user_model().objects.create_user(f'parallel-{index}@example.invalid',
                                                         'Release-Test-93!', is_staff=True)
            actor.user_permissions.set(permissions)
            self.actors.append(actor)

    def parallel_actions(self, actions):
        barrier = Barrier(2)

        def execute(actor_id, kind, expected_status, expected_payment_status):
            try:
                actor = get_user_model().objects.get(pk=actor_id)
                barrier.wait(timeout=10)
                try:
                    result, changed = record_payment(self.order.pk, actor, kind,
                        expected_status=expected_status, expected_payment_status=expected_payment_status)
                    return ('ok', changed, result.status, result.payment_status)
                except ValidationError:
                    return ('conflict',)
            finally:
                # Connections belong to these threads; never leave PG sessions behind.
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(execute, actor.pk, *action) for actor, action in zip(self.actors, actions)]
            return [future.result(timeout=20) for future in futures]

    def test_two_operators_collect_once_with_the_server_amount(self):
        results = self.parallel_actions([('collected', 'confirmed', 'due')] * 2)
        self.assertEqual(sorted(result[1] for result in results), [False, True], results)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'paid')
        event = self.order.onsite_events.get()
        self.assertEqual((event.kind, event.amount), ('collected', Decimal('17.80')))
        self.assertIn(event.actor_id, [actor.pk for actor in self.actors])

    def test_two_operators_refund_once_and_cancel_service_once(self):
        record_payment(self.order.pk, self.actors[0], 'collected', expected_status='confirmed', expected_payment_status='due')
        results = self.parallel_actions([('refunded', 'confirmed', 'paid')] * 2)
        self.assertEqual(sorted(result[1] for result in results), [False, True], results)
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ('cancelled', 'refunded'))
        self.assertEqual(list(self.order.onsite_events.values_list('kind', 'amount')),
                         [('collected', Decimal('17.80')), ('refunded', Decimal('17.80'))])
        self.assertEqual(self.order.history.filter(status='cancelled').count(), 1)

    def test_collection_replay_racing_refund_never_restores_paid(self):
        record_payment(self.order.pk, self.actors[0], 'collected', expected_status='confirmed', expected_payment_status='due')
        results = self.parallel_actions([('collected', 'confirmed', 'due'), ('refunded', 'confirmed', 'paid')])
        self.assertEqual(results[1], ('ok', True, 'cancelled', 'refunded'), results)
        self.assertIn(results[0], [('conflict',), ('ok', False, 'confirmed', 'paid')])
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status), ('cancelled', 'refunded'))
        self.assertEqual(self.order.onsite_events.count(), 2)

    @override_settings(DEMO_MODE=False, PAYMENT_MODE='on_site')
    def test_two_simultaneous_customer_posts_create_and_notify_once(self):
        Restaurant.objects.create(pk=1, delivery_enabled=False)
        category = Category.objects.create(name='Concurrence')
        product = Product.objects.create(name='Recette', category=category, price=Decimal('4.50'))
        bootstrap = APIClient(enforce_csrf_checks=True)
        bootstrap.get('/api/auth/csrf/')
        cookies = {name: morsel.value for name, morsel in bootstrap.cookies.items()}
        payload = {'mode': 'À emporter', 'paymentMethod': 'on_site',
                   'items': [{'productId': product.pk, 'quantity': 2, 'choices': []}],
                   'customer': {'name': 'Client parallèle', 'email': 'parallel@example.invalid', 'phone': '0612345678'}}
        key = uuid.uuid4().hex
        barrier = Barrier(2)

        def submit():
            try:
                client = APIClient(enforce_csrf_checks=True)
                for name, value in cookies.items():
                    client.cookies[name] = value
                client.credentials(HTTP_X_CSRFTOKEN=cookies['csrftoken'])
                barrier.wait(timeout=10)
                response = client.post('/api/orders/', payload, format='json', HTTP_IDEMPOTENCY_KEY=key)
                return response.status_code, response.data
            finally:
                connections.close_all()

        with patch.object(Restaurant, 'is_open', return_value=True), patch('shop.services.order_confirmed') as notify:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(submit) for _ in range(2)]
                results = [future.result(timeout=20) for future in futures]
            self.assertEqual(sorted(status for status, _ in results), [200, 201], results)
            self.assertEqual(len({body['id'] for _, body in results}), 1)
            created = Order.objects.get(idempotency_key=key)
            self.assertEqual((created.payment_method, created.payment_status, created.total),
                             ('on_site', 'due', Decimal('9.00')))
            self.assertFalse(created.onsite_events.exists())
            notify.assert_called_once_with(created.pk)
