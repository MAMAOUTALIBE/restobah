"""Regression tests for the reliability audit (errors, availability, e-mails, Stripe cancellation)."""
import copy
import hashlib
import hmac
import json
import time
import uuid
from datetime import time as clock, timedelta
from unittest import skipUnless
from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
import stripe
from .admin import OrderAdmin, OrderForm
from .models import Address, Category, Choice, OpeningHour, Order, Payment, Product, Restaurant
from .payments import CHECKOUT_WINDOW

WEBHOOK_SECRET = 'whsec_reliability_test'

def signed(payload, secret=WEBHOOK_SECRET, timestamp=None):
    body = json.dumps(payload)
    stamp = int(time.time()) if timestamp is None else timestamp
    signature = hmac.new(secret.encode(), f'{stamp}.{body}'.encode(), hashlib.sha256).hexdigest()
    return body, f't={stamp},v1={signature}'

def session_event(event_id, order, event_type='checkout.session.completed', session='cs_test_rel', amount=None, livemode=False):
    return {'id':event_id,'object':'event','type':event_type,'livemode':livemode,'data':{'object':{'id':session,'object':'checkout.session','metadata':{'order_id':order.id},'amount_total':int(order.total*100) if amount is None else amount,'currency':'eur','payment_status':'paid' if event_type.endswith('completed') else 'unpaid','payment_intent':'pi_test_rel'}}}

