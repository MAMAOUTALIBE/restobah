"""Physical-payment regressions. Django creates and destroys the database for every run."""
import copy
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Category, OnSitePaymentEvent, Order, OrderHistory, Payment, Product, Restaurant
from .onsite_payments import record_payment
from .payments import handle_refund, handle_session, release_checkout
from .services import order_data


@override_settings(DEMO_MODE=False, PAYMENT_MODE='on_site',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   ORDER_NOTIFICATION_EMAILS=['cuisine@example.com'])
class OnSiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restaurant = Restaurant.objects.create(pk=1, delivery_postal_codes=['75011'])
        category = Category.objects.create(name='Burgers')
        cls.product = Product.objects.create(name='Burger', category=category, description='Poulet', price='8.90')
        users = get_user_model()
        cls.manager = users.objects.create_user('finance@example.com', 'Strong-Test-93!', is_staff=True, first_name='Lou')
        cls.second_manager = users.objects.create_user('finance-two@example.com', 'Strong-Test-93!', is_staff=True)
        cls.preparer = users.objects.create_user('preparer@example.com', 'Strong-Test-93!', is_staff=True)
        cls.reader = users.objects.create_user('reader@example.com', 'Strong-Test-93!', is_staff=True)
        cls.customer = users.objects.create_user('customer@example.com', 'Strong-Test-93!')
        cls.inactive = users.objects.create_user('inactive@example.com', 'Strong-Test-93!', is_staff=True, is_active=False)
        for user in [cls.manager, cls.second_manager, cls.inactive]:
            user.user_permissions.set(Permission.objects.filter(content_type__app_label='shop', codename__in=['view_order','change_order','record_onsite_payment']))
        cls.preparer.user_permissions.set(Permission.objects.filter(content_type__app_label='shop', codename__in=['view_order','change_order']))
        cls.reader.user_permissions.set(Permission.objects.filter(content_type__app_label='shop', codename='view_order'))

    def setUp(self):
        cache.clear()
        opened = patch.object(Restaurant, 'is_open', return_value=True)
        opened.start()
        self.addCleanup(opened.stop)
        self.api = APIClient(enforce_csrf_checks=True)
        self.api.get('/api/auth/csrf/')
        self.api.credentials(HTTP_X_CSRFTOKEN=self.api.cookies['csrftoken'].value)
        self.payload = {'mode':'À emporter', 'items':[{'productId':self.product.pk,'quantity':2,'choices':[]}],
                        'customer':{'name':'Client Test','email':'client@example.com','phone':'0612345678'}, 'paymentMethod':'on_site'}

    def create(self, key=None, payload=None):
        return self.api.post('/api/orders/', payload or self.payload, format='json', HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)

    def order(self, status='confirmed', payment_status='due', payment_method='on_site', total='17.80'):
        order = Order.objects.create(scope='onsite-tests', idempotency_key=uuid.uuid4().hex, payload_hash='f'*64,
                                     mode='À emporter', status=status, payment_status=payment_status, payment_method=payment_method,
                                     subtotal=Decimal(total), total=Decimal(total), customer=self.payload['customer'], demo_mode=False)
        OrderHistory.objects.create(order=order, status=status)
        return order

    def record(self, order, kind='collected', actor=None, **kwargs):
        return record_payment(order.pk, actor or self.manager, kind, expected_status=kwargs.get('expected_status',order.status),
                              expected_payment_status=kwargs.get('expected_payment_status',order.payment_status))

    def crm(self, user=None, csrf=False):
        client = Client(enforce_csrf_checks=csrf)
        client.force_login(user or self.manager)
        client.get(reverse('crm:orders'))
        return client

    def action(self, client, order, name='order_collect', **extras):
        data = {'expected_status':order.status, 'expected_payment_status':order.payment_status,
                'return_filter':'all', 'return_q':'Client Test', 'return_page':'1', **extras}
        return client.post(reverse(f'crm:{name}', args=[order.pk]), data)

    def test_guest_creation_is_real_confirmed_due_with_exact_totals(self):
        with self.captureOnCommitCallbacks(execute=True), patch('shop.payments.stripe.checkout.Session.create') as stripe:
            response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data['status'],response.data['paymentStatus'],response.data['paymentMethod']), ('confirmed','due','on_site'))
        self.assertEqual(response.data['total'], 17.8)
        order = Order.objects.get(pk=response.data['id'])
        self.assertFalse(order.demo_mode)
        self.assertEqual(order.payment_method, 'on_site')
        self.assertFalse(order.onsite_events.exists())
        self.assertFalse(Payment.objects.exists())
        stripe.assert_not_called()
        self.assertEqual(len(mail.outbox),2)
        for message in mail.outbox:
            self.assertIn('À régler au restaurant', message.body)
            self.assertNotIn('Paiement confirmé', message.body)
            self.assertNotIn('Stripe', message.body)
            self.assertNotIn('démonstration', message.body)

    def test_authenticated_delivery_fee_and_label(self):
        self.api.force_authenticate(self.customer)
        self.payload['mode']='Livraison'
        self.payload['customer'].update(address='24 rue du Test',postal='75011',city='Paris')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.create()
        self.assertEqual(response.status_code,201,response.data)
        order = Order.objects.get(pk=response.data['id'])
        self.assertEqual(order.user,self.customer)
        self.assertEqual(order.total,Decimal('21.70'))
        self.assertEqual(order.payment_label,'À régler à la livraison')
        self.assertIn('À régler à la livraison',mail.outbox[0].body)

    def test_idempotence_does_not_duplicate_confirmation_or_order(self):
        key=uuid.uuid4().hex
        with self.captureOnCommitCallbacks(execute=True):
            first=self.create(key)
            second=self.create(key)
        self.assertEqual((first.status_code,second.status_code),(201,200))
        self.assertEqual(first.data['id'],second.data['id'])
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(len(mail.outbox),2)
        self.assertEqual(OrderHistory.objects.count(),1)

    def test_changed_method_cannot_mutate_existing_order_even_after_mode_switch(self):
        key=uuid.uuid4().hex
        response=self.create(key)
        with override_settings(PAYMENT_MODE='stripe'):
            self.assertEqual(self.create(key).status_code,200)
            changed=copy.deepcopy(self.payload)
            changed['paymentMethod']='stripe'
            self.assertEqual(self.create(key,changed).status_code,409)
        self.assertEqual(Order.objects.get(pk=response.data['id']).payment_method,'on_site')

    def test_pause_closed_unavailable_wrong_method_and_forged_amount_rejected(self):
        Restaurant.objects.filter(pk=1).update(ordering_enabled=False)
        self.assertEqual(self.create().status_code,400)
        Restaurant.objects.filter(pk=1).update(ordering_enabled=True)
        with patch.object(Restaurant,'is_open',return_value=False):
            self.assertEqual(self.create().status_code,400)
        Product.objects.filter(pk=self.product.pk).update(available=False)
        self.assertEqual(self.create().status_code,400)
        Product.objects.filter(pk=self.product.pk).update(available=True)
        for field,value in [('total',0.01),('payment_status','paid'),('actor',self.manager.pk)]:
            payload={**self.payload,field:value}
            self.assertEqual(self.create(payload=payload).status_code,400)
        self.payload['paymentMethod']='simulation'
        self.assertEqual(self.create().status_code,400)
        self.assertFalse(Order.objects.exists())

    def test_smtp_failure_preserves_confirmed_order(self):
        with patch('shop.notifications.send_mail',side_effect=RuntimeError('smtp unavailable')), self.assertLogs('shop.notifications','ERROR'), self.captureOnCommitCallbacks(execute=True):
            response=self.create()
        self.assertEqual(response.status_code,201)
        self.assertEqual(Order.objects.get().payment_status,'due')

    def test_due_order_can_prepare_and_ready_but_not_complete(self):
        order=self.order()
        order.transition('preparing')
        order.transition('ready')
        with self.assertRaisesMessage(ValidationError,'encaissement'):
            order.transition('completed')
        self.assertEqual(list(order.history.values_list('status',flat=True)),['confirmed','preparing','ready'])

    def test_due_cancellation_clears_balance_without_event(self):
        order=self.order()
        with patch('shop.payments.stripe.checkout.Session.retrieve') as retrieve:
            order.transition('cancelled')
            release_checkout(order)
        order.refresh_from_db()
        self.assertEqual((order.status,order.payment_status),('cancelled','cancelled'))
        self.assertFalse(order.onsite_events.exists())
        retrieve.assert_not_called()

    def test_collect_exact_server_amount_actor_and_time_then_complete(self):
        order=self.order(status='ready')
        result,changed=self.record(order)
        self.assertTrue(changed)
        self.assertEqual(result.payment_status,'paid')
        event=order.onsite_events.get()
        self.assertEqual((event.kind,event.amount,event.actor),('collected',order.total,self.manager))
        self.assertIsNotNone(event.created_at)
        result.transition('completed')
        self.assertEqual(result.status,'completed')
        self.assertEqual(result.payment_label,'Réglé sur place')

    def test_collect_replay_by_second_operator_is_idempotent(self):
        order=self.order()
        self.record(order)
        result,changed=self.record(order,actor=self.second_manager)
        self.assertFalse(changed)
        self.assertEqual(result.payment_status,'paid')
        self.assertEqual(order.onsite_events.count(),1)
        self.assertEqual(order.onsite_events.get().actor,self.manager)
        self.assertEqual(order.history.count(),1)

    def test_refund_active_cancels_atomically_and_replay_is_idempotent(self):
        order,_=self.record(self.order(status='preparing'))
        refunded,changed=self.record(order,'refunded')
        self.assertTrue(changed)
        self.assertEqual((refunded.status,refunded.payment_status),('cancelled','refunded'))
        self.assertEqual(order.onsite_events.get(kind='refunded').amount,order.total)
        replay,changed=self.record(order,'refunded')
        self.assertFalse(changed)
        self.assertEqual(replay.status,'cancelled')
        self.assertEqual(order.onsite_events.count(),2)
        self.assertEqual(order.history.filter(status='cancelled').count(),1)
        with self.assertRaises(ValidationError):
            self.record(order,'collected',expected_payment_status='due')
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status,'refunded')

    def test_completed_refund_preserves_service_status(self):
        order,_=self.record(self.order(status='ready'))
        order.transition('completed')
        result,_=self.record(order,'refunded')
        self.assertEqual((result.status,result.payment_status),('completed','refunded'))
        self.assertFalse(order.history.filter(status='cancelled').exists())

    def test_no_refund_without_recorded_collection_or_wrong_origin(self):
        cases=[self.order(),self.order(payment_status='paid'),self.order(payment_status='simulated',payment_method='simulation'),
               self.order(payment_status='paid',payment_method='stripe')]
        for order in cases:
            with self.subTest(order=order.pk),self.assertRaises(ValidationError):
                self.record(order,'refunded')
        self.assertFalse(OnSitePaymentEvent.objects.exists())

    def test_invalid_states_stale_request_and_inconsistent_amount_fail_without_write(self):
        for status,payment in [('cancelled','cancelled'),('completed','due'),('confirmed','refunded')]:
            with self.subTest(status=status),self.assertRaises(ValidationError):
                self.record(self.order(status=status,payment_status=payment))
        order=self.order(status='preparing')
        with self.assertRaises(ValidationError):
            self.record(order,expected_status='confirmed')
        OnSitePaymentEvent.objects.create(order=order,kind='collected',amount=Decimal('1.00'),actor=self.manager)
        with self.assertRaises(ValidationError):
            self.record(order)
        order.refresh_from_db()
        self.assertEqual(order.payment_status,'due')

    def test_zero_amount_is_supported_and_constraints_reject_duplicates_negative(self):
        order,_=self.record(self.order(total='0.00'))
        self.assertEqual(order.onsite_events.get().amount,Decimal('0.00'))
        for kind,amount in [('collected','0.00'),('refunded','-1.00')]:
            with self.subTest(kind=kind),self.assertRaises(IntegrityError),transaction.atomic():
                OnSitePaymentEvent.objects.create(order=order,kind=kind,amount=amount,actor=self.manager)

    def test_origin_and_financial_events_are_immutable_and_actor_protected(self):
        order=self.order()
        order.payment_method='stripe'
        with self.assertRaises(ValidationError):
            order.save()
        with self.assertRaises(ValidationError):
            Order.objects.filter(pk=order.pk).update(payment_method='stripe')
        with self.assertRaises(ValidationError):
            Order.objects.bulk_update([order],['payment_method'])
        with self.assertRaises(ValidationError):
            Order.objects.bulk_create([order],update_conflicts=True,update_fields=['payment_method'],unique_fields=['id'])
        order.refresh_from_db()
        self.record(order)
        event=order.onsite_events.get()
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            OnSitePaymentEvent.objects.filter(pk=event.pk).update(amount=0)
        with self.assertRaises(ValidationError):
            OnSitePaymentEvent.objects.filter(pk=event.pk).delete()
        with self.assertRaises(ProtectedError):
            self.manager.delete()
        with self.assertRaises(ProtectedError):
            order.delete()

    def test_service_denies_customers_reader_preparer_inactive(self):
        order=self.order()
        for actor in [self.customer,self.reader,self.preparer,self.inactive]:
            with self.subTest(actor=actor.email),self.assertRaises(PermissionDenied):
                self.record(order,actor=actor)
        self.assertFalse(order.onsite_events.exists())

    def test_crm_actions_require_staff_finance_permission_and_post(self):
        order=self.order()
        for user in [self.customer,self.reader,self.preparer,self.inactive]:
            client=self.crm(user)
            for name in ['order_collect','order_refund']:
                with self.subTest(user=user.email,name=name):
                    self.assertIn(self.action(client,order,name).status_code,[302,403])
        self.assertEqual(self.action(Client(),order).status_code,302)
        self.assertEqual(self.crm().get(reverse('crm:order_collect',args=[order.pk])).status_code,405)
        self.assertFalse(order.onsite_events.exists())

    def test_csrf_and_forged_financial_inputs_rejected(self):
        order=self.order()
        csrf=self.crm(csrf=True)
        self.assertEqual(self.action(csrf,order).status_code,403)
        for field,value in [('amount','0.01'),('actor',self.customer.pk),('payment_method','stripe'),('created_at','2020-01-01')]:
            self.assertEqual(self.action(self.crm(),order,**{field:value}).status_code,400)
        self.assertFalse(order.onsite_events.exists())

    def test_crm_collect_refund_context_and_stale_conflict(self):
        order=self.order()
        client=self.crm()
        response=self.action(client,order)
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,reverse('crm:orders')+'?status=all&q=Client+Test&page=1')
        self.assertEqual(self.action(client,order).status_code,302)
        order.refresh_from_db()
        order.transition('preparing')
        response=self.action(client,order,'order_refund',expected_status='confirmed')
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.context['q'],'Client Test')
        response=self.action(client,order,'order_refund')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,reverse('crm:orders')+'?status=all&q=Client+Test&page=1')

    def test_crm_labels_financial_events_and_reader_visibility(self):
        order=self.order(status='ready')
        page=self.crm().get(reverse('crm:orders'))
        self.assertContains(page,'À régler au restaurant')
        self.assertContains(page,'Enregistrer l’encaissement')
        self.assertContains(page,'avant de terminer')
        reader=self.crm(self.reader).get(reverse('crm:orders'))
        self.assertNotContains(reader,'Enregistrer l’encaissement')
        self.record(order)
        page=self.crm().get(reverse('crm:orders'))
        self.assertContains(page,'Encaissement enregistré')
        self.assertContains(page,'Lou')
        self.assertContains(page,'Confirmer le remboursement et annuler')

    def test_private_api_has_origin_but_no_financial_actor_or_ledger(self):
        order,_=self.record(self.order())
        data=order_data(order,include_customer=True,include_token=True)
        self.assertEqual(data['paymentMethod'],'on_site')
        for key in ['actor','onsite_events','paymentEvents','onsiteEvents']:
            self.assertNotIn(key,data)
        self.assertNotIn(self.manager.email,str(data))
        response=self.api.get(f'/api/orders/{order.pk}/?token={order.access_token}')
        self.assertEqual(response.status_code,200)
        self.assertNotIn(self.manager.email,str(response.data))

    @override_settings(PAYMENT_MODE='stripe',STRIPE_SECRET_KEY='sk_test_fake')
    def test_stripe_paths_never_touch_onsite_even_with_malicious_payment_relation(self):
        order=self.order()
        Payment.objects.create(order=order,session_id='cs_onsite',payment_intent='pi_onsite')
        with patch('shop.payments.stripe.checkout.Session.retrieve') as retrieve,patch('shop.payments.stripe.checkout.Session.create') as create:
            release_checkout(order)
            response=self.api.post(f'/api/orders/{order.pk}/payment/',{'token':order.access_token},format='json')
            self.assertEqual(response.status_code,400,response.data)
            with transaction.atomic():
                handle_session('checkout.session.completed',{'metadata':{'order_id':order.pk},'id':'cs_onsite','payment_status':'paid','amount_total':1780,'currency':'eur'})
                handle_refund({'payment_intent':'pi_onsite','amount_refunded':1780,'currency':'eur'})
            retrieve.assert_not_called()
            create.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.payment_status,'due')
        self.assertFalse(order.onsite_events.exists())

    @override_settings(STRIPE_SECRET_KEY='sk_test_fake')
    def test_old_stripe_order_remains_resumable_after_global_switch(self):
        order=self.order(status='pending_payment',payment_status='pending',payment_method='stripe')
        with patch('shop.payments.stripe.checkout.Session.create',return_value={'id':'cs_old','url':'https://checkout.stripe.com/c/pay/old'}) as create:
            response=self.api.post(f'/api/orders/{order.pk}/payment/',{'token':order.access_token},format='json')
        self.assertEqual(response.status_code,200,response.data)
        create.assert_called_once()
        order.refresh_from_db()
        self.assertEqual(order.payment_method,'stripe')

    def test_admin_financial_register_is_read_only(self):
        request=type('Request',(),{'user':self.manager})()
        model_admin=admin.site._registry[OnSitePaymentEvent]
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
