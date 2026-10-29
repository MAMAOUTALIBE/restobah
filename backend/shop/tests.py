import copy
import json
import uuid
from datetime import datetime,time,timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase,override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from .models import Order,OrderHistory,Product,Choice,Restaurant,Payment,StripeEvent,Closure,OpeningHour,Address

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class APITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo',verbosity=0)
    def setUp(self):
        cache.clear()
        self.client=APIClient(enforce_csrf_checks=True)
        self.csrf(self.client)
        self.payload={'mode':'Livraison','items':[{'productId':1,'quantity':2,'choices':['sauce-maison','extra-cheddar']}],'customer':{'name':'Camille Martin','email':'camille@example.com','phone':'0612345678','address':'24 rue du Test','postal':'75011','city':'Paris','note':''},'paymentMethod':'simulation'}
    def csrf(self,client):
        client.get('/api/auth/csrf/')
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
    def order(self,payload=None,key=None,client=None):
        return (client or self.client).post('/api/orders/',payload or self.payload,format='json',HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)
    def register(self,client=None,email='client@example.com'):
        client=client or self.client
        response=client.post('/api/auth/register/',{'name':'Client Test','email':email,'password':'STC-Test-9x!Strong'},format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.csrf(client)
        return response
    def test_catalog_and_health(self):
        self.assertEqual(self.client.get('/api/health/').status_code,200)
        products=self.client.get('/api/products/').data
        self.assertEqual(len(products),9)
        self.assertEqual(next(p for p in products if p['id']==90)['price'],11.13)
        self.assertEqual(next(p for p in products if p['id']==1)['optionGroups'][0]['min'],1)
    def test_csrf_enforced_for_guest_order_and_register(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertEqual(self.order(client=client).status_code,403)
        self.assertEqual(client.post('/api/auth/register/',{'name':'Test','email':'test@example.com','password':'STC-Test-9x!Strong'},format='json').status_code,403)
        self.assertEqual(client.post('/api/auth/login/',{'email':'x@example.com','password':'x'},format='json').status_code,403)
    def test_totals_snapshot_and_idempotence(self):
        key=uuid.uuid4().hex
        response=self.order(key=key)
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['subtotal'],26.8)
        self.assertEqual(response.data['total'],30.7)
        self.assertEqual(response.data['paymentStatus'],'simulated')
        self.assertEqual(self.order(key=key).status_code,200)
        self.assertEqual(Order.objects.count(),1)
        Product.objects.filter(pk=1).update(price=100)
        self.assertEqual(self.order(key=key).data['total'],30.7)
        self.assertEqual(Order.objects.first().lines.first().unit_price,Decimal('13.40'))
    def test_idempotence_changed_payload_conflict_and_scope(self):
        key=uuid.uuid4().hex
        self.order(key=key)
        changed=copy.deepcopy(self.payload)
        changed['items'][0]['quantity']=1
        self.assertEqual(self.order(changed,key).status_code,409)
        other=APIClient(enforce_csrf_checks=True)
        self.csrf(other)
        self.assertEqual(self.order(key=key,client=other).status_code,201)
    def test_no_client_prices_accepted(self):
        for mutate in ['total','unitPrice','price']:
            payload=copy.deepcopy(self.payload)
            if mutate=='total':
                payload['total']=0.01
            else:
                payload['items'][0][mutate]=0.01
            self.assertEqual(self.order(payload).status_code,400)
        self.assertEqual(Order.objects.count(),0)
    def test_required_unknown_duplicate_excess_choices(self):
        for choices in [[],['extra-cheddar'],['sauce-maison','sauce-barbecue'],['sauce-maison','sauce-maison'],['drink-cola'],['unknown']]:
            payload=copy.deepcopy(self.payload)
            payload['items'][0]['choices']=choices
            self.assertEqual(self.order(payload).status_code,400)
        Choice.objects.filter(pk='sauce-maison').update(available=False)
        self.assertEqual(self.order().status_code,400)
    def test_quantity_bounds_and_boolean(self):
        for quantity in [0,-1,21,True,'2',2.5]:
            payload=copy.deepcopy(self.payload)
            payload['items'][0]['quantity']=quantity
            self.assertEqual(self.order(payload).status_code,400)
    def test_product_unavailable(self):
        Product.objects.filter(pk=1).update(available=False)
        self.assertEqual(self.order().status_code,400)
    def test_promotion_calculated_from_source_and_expiry(self):
        payload=copy.deepcopy(self.payload)
        payload['items']=[{'productId':90,'quantity':1,'choices':['drink-cola']}]
        payload['mode']='À emporter'
        self.assertEqual(self.order(payload).data['total'],11.13)
        Product.objects.filter(pk=2).update(price=Decimal('20.00'))
        self.assertEqual(self.order(payload).data['total'],14)
        Product.objects.filter(pk=90).update(promotion_ends=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.order(payload).status_code,400)
    def test_delivery_zone_and_minimum(self):
        payload=copy.deepcopy(self.payload)
        payload['customer']['postal']='69001'
        self.assertEqual(self.order(payload).status_code,400)
        Restaurant.objects.filter(pk=1).update(min_delivery_total=30)
        self.assertEqual(self.order().status_code,400)
    def test_customer_validation(self):
        for field,value in [('name',' '),('email','bad'),('phone','          '),('phone','123456789'),('postal','123'),('address',''),('city','')]:
            payload=copy.deepcopy(self.payload)
            payload['customer'][field]=value
            self.assertEqual(self.order(payload).status_code,400)
    def test_ordering_disabled(self):
        Restaurant.objects.filter(pk=1).update(ordering_enabled=False)
        self.assertEqual(self.order().status_code,400)
    @override_settings(DEMO_MODE=False)
    def test_production_respects_closure(self):
        restaurant=Restaurant.objects.get(pk=1)
        Closure.objects.create(restaurant=restaurant,date=timezone.localdate())
        self.assertEqual(self.order().status_code,400)
    def test_mode_disabled(self):
        Restaurant.objects.filter(pk=1).update(delivery_enabled=False)
        self.assertEqual(self.order().status_code,400)
    def test_guest_token_and_unicode_and_customer_not_exposed(self):
        response=self.order()
        order_id=response.data['id']
        token=response.data['accessToken']
        other=APIClient()
        self.assertEqual(other.get(f'/api/orders/{order_id}/').status_code,404)
        self.assertEqual(other.get(f'/api/orders/{order_id}/',{'token':'💥'}).status_code,404)
        details=other.get(f'/api/orders/{order_id}/',{'token':token})
        self.assertEqual(details.status_code,200)
        self.assertNotIn('customer',details.data)
        self.assertNotIn('accessToken',details.data)
        self.assertEqual(other.get('/api/orders/').status_code,403)
    def test_account_auth_and_owner_history(self):
        self.register()
        response=self.order()
        self.assertEqual(self.client.get('/api/orders/').data[0]['id'],response.data['id'])
        self.assertIn('customer',self.client.get(f"/api/orders/{response.data['id']}/").data)
        other=APIClient(enforce_csrf_checks=True)
        self.csrf(other)
        self.register(other,'other@example.com')
        self.assertEqual(other.get('/api/orders/').data,[])
        self.assertEqual(other.get(f"/api/orders/{response.data['id']}/").status_code,404)
        self.assertEqual(self.client.post('/api/auth/logout/',{},format='json').status_code,200)
        self.csrf(self.client)
        self.assertIsNone(self.client.get('/api/auth/me/').data['user'])
        login=self.client.post('/api/auth/login/',{'email':'CLIENT@example.com','password':'STC-Test-9x!Strong'},format='json')
        self.assertEqual(login.status_code,200)
    def test_weak_password_and_duplicate_email(self):
        response=self.client.post('/api/auth/register/',{'name':'Test','email':'test@example.com','password':'12345678'},format='json')
        self.assertEqual(response.status_code,400)
        self.register()
        response=self.client.post('/api/auth/register/',{'name':'Other','email':'CLIENT@example.com','password':'STC-Test-9x!Strong'},format='json')
        self.assertEqual(response.status_code,400)
    def test_address_owner_and_invalid_phone(self):
        self.register()
        payload={'label':'Maison','name':'Client Test','phone':'0612345678','address':'24 rue du Test','postal':'75011','city':'Paris'}
        address=self.client.post('/api/addresses/',payload,format='json')
        self.assertEqual(address.status_code,201,address.data)
        other=APIClient(enforce_csrf_checks=True)
        self.csrf(other)
        self.register(other,'other@example.com')
        self.assertEqual(other.patch(f"/api/addresses/{address.data['id']}/",{'city':'Lyon'},format='json').status_code,404)
        self.assertEqual(other.delete(f"/api/addresses/{address.data['id']}/").status_code,404)
        self.assertEqual(self.client.patch(f"/api/addresses/{address.data['id']}/",{'city':'Paris 11'},format='json').status_code,200)
        invalid={**payload,'phone':'          '}
        self.assertEqual(self.client.post('/api/addresses/',invalid,format='json').status_code,400)
        self.assertEqual(self.client.delete(f"/api/addresses/{address.data['id']}/").status_code,204)
    def test_favorites_account_scoped(self):
        self.register()
        self.assertEqual(self.client.put('/api/favorites/',{'productIds':[1,3]},format='json').data,[1,3])
        self.assertEqual(self.client.put('/api/favorites/',{'productIds':[90]},format='json').status_code,400)
        self.assertEqual(self.client.put('/api/favorites/',{'productIds':[False]},format='json').status_code,400)
    def test_reset_response_and_single_use(self):
        self.register()
        self.client.post('/api/auth/logout/',{},format='json')
        self.csrf(self.client)
        a=self.client.post('/api/auth/password-reset/',{'email':'client@example.com'},format='json')
        b=self.client.post('/api/auth/password-reset/',{'email':'nobody@example.com'},format='json')
        self.assertEqual(a.data,b.data)
        self.assertEqual(len(mail.outbox),1)
        user=get_user_model().objects.get(email='client@example.com')
        payload={'uid':urlsafe_base64_encode(force_bytes(user.pk)),'token':default_token_generator.make_token(user),'password':'New-Pass-Test-47!'}
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/',payload,format='json').status_code,200)
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/',payload,format='json').status_code,400)
        self.assertEqual(self.client.post('/api/auth/login/',{'email':'client@example.com','password':'New-Pass-Test-47!'},format='json').status_code,200)
    def test_admin_transitions_and_payment_guards(self):
        self.order()
        order=Order.objects.first()
        order.transition('preparing')
        order.transition('ready')
        order.transition('completed')
        self.assertEqual(order.history.count(),4)
        with self.assertRaises(ValidationError):
            order.transition('preparing')
        order.status='confirmed'
        order.payment_status='paid'
        with self.assertRaises(ValidationError):
            order.transition('cancelled')
    def test_unsigned_webhook_does_not_accept(self):
        response=self.client.post('/api/payments/webhook/',{},format='json')
        self.assertIn(response.status_code,[400,503])
    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test')
    def test_bad_signature(self):
        response=self.client.post('/api/payments/webhook/',{},format='json',HTTP_STRIPE_SIGNATURE='invalid')
        self.assertEqual(response.status_code,400)
    @override_settings(PAYMENT_MODE='stripe',STRIPE_SECRET_KEY='sk_test_placeholder',STRIPE_WEBHOOK_SECRET='whsec_placeholder')
    def test_stripe_checkout_verified_webhook_idempotent(self):
        payload=copy.deepcopy(self.payload)
        payload['paymentMethod']='stripe'
        response=self.order(payload)
        self.assertEqual(response.status_code,201,response.data)
        order=Order.objects.get(pk=response.data['id'])
        self.assertEqual(order.status,'pending_payment')
        self.assertEqual(order.payment_status,'pending')
        with patch('shop.payments.stripe.checkout.Session.create',return_value={'id':'cs_test_123','url':'https://checkout.stripe.com/c/pay/cs_test_123'}) as create:
            checkout=self.client.post(f'/api/orders/{order.id}/payment/',{'token':response.data['accessToken']},format='json')
            self.assertEqual(checkout.status_code,200,checkout.data)
            self.assertEqual(create.call_args.kwargs['line_items'][0]['price_data']['unit_amount'],3070)
        order.refresh_from_db()
        self.assertEqual(order.status,'pending_payment')
        event={'id':'evt_test_1','type':'checkout.session.completed','livemode':False,'data':{'object':{'id':'cs_test_123','metadata':{'order_id':order.id},'amount_total':3070,'currency':'eur','payment_status':'paid','payment_intent':'pi_test_1'}}}
        with patch('shop.payments.stripe.Webhook.construct_event',return_value=event):
            first=self.client.post('/api/payments/webhook/',{},format='json')
            second=self.client.post('/api/payments/webhook/',{},format='json')
            self.assertEqual(first.status_code,200)
            self.assertEqual(second.status_code,200)
        order.refresh_from_db()
        self.assertEqual(order.status,'confirmed')
        self.assertEqual(order.payment_status,'paid')
        self.assertEqual(order.history.filter(status='confirmed').count(),1)
        refund={'id':'evt_refund','type':'charge.refunded','livemode':False,'data':{'object':{'payment_intent':'pi_test_1','refunded':True,'amount_refunded':3070,'currency':'eur'}}}
        with patch('shop.payments.stripe.Webhook.construct_event',return_value=refund):
            self.client.post('/api/payments/webhook/',{},format='json')
        order.refresh_from_db()
        self.assertEqual(order.status,'cancelled')
        self.assertEqual(order.payment_status,'refunded')
    @override_settings(PAYMENT_MODE='stripe',STRIPE_SECRET_KEY='sk_test_placeholder',STRIPE_WEBHOOK_SECRET='whsec_placeholder')
    def test_wrong_amount_webhook_never_marks_paid(self):
        payload=copy.deepcopy(self.payload)
        payload['paymentMethod']='stripe'
        order=Order.objects.get(pk=self.order(payload).data['id'])
        Payment.objects.create(order=order,session_id='cs_test_wrong')
        event={'id':'evt_wrong','type':'checkout.session.completed','livemode':False,'data':{'object':{'id':'cs_test_wrong','metadata':{'order_id':order.id},'amount_total':1,'currency':'eur','payment_status':'paid'}}}
        with patch('shop.payments.stripe.Webhook.construct_event',return_value=event):
            self.client.post('/api/payments/webhook/',{},format='json')
        order.refresh_from_db()
        self.assertEqual(order.payment_status,'pending')
    def test_seed_non_destructive(self):
        Product.objects.filter(pk=1).update(name='Nouveau nom',price=Decimal('12.34'),available=False)
        call_command('seed_demo',verbosity=0)
        product=Product.objects.get(pk=1)
        self.assertEqual(product.name,'Nouveau nom')
        self.assertEqual(product.price,Decimal('12.34'))
        self.assertFalse(product.available)
    def test_overnight_hours(self):
        restaurant=Restaurant.objects.get(pk=1)
        restaurant.opening_hours.all().delete()
        OpeningHour.objects.create(restaurant=restaurant,weekday=4,opens=time(18),closes=time(2))
        friday=datetime(2026,10,23,23,tzinfo=ZoneInfo('Europe/Paris'))
        saturday=datetime(2026,10,24,1,tzinfo=ZoneInfo('Europe/Paris'))
        self.assertTrue(restaurant.is_open(friday))
        self.assertTrue(restaurant.is_open(saturday))
        Closure.objects.create(restaurant=restaurant,date=friday.date())
        self.assertFalse(restaurant.is_open(saturday))

    @override_settings(PAYMENT_MODE='stripe',STRIPE_SECRET_KEY='sk_test_placeholder',STRIPE_WEBHOOK_SECRET='whsec_placeholder')
    def test_interrupted_checkout_resumes_open_session(self):
        payload=copy.deepcopy(self.payload)
        payload['paymentMethod']='stripe'
        response=self.order(payload)
        order=Order.objects.get(pk=response.data['id'])
        Payment.objects.create(order=order,session_id='cs_test_resume',checkout_url='https://checkout.stripe.com/c/pay/resume')
        with patch('shop.payments.stripe.checkout.Session.retrieve',return_value={'status':'open','url':'https://checkout.stripe.com/c/pay/resume'}):
            resumed=self.client.post(f'/api/orders/{order.id}/payment/',{'token':response.data['accessToken']},format='json')
        self.assertEqual(resumed.status_code,200)
        self.assertEqual(resumed.data['url'],'https://checkout.stripe.com/c/pay/resume')
        order.refresh_from_db()
        self.assertEqual(order.status,'pending_payment')
    @override_settings(PAYMENT_MODE='stripe',STRIPE_SECRET_KEY='sk_test_placeholder',STRIPE_WEBHOOK_SECRET='whsec_placeholder')
    def test_expired_checkout_cancels_unpaid_order(self):
        payload=copy.deepcopy(self.payload)
        payload['paymentMethod']='stripe'
        response=self.order(payload)
        order=Order.objects.get(pk=response.data['id'])
        Payment.objects.create(order=order,session_id='cs_test_expired')
        with patch('shop.payments.stripe.checkout.Session.retrieve',return_value={'status':'expired'}):
            expired=self.client.post(f'/api/orders/{order.id}/payment/',{'token':response.data['accessToken']},format='json')
        self.assertEqual(expired.status_code,409)
        order.refresh_from_db()
        self.assertEqual(order.status,'cancelled')
        self.assertEqual(order.payment_status,'cancelled')
    def test_private_development_email_permissions(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            with override_settings(EMAIL_BACKEND='shop.email_backend.PrivateFileEmailBackend',EMAIL_FILE_PATH=directory):
                mail.send_mail('STC test','No sensitive test data','bonjour@stc.example',['client@example.com'])
            files=list(Path(directory).glob('*.log'))
            self.assertEqual(len(files),1)
            self.assertEqual(files[0].stat().st_mode & 0o777,0o600)

    def test_guest_order_requires_preexisting_valid_session(self):
        self.client.cookies.pop('sessionid',None)
        response=self.order()
        self.assertEqual(response.status_code,409)
        self.assertEqual(Order.objects.count(),0)
        self.csrf(self.client)
        self.assertEqual(self.order().status_code,201)
    def test_csrf_bootstrap_creates_stable_session(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertNotIn('sessionid',client.cookies)
        self.csrf(client)
        session_key=client.cookies['sessionid'].value
        self.csrf(client)
        self.assertEqual(client.cookies['sessionid'].value,session_key)

from django.test import TransactionTestCase
from django.db import close_old_connections,connections
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation')
class ConcurrentGuestOrderTests(TransactionTestCase):
    reset_sequences=True
    def setUp(self):
        cache.clear()
        call_command('seed_demo',verbosity=0)
    def test_concurrent_first_guest_posts_create_one_order(self):
        bootstrap=APIClient(enforce_csrf_checks=True)
        bootstrap.get('/api/auth/csrf/')
        cookies={k:v.value for k,v in bootstrap.cookies.items()}
        payload={'mode':'À emporter','items':[{'productId':6,'quantity':1,'choices':[]}],'customer':{'name':'Client Concurrent','email':'concurrent@example.com','phone':'0612345678'},'paymentMethod':'simulation'}
        key=uuid.uuid4().hex
        barrier=Barrier(2)
        def submit():
            close_old_connections()
            client=APIClient(enforce_csrf_checks=True)
            for name,value in cookies.items():
                client.cookies[name]=value
            client.credentials(HTTP_X_CSRFTOKEN=cookies['csrftoken'])
            try:
                barrier.wait(timeout=10)
                response=client.post('/api/orders/',payload,format='json',HTTP_IDEMPOTENCY_KEY=key)
                return response.status_code,response.data
            finally:
                # Persistent PostgreSQL connections belong to this worker thread.
                # Close them explicitly so Django can drop its temporary test DB.
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as workers:
            results=list(workers.map(lambda _:submit(),range(2)))
        self.assertEqual(sorted(status for status,_ in results),[200,201],results)
        self.assertEqual(len({body['id'] for _,body in results}),1)
        self.assertEqual(Order.objects.count(),1)

@override_settings(DEMO_MODE=True,PAYMENT_MODE='stripe',STRIPE_SECRET_KEY='sk_test_placeholder',STRIPE_WEBHOOK_SECRET='whsec_placeholder')
class OutOfOrderPaymentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo',verbosity=0)
    def test_refund_before_checkout_confirmation_stays_refunded(self):
        client=APIClient(enforce_csrf_checks=True)
        client.get('/api/auth/csrf/')
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        payload={'mode':'À emporter','items':[{'productId':6,'quantity':1,'choices':[]}],'customer':{'name':'Client Stripe','email':'stripe@example.com','phone':'0612345678'},'paymentMethod':'stripe'}
        response=client.post('/api/orders/',payload,format='json',HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)
        self.assertEqual(response.status_code,201,response.data)
        order=Order.objects.get(pk=response.data['id'])
        with patch('shop.payments.stripe.checkout.Session.create',return_value={'id':'cs_test_early','url':'https://checkout.stripe.com/c/pay/early'}) as create:
            checkout=client.post(f'/api/orders/{order.id}/payment/',{'token':response.data['accessToken']},format='json')
            self.assertEqual(checkout.status_code,200)
            self.assertEqual(create.call_args.kwargs['payment_intent_data']['metadata']['order_id'],order.id)
        refund={'id':'evt_early_refund','type':'charge.refunded','livemode':False,'data':{'object':{'payment_intent':'pi_test_early','metadata':{'order_id':order.id},'refunded':True,'amount_refunded':390,'currency':'eur'}}}
        complete={'id':'evt_delayed_complete','type':'checkout.session.completed','livemode':False,'data':{'object':{'id':'cs_test_early','metadata':{'order_id':order.id},'payment_intent':'pi_test_early','amount_total':390,'currency':'eur','payment_status':'paid'}}}
        for event in [refund,complete,refund]:
            with patch('shop.payments.stripe.Webhook.construct_event',return_value=event):
                self.assertEqual(client.post('/api/payments/webhook/',{},format='json').status_code,200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status,'refunded')
        self.assertEqual(order.status,'cancelled')
        self.assertEqual(order.history.filter(status='cancelled').count(),1)

@override_settings(ADMIN_LOGIN_LIMIT=2,ADMIN_LOGIN_WINDOW=60,TRUST_PROXY=False)
class AdminThrottleTests(TestCase):
    def login(self,**headers):
        return self.client.post('/admin/login/',{'username':'unknown@example.com','password':'invalid'},**headers)
    def test_rate_limit_and_get_remains_accessible(self):
        from .models import AdminLoginAttempt
        self.assertEqual(self.client.get('/admin/login/').status_code,200)
        self.assertEqual(self.login().status_code,200)
        self.assertEqual(self.login().status_code,200)
        blocked=self.login()
        self.assertEqual(blocked.status_code,429)
        self.assertGreater(int(blocked['Retry-After']),0)
        self.assertEqual(self.client.get('/admin/login/').status_code,200)
        counter=AdminLoginAttempt.objects.get()
        self.assertEqual(counter.count,2)
        self.assertNotIn('127.0.0.1',counter.key)
    def test_expired_window_allows_login_again(self):
        from .models import AdminLoginAttempt
        self.login()
        self.login()
        self.assertEqual(self.login().status_code,429)
        AdminLoginAttempt.objects.update(window_started=timezone.now()-timedelta(seconds=61))
        self.assertEqual(self.login().status_code,200)
    def test_untrusted_header_cannot_bypass_limit(self):
        self.login(HTTP_X_REAL_IP='192.0.2.1')
        self.login(HTTP_X_REAL_IP='192.0.2.2')
        self.assertEqual(self.login(HTTP_X_REAL_IP='192.0.2.3').status_code,429)
    @override_settings(TRUST_PROXY=True)
    def test_trusted_proxy_addresses_are_distinguished(self):
        self.login(HTTP_X_REAL_IP='192.0.2.1')
        self.login(HTTP_X_REAL_IP='192.0.2.1')
        self.assertEqual(self.login(HTTP_X_REAL_IP='192.0.2.1').status_code,429)
        self.assertEqual(self.login(HTTP_X_REAL_IP='192.0.2.2').status_code,200)
    def test_unrelated_api_route_not_throttled(self):
        self.login()
        self.login()
        self.assertEqual(self.client.get('/api/health/').status_code,200)
    def test_dev_admin_uses_configured_runtime_directory(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            with override_settings(DEBUG=True,RUNTIME_DIR=Path(directory)):
                call_command('dev_admin',verbosity=0)
            target=Path(directory)/'admin-credentials.txt'
            self.assertTrue(target.exists())
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