class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo',verbosity=0)
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.csrf()
        self.payload = {'mode':'Livraison','items':[{'productId':1,'quantity':2,'choices':['sauce-maison','extra-cheddar']}],'customer':{'name':'Camille Martin','email':'camille@example.com','phone':'0612345678','address':'24 rue du Test','postal':'75011','city':'Paris','note':'Interphone 12'},'paymentMethod':'simulation'}
    def csrf(self):
        self.client.get('/api/auth/csrf/')
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
    def order(self, payload=None, key=None):
        return self.client.post('/api/orders/',payload or self.payload,format='json',HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ErrorMessageTests(Base):
    def test_business_refusal_is_shown_verbatim(self):
        payload = copy.deepcopy(self.payload)
        payload['customer']['postal'] = '69001'
        response = self.order(payload)
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.data['detail'],'Cette adresse est en dehors de notre zone de livraison.')
        Restaurant.objects.filter(pk=1).update(min_delivery_total=100)
        self.assertEqual(self.order().data['detail'],'Le minimum de livraison est de 100.00 €.')
    def test_field_errors_name_the_french_field(self):
        payload = copy.deepcopy(self.payload)
        payload['customer']['phone'] = '06 12 34 56 7'
        self.assertEqual(self.order(payload).data['detail'],'Téléphone : Le téléphone doit contenir entre 10 et 15 chiffres.')
        response = self.client.post('/api/auth/register/',{'name':'Camille','email':'weak@example.com','password':'motdepasse'},format='json')
        self.assertEqual(response.status_code,400)
        self.assertTrue(response.data['detail'].startswith('Mot de passe : '),response.data)
        self.assertIn('errors',response.data)
    def test_item_errors_are_reported(self):
        payload = copy.deepcopy(self.payload)
        payload['items'].append({'productId':6,'quantity':0,'choices':[]})
        self.assertEqual(self.order(payload).data['detail'].replace('\xa0',' '),'Quantité : Assurez-vous que cette valeur est supérieure ou égale à 1.')

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CatalogTests(Base):
    def products(self):
        return {p['id']:p for p in self.client.get('/api/products/').data}
    def test_required_option_without_available_choice_makes_product_unavailable(self):
        Choice.objects.filter(group_id='sauce').update(available=False)
        products = self.products()
        self.assertFalse(products[1]['available'])
        self.assertTrue(products[6]['available'])
        self.assertTrue(products[2]['available'])
    def test_promotion_exposes_server_discount(self):
        promotion = self.products()[90]
        self.assertEqual((promotion['discountPercent'],promotion['regularPrice'],promotion['price']),(30,15.9,11.13))
        self.assertEqual(self.products()[1]['discountPercent'],0)
    def test_categories_follow_administration(self):
        names = [c['name'] for c in self.client.get('/api/categories/').data]
        self.assertEqual(names,['Menus','Burgers','Poulet','Accompagnements','Boissons','Desserts'])
        Category.objects.create(name='Salades',position=1)
        names = [c['name'] for c in self.client.get('/api/categories/').data]
        self.assertEqual(names[:3],['Menus','Burgers','Salades'])
    def test_allergens_must_be_a_list_of_names(self):
        product = Product.objects.get(pk=4)
        product.allergens = 'gluten, lait'
        with self.assertRaises(ValidationError):
            product.full_clean()
        product.allergens = ['gluten','']
        with self.assertRaises(ValidationError):
            product.full_clean()
        product.allergens = ['gluten','lait']
        product.rating = ''
        product.full_clean()
        # Legacy invalid data never reaches the interface as a non-list.
        Product.objects.filter(pk=4).update(allergens='gluten')
        self.assertEqual(self.products()[4]['allergens'],[])
    def test_hours_summary(self):
        restaurant = Restaurant.objects.get(pk=1)
        data = self.client.get('/api/restaurant/').data
        self.assertEqual((data['days'],data['hours']),('Tous les jours','11h30 – 23h00'))
        restaurant.opening_hours.all().delete()
        for day in range(7):
            OpeningHour.objects.create(restaurant=restaurant,weekday=day,opens=clock(11,30),closes=clock(14,30))
            OpeningHour.objects.create(restaurant=restaurant,weekday=day,opens=clock(18,30),closes=clock(23))
        self.assertEqual(self.client.get('/api/restaurant/').data['hours'],'11h30 – 14h30 · 18h30 – 23h00')
        OpeningHour.objects.filter(weekday=timezone.localdate().weekday()).delete()
        data = self.client.get('/api/restaurant/').data
        self.assertTrue(data['days'].startswith('Aujourd’hui'))
        self.assertEqual(data['hours'],'Fermé')

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',ORDER_NOTIFICATION_EMAILS=['cuisine@example.com'],FRONTEND_URL='https://stc.example')
class EmailTests(Base):
    def test_confirmation_and_team_alert_sent_once(self):
        key = uuid.uuid4().hex
        with self.captureOnCommitCallbacks(execute=True):
            response = self.order(key=key)
        self.assertEqual(response.status_code,201)
        self.assertEqual(len(mail.outbox),2)
        customer, team = mail.outbox
        self.assertEqual(customer.to,['camille@example.com'])
        self.assertIn(response.data['id'],customer.subject)
        self.assertIn('Total TTC : 30,70 €',customer.body)
        self.assertIn(f"https://stc.example/?order_id={response.data['id']}&token={response.data['accessToken']}",customer.body)
        self.assertIn('Commande de démonstration',customer.body)
        self.assertEqual(team.to,['cuisine@example.com'])
        self.assertIn('0612345678',team.body)
        self.assertIn('Interphone 12',team.body)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.order(key=key).status_code,200)
        self.assertEqual(len(mail.outbox),2)
    def test_smtp_failure_never_blocks_the_order(self):
        with patch('shop.notifications.send_mail',side_effect=OSError('smtp down')), self.assertLogs('shop.notifications','ERROR'):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.order()
        self.assertEqual(response.status_code,201)
        self.assertEqual(Order.objects.count(),1)
    def test_reset_smtp_failure_is_logged_with_generic_answer(self):
        get_user_model().objects.create_user('client@example.com','STC-Test-9x!Strong',first_name='Client')
        with patch('shop.views.send_mail',side_effect=OSError('smtp down')), self.assertLogs('shop.accounts','ERROR'):
            response = self.client.post('/api/auth/password-reset/',{'email':'client@example.com'},format='json')
        self.assertEqual(response.status_code,200)
        self.assertIn('Si un compte correspond',response.data['detail'])

@override_settings(DEMO_MODE=True,PAYMENT_MODE='stripe',STRIPE_SECRET_KEY='sk_test_placeholder',STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET,EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class StripeTests(Base):
    def setUp(self):
        super().setUp()
        self.payload['paymentMethod'] = 'stripe'
    def pending(self, session='cs_test_rel'):
        response = self.order()
        self.assertEqual(response.status_code,201,response.data)
        order = Order.objects.get(pk=response.data['id'])
        if session:
            Payment.objects.create(order=order,session_id=session)
        return order, response.data['accessToken']
    def webhook(self, payload, **kwargs):
        body, header = signed(payload, **kwargs)
        return self.client.post('/api/payments/webhook/',data=body,content_type='application/json',HTTP_STRIPE_SIGNATURE=header)

    def test_signed_webhook_confirms_and_emails_once(self):
        order,_ = self.pending()
        event = session_event('evt_rel_paid',order)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.webhook(event).status_code,200)
            self.assertEqual(self.webhook(event).status_code,200)
        order.refresh_from_db()
        self.assertEqual((order.status,order.payment_status),('confirmed','paid'))
        self.assertEqual(order.payment.payment_intent,'pi_test_rel')
        self.assertEqual(len(mail.outbox),1)
        self.assertIn('Paiement confirmé par carte',mail.outbox[0].body)
    def test_signature_tampering_replay_and_livemode_rejected(self):
        order,_ = self.pending()
        body, header = signed(session_event('evt_rel_tampered',order))
        forged = body.replace('"amount_total": 3070','"amount_total": 1')
        self.assertEqual(self.client.post('/api/payments/webhook/',data=forged,content_type='application/json',HTTP_STRIPE_SIGNATURE=header).status_code,400)
        self.assertEqual(self.webhook(session_event('evt_rel_old',order),timestamp=int(time.time())-3600).status_code,400)
        self.assertEqual(self.webhook(session_event('evt_rel_wrong_secret',order),secret='whsec_other').status_code,400)
        self.assertEqual(self.webhook(session_event('evt_rel_live',order,livemode=True)).status_code,400)
        order.refresh_from_db()
        self.assertEqual(order.payment_status,'pending')
    def test_wrong_amount_is_logged_and_never_paid(self):
        order,_ = self.pending()
        with self.assertLogs('shop.payments','ERROR'):
            self.assertEqual(self.webhook(session_event('evt_rel_amount',order,amount=100)).status_code,200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status,'pending')
    def test_checkout_session_expires_quickly_with_stable_retry_key(self):
        order, token = self.pending(session=None)
        with patch('shop.payments.stripe.checkout.Session.create',return_value={'id':'cs_test_new','url':'https://checkout.stripe.com/c/pay/new'}) as create:
            started = time.time()
            self.assertEqual(self.client.post(f'/api/orders/{order.id}/payment/',{'token':token},format='json').status_code,200)
        kwargs = create.call_args.kwargs
        self.assertGreaterEqual(kwargs['expires_at'],started+1800)
        self.assertLessEqual(kwargs['expires_at'],started+1800+60+CHECKOUT_WINDOW+1)
        self.assertEqual(kwargs['idempotency_key'],f'stc-checkout-{order.id}-{int(started)//CHECKOUT_WINDOW}')
    def test_old_unpaid_order_cannot_start_checkout(self):
        order, token = self.pending(session=None)
        Order.objects.filter(pk=order.pk).update(date=timezone.now()-timedelta(minutes=50))
        with patch('shop.payments.stripe.checkout.Session.create') as create:
            response = self.client.post(f'/api/orders/{order.id}/payment/',{'token':token},format='json')
        self.assertEqual(response.status_code,409)
        create.assert_not_called()
        order.refresh_from_db()
        self.assertEqual((order.status,order.payment_status),('cancelled','cancelled'))

    def admin_cancel(self, order):
        form = OrderForm(data={'status':'cancelled'},instance=order)
        valid = form.is_valid()
        if valid:
            request = RequestFactory().post('/')
            request.user = get_user_model().objects.create_superuser('staff@example.com','STC-Test-9x!Strong')
            OrderAdmin(Order,admin.site).save_model(request,order,form,True)
        order.refresh_from_db()
        return valid, form
    def test_admin_cancel_closes_open_session_first(self):
        order,_ = self.pending()
        with patch('shop.payments.stripe.checkout.Session.retrieve',return_value={'status':'open'}), patch('shop.payments.stripe.checkout.Session.expire',return_value={'status':'expired'}) as expire:
            valid, form = self.admin_cancel(order)
        self.assertTrue(valid,form.errors)
        expire.assert_called_once_with('cs_test_rel')
        self.assertEqual((order.status,order.payment_status),('cancelled','cancelled'))
    def test_admin_cancel_refused_when_session_already_paid_or_stripe_down(self):
        order,_ = self.pending()
        with patch('shop.payments.stripe.checkout.Session.retrieve',return_value={'status':'complete'}):
            valid, form = self.admin_cancel(order)
        self.assertFalse(valid)
        self.assertIn('déjà payé',str(form.errors))
        with patch('shop.payments.stripe.checkout.Session.retrieve',side_effect=stripe.APIConnectionError('down')), self.assertLogs('shop.payments','ERROR'):
            valid, form = self.admin_cancel(order)
        self.assertFalse(valid)
        self.assertIn('injoignable',str(form.errors))
        self.assertEqual(order.status,'pending_payment')
    def test_admin_cancel_without_session_needs_no_stripe_call(self):
        order,_ = self.pending(session=None)
        with patch('shop.payments.stripe.checkout.Session.retrieve') as retrieve:
            valid,_ = self.admin_cancel(order)
        self.assertTrue(valid)
        retrieve.assert_not_called()
        self.assertEqual(order.status,'cancelled')
    def test_payment_after_cancellation_is_recorded_and_flagged_for_refund(self):
        order,_ = self.pending()
        order.transition('cancelled')
        with self.assertLogs('shop.payments','ERROR'), self.captureOnCommitCallbacks(execute=True):
            self.webhook(session_event('evt_rel_late',order))
        order.refresh_from_db()
        self.assertEqual((order.status,order.payment_status,order.refund_required),('cancelled','paid',True))
        self.assertEqual(len(mail.outbox),0)
        refund = {'id':'evt_rel_refund','object':'event','type':'charge.refunded','livemode':False,'data':{'object':{'object':'charge','payment_intent':'pi_test_rel','refunded':True,'amount_refunded':int(order.total*100),'currency':'eur'}}}
        self.webhook(refund)
        order.refresh_from_db()
        self.assertEqual((order.status,order.payment_status,order.refund_required),('cancelled','refunded',False))
    def test_stale_orders_command(self):
        old_open,_ = self.pending(session='cs_test_open')
        old_paid,_ = self.pending(session='cs_test_paid')
        old_plain,_ = self.pending(session=None)
        recent,_ = self.pending(session=None)
        Order.objects.filter(pk__in=[old_open.pk,old_paid.pk,old_plain.pk]).update(date=timezone.now()-timedelta(hours=2))
        statuses = {'cs_test_open':'open','cs_test_paid':'complete'}
        with patch('shop.payments.stripe.checkout.Session.retrieve',side_effect=lambda session:{'status':statuses[session]}), patch('shop.payments.stripe.checkout.Session.expire',return_value={'status':'expired'}) as expire:
            call_command('cancel_stale_orders',stdout=open('/dev/null','w'),stderr=open('/dev/null','w'))
        expire.assert_called_once_with('cs_test_open')
        result = dict(Order.objects.values_list('pk','status'))
        self.assertEqual(result[old_open.pk],'cancelled')
        self.assertEqual(result[old_plain.pk],'cancelled')
        self.assertEqual(result[old_paid.pk],'pending_payment')
        self.assertEqual(result[recent.pk],'pending_payment')

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AdminTests(Base):
    def test_search_orders_by_customer_and_readable_details(self):
        order_id = self.order().data['id']
        staff = get_user_model().objects.create_superuser('staff@example.com','STC-Test-9x!Strong')
        browser = self.client_class()
        browser.force_login(staff)
        for query in ['camille@example.com','Camille Martin','0612345678']:
            response = browser.get('/admin/shop/order/',{'q':query})
            self.assertContains(response,order_id)
        self.assertNotContains(browser.get('/admin/shop/order/',{'q':'inconnu@example.com'}),order_id)
        detail = browser.get(f'/admin/shop/order/{order_id}/change/')
        self.assertContains(detail,'<strong>Téléphone</strong> : 0612345678',html=False)

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ThrottleTests(Base):
    def test_order_history_polling_does_not_consume_order_quota(self):
        self.client.post('/api/auth/register/',{'name':'Client Suivi','email':'suivi@example.com','password':'STC-Test-9x!Strong'},format='json')
        self.csrf()
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES,{'orders':'2/hour'}):
            for _ in range(5):
                self.assertEqual(self.client.get('/api/orders/').status_code,200)
            self.assertEqual(self.order().status_code,201)
            self.assertEqual(self.order().status_code,201)
            self.assertEqual(self.order().status_code,429)
            self.assertEqual(self.client.get('/api/orders/').status_code,200)

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation')
class PhotoTests(Base):
    def test_uploaded_photo_replaces_illustration(self):
        import io, tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB',(4,4),'red').save(buffer,'PNG')
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            product = Product.objects.get(pk=4)
            product.photo = SimpleUploadedFile('frites.png',buffer.getvalue(),content_type='image/png')
            product.full_clean()
            product.save()
            image = next(p for p in self.client.get('/api/products/').data if p['id']==4)['image']
        self.assertRegex(image,r'^http://testserver/media/products/frites[^/]*\.png$')
        # The administration form (Pillow) rejects a file that is not a real image.
        from django.forms import modelform_factory
        form = modelform_factory(Product,fields=['photo'])(data={},files={'photo':SimpleUploadedFile('faux.png',b'not an image',content_type='image/png')},instance=product)
        self.assertFalse(form.is_valid())

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RestaurantSettingsTests(Base):
    def test_delivery_needs_a_zone(self):
        restaurant = Restaurant.objects.get(pk=1)
        restaurant.delivery_postal_codes = []
        with self.assertRaises(ValidationError):
            restaurant.full_clean()
        restaurant.delivery_enabled = False
        restaurant.full_clean()
        # A zone emptied outside the form closes delivery instead of accepting every address.
        Restaurant.objects.filter(pk=1).update(delivery_postal_codes=[])
        self.assertFalse(self.client.get('/api/restaurant/').data['deliveryEnabled'])
        self.assertEqual(self.order().data['detail'],'Ce mode de commande n’est pas disponible.')
    def test_displayed_delays_are_configurable(self):
        Restaurant.objects.filter(pk=1).update(pickup_delay='10 min',delivery_delay='45 min')
        data = self.client.get('/api/restaurant/').data
        self.assertEqual((data['pickupDelay'],data['deliveryDelay']),('10 min','45 min'))

@override_settings(DEMO_MODE=True,PAYMENT_MODE='simulation',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountDeletionTests(Base):
    password = 'STC-Test-9x!Strong'
    def register(self):
        response = self.client.post('/api/auth/register/',{'name':'Client Effacé','email':'efface@example.com','password':self.password},format='json')
        self.assertEqual(response.status_code,201)
        self.csrf()
    def test_deletion_requires_password_and_keeps_orders(self):
        self.assertEqual(self.client.post('/api/auth/delete-account/',{'password':self.password},format='json').status_code,403)
        self.register()
        user = get_user_model().objects.get(email='efface@example.com')
        self.client.post('/api/addresses/',{'label':'Maison','name':'Client Effacé','phone':'0612345678','address':'24 rue du Test','postal':'75011','city':'Paris'},format='json')
        self.client.put('/api/favorites/',{'productIds':[1]},format='json')
        order_id = self.order().data['id']
        wrong = self.client.post('/api/auth/delete-account/',{'password':'mauvais'},format='json')
        self.assertEqual((wrong.status_code,wrong.data['detail']),(400,'Mot de passe : Mot de passe incorrect.'))
        response = self.client.post('/api/auth/delete-account/',{'password':self.password},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())
        self.assertFalse(Address.objects.filter(user_id=user.pk).exists())
        order = Order.objects.get(pk=order_id)
        self.assertIsNone(order.user_id)
        self.assertIsNone(self.client.get('/api/auth/me/').data['user'])
        self.csrf()
        self.assertIn(self.client.post('/api/auth/login/',{'email':'efface@example.com','password':self.password},format='json').status_code,[401,403])
    def test_staff_accounts_are_not_self_deleted(self):
        staff = get_user_model().objects.create_user('equipe@example.com',self.password,is_staff=True)
        self.client.force_authenticate(staff)
        response = self.client.post('/api/auth/delete-account/',{'password':self.password},format='json')
        self.assertEqual(response.status_code,400)
        self.assertTrue(get_user_model().objects.filter(pk=staff.pk).exists())

class AdminRefreshAndCacheTests(Base):
    def test_order_list_loads_refresh_script(self):
        staff = get_user_model().objects.create_superuser('staff@example.com','STC-Test-9x!Strong')
        browser = self.client_class()
        browser.force_login(staff)
        self.assertContains(browser.get('/admin/shop/order/'),'shop/admin-orders.js')
    @skipUnless(connection.vendor == 'postgresql','Shared counters are configured for PostgreSQL deployments.')
    def test_rate_limit_counters_are_shared_in_database(self):
        cache.set('stc-shared-probe',3)
        with connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM stc_cache')
            self.assertGreaterEqual(cursor.fetchone()[0],1)
