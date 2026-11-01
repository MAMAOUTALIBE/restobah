"""CRM acceptance tests. All writes use Django's temporary test database/media."""
import io
import tempfile
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PIL import Image
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Category, Closure, OpeningHour, Order, OrderHistory, OrderLine, Product, Restaurant


def image_upload(name='recette.png', size=(24, 18), image_format='PNG', trailer=b''):
    data = io.BytesIO()
    Image.new('RGB', size, '#ff981f').save(data, image_format)
    return SimpleUploadedFile(name, data.getvalue() + trailer, content_type=f'image/{image_format.lower()}')


def posted_form(form):
    """Submit what the rendered form actually exposes, including its revision."""
    data = {}
    for name, field in form.fields.items():
        if isinstance(field, forms.FileField):
            continue
        value = form[name].value()
        if isinstance(field, forms.BooleanField):
            if value:
                data[name] = 'on'
        elif isinstance(field, (forms.MultipleChoiceField, forms.ModelMultipleChoiceField)):
            data[name] = [str(item) for item in value or []]
        elif value is not None:
            data[name] = str(value)
    return data


@override_settings(DEMO_MODE=True, PAYMENT_MODE='simulation', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CRMTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = tempfile.TemporaryDirectory(prefix='stc-crm-tests-')
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        cls.media_directory.cleanup()

    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', verbosity=0)
        users = get_user_model()
        cls.manager = users.objects.create_superuser('crm-manager@example.com', 'CRM-Test-9x!Strong')
        cls.customer = users.objects.create_user('crm-client@example.com', 'CRM-Test-9x!Strong')
        cls.staff = users.objects.create_user('crm-staff@example.com', 'CRM-Test-9x!Strong', is_staff=True)
        cls.reader = users.objects.create_user('crm-reader@example.com', 'CRM-Test-9x!Strong', is_staff=True)
        cls.reader.user_permissions.set(Permission.objects.filter(content_type__app_label='shop', codename__in=['view_product', 'view_order', 'view_restaurant']))

    def setUp(self):
        self.client.force_login(self.manager)

    def url(self, name, pk=None):
        return reverse(f'crm:{name}', args=[] if pk is None else [pk])

    def product_data(self, product=None):
        response = self.client.get(self.url('product_edit', product.pk) if product else self.url('product_add'))
        self.assertEqual(response.status_code, 200)
        return posted_form(response.context['form'])

    def restaurant_data(self, periods=None):
        response = self.client.get(self.url('restaurant'))
        self.assertEqual(response.status_code, 200)
        data = posted_form(response.context['form'])
        formset = response.context['opening_formset']
        prefix = formset.prefix
        if periods is None:
            for key, value in formset.management_form.initial.items():
                data[f'{prefix}-{key}'] = str(value)
            for index, form in enumerate(formset.forms):
                for key, value in posted_form(form).items():
                    data[f'{prefix}-{index}-{key}'] = value
        else:
            existing = list(Restaurant.objects.get(pk=1).opening_hours.all())
            data.update({f'{prefix}-TOTAL_FORMS': str(len(existing) + len(periods)), f'{prefix}-INITIAL_FORMS': str(len(existing)), f'{prefix}-MIN_NUM_FORMS': '0', f'{prefix}-MAX_NUM_FORMS': '1000'})
            for index, period in enumerate(existing):
                data.update({f'{prefix}-{index}-id': str(period.pk), f'{prefix}-{index}-weekday': str(period.weekday), f'{prefix}-{index}-opens': period.opens.strftime('%H:%M'), f'{prefix}-{index}-closes': period.closes.strftime('%H:%M'), f'{prefix}-{index}-DELETE': 'on'})
            for index, period in enumerate(periods, len(existing)):
                for key, value in period.items():
                    data[f'{prefix}-{index}-{key}'] = str(value)
        return data

    def order(self, status='confirmed', payment='simulated'):
        order = Order.objects.create(scope='crm-test', idempotency_key=uuid.uuid4().hex, payload_hash='f' * 64, mode='À emporter', status=status, payment_status=payment, payment_method='simulation' if payment == 'simulated' else 'stripe', subtotal=Decimal('5.00'), total=Decimal('5.00'), customer={'name': 'Client privé', 'email': 'prive@example.com', 'phone': '0612345678'})
        OrderLine.objects.create(order=order, product_id=6, name='Recette historique', quantity=1, unit_price=Decimal('5.00'), total=Decimal('5.00'))
        OrderHistory.objects.create(order=order, status=status)
        return order

    def test_anonymous_customer_and_staff_without_permissions_are_denied(self):
        pages = ['dashboard', 'menu', 'orders', 'restaurant', 'dashboard_fragment', 'orders_fragment']
        self.client.logout()
        for page in pages:
            with self.subTest(page=page, user='anonymous'):
                response = self.client.get(self.url(page))
                self.assertEqual(response.status_code, 302)
                self.assertIn(self.url('login'), response.url)
        for user in [self.customer, self.staff]:
            self.client.force_login(user)
            for page in pages:
                with self.subTest(page=page, user=user.email):
                    self.assertEqual(self.client.get(self.url(page)).status_code, 403)

    def test_reader_can_read_but_cannot_modify_any_module(self):
        self.client.force_login(self.reader)
        for page in ['dashboard', 'menu', 'orders', 'restaurant', 'dashboard_fragment', 'orders_fragment']:
            self.assertEqual(self.client.get(self.url(page)).status_code, 200)
        product = Product.objects.get(pk=6)
        order = self.order()
        writes = [('product_add', None), ('product_edit', product.pk), ('product_availability', product.pk), ('restaurant', None), ('closure_add', None), ('order_status', order.pk)]
        for route, pk in writes:
            with self.subTest(route=route):
                self.assertEqual(self.client.post(self.url(route, pk), {}).status_code, 403)
        product.refresh_from_db()
        self.assertTrue(product.available)
        self.assertEqual(order.history.count(), 1)

    def test_private_pages_and_fragments_are_never_cacheable(self):
        for page in ['dashboard', 'menu', 'orders', 'restaurant', 'dashboard_fragment', 'orders_fragment']:
            response = self.client.get(self.url(page))
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response.headers.get('Cache-Control', ''))
        self.assertEqual(self.client.get(self.url('orders_fragment')).headers.get('X-STC-Fragment'), 'orders')

    def test_product_only_staff_cannot_read_order_metrics_or_other_modules(self):
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='shop', codename='view_product'))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url('menu')).status_code, 200)
        self.assertEqual(self.client.get(self.url('dashboard')).status_code, 200)
        for route in ['orders', 'orders_fragment', 'dashboard_fragment', 'restaurant']:
            self.assertEqual(self.client.get(self.url(route)).status_code, 403)

    def test_mutations_require_post_and_csrf(self):
        product = Product.objects.get(pk=6)
        order = self.order()
        closure = Closure.objects.create(restaurant_id=1, date='2030-02-01')
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)
        for route, pk in [('logout', None), ('product_availability', product.pk), ('order_status', order.pk), ('closure_add', None), ('closure_delete', closure.pk)]:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(self.url(route, pk)).status_code, 405)
                self.assertEqual(csrf_client.post(self.url(route, pk), {}).status_code, 403)
        product.refresh_from_db()
        self.assertTrue(product.available)
        self.assertTrue(Closure.objects.filter(pk=closure.pk).exists())
        for route, pk in [('product_add', None), ('product_edit', product.pk), ('restaurant', None), ('login', None)]:
            self.assertEqual(csrf_client.post(self.url(route, pk), {}).status_code, 403)

    def test_login_rejects_customer_and_external_return_url(self):
        self.client.logout()
        response = self.client.post(self.url('login'), {'username': self.customer.email, 'password': 'CRM-Test-9x!Strong'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post(self.url('login'), {'username': self.manager.email.upper(), 'password': 'CRM-Test-9x!Strong', 'next': 'https://outside.invalid/staff'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/crm/'))
        self.assertNotIn('outside.invalid', response.url)

    @override_settings(ADMIN_LOGIN_LIMIT=2, ADMIN_LOGIN_WINDOW=60)
    def test_login_attempts_are_limited(self):
        self.client.logout()
        for _ in range(2):
            self.assertEqual(self.client.post(self.url('login'), {'username': 'nobody@example.com', 'password': 'incorrect'}).status_code, 200)
        response = self.client.post(self.url('login'), {'username': 'nobody@example.com', 'password': 'incorrect'})
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response.headers)

    def test_logout_remains_available_after_management_permissions_are_removed(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url('menu')).status_code, 403)
        self.assertIn('_auth_user_id', self.client.session)
        response = self.client.post(self.url('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_create_and_edit_recipe_with_decimal_price_and_real_photo(self):
        data = self.product_data()
        data.update({'name': 'Plat CRM testé', 'category': str(Category.objects.get(name='Burgers').pk), 'price': '12,50', 'description': 'Une recette préparée sur place.', 'available': 'on', 'allergens_text': 'gluten, lait', 'photo': image_upload('../../ma-photo.php.png', trailer=b'STC_UNTRUSTED_TRAILER')})
        response = self.client.post(self.url('product_add'), data)
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name='Plat CRM testé')
        self.assertEqual(product.price, Decimal('12.50'))
        self.assertEqual(product.allergens, ['gluten', 'lait'])
        self.assertRegex(Path(product.photo.name).name, r'^[a-f0-9-]{32,36}\.jpg$')
        with product.photo.open('rb') as file:
            content = file.read()
        self.assertNotIn(b'STC_UNTRUSTED_TRAILER', content)
        self.assertEqual(Image.open(io.BytesIO(content)).format, 'JPEG')
        filename = product.photo.name
        data = self.product_data(product)
        data.update({'name': 'Plat CRM modifié', 'price': '13.40'})
        self.assertEqual(self.client.post(self.url('product_edit', product.pk), data).status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.name, 'Plat CRM modifié')
        self.assertEqual(product.price, Decimal('13.40'))
        self.assertEqual(product.photo.name, filename)
        public = APIClient().get('/api/products/').data
        self.assertEqual(next(row for row in public if row['id'] == product.pk)['price'], 13.4)

    def test_invalid_price_never_changes_saved_recipe(self):
        product = Product.objects.get(pk=6)
        original = product.price
        for value in ['-1', '12.345', 'not-a-price', '1000000']:
            with self.subTest(value=value):
                data = self.product_data(product)
                data.update({'name': 'Ne doit pas être enregistré', 'price': value})
                response = self.client.post(self.url('product_edit', product.pk), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                product.refresh_from_db()
                self.assertEqual(product.price, original)
                self.assertNotEqual(product.name, 'Ne doit pas être enregistré')

    def test_bad_or_excessive_photos_are_rejected(self):
        product = Product.objects.get(pk=6)
        uploads = [SimpleUploadedFile('faux.png', b'<svg onload="alert(1)"></svg>', content_type='image/png'), image_upload('anime.gif', image_format='GIF'), image_upload('trop-large.png', size=(6001, 1)), SimpleUploadedFile('trop-lourd.jpg', b'x' * (5 * 1024 * 1024 + 1), content_type='image/jpeg')]
        for upload in uploads:
            with self.subTest(name=upload.name):
                data = self.product_data(product)
                data['photo'] = upload
                response = self.client.post(self.url('product_edit', product.pk), data)
                self.assertEqual(response.status_code, 200)
                self.assertIn('photo', response.context['form'].errors)
                product.refresh_from_db()
                self.assertFalse(product.photo)

    def test_stale_product_form_cannot_overwrite_a_newer_change(self):
        product = Product.objects.get(pk=6)
        data = self.product_data(product)
        data['price'] = '1.00'
        Product.objects.filter(pk=product.pk).update(price=Decimal('9.25'))
        response = self.client.post(self.url('product_edit', product.pk), data)
        product.refresh_from_db()
        self.assertEqual(product.price, Decimal('9.25'))
        self.assertIn(response.status_code, [200, 409])

    def test_edit_preserves_existing_options_and_model_fields(self):
        product = Product.objects.get(pk=1)
        groups = list(product.option_groups.values_list('pk', flat=True))
        data = self.product_data(product)
        data['price'] = '12.25'
        self.assertEqual(self.client.post(self.url('product_edit', product.pk), data).status_code, 302)
        product.refresh_from_db()
        self.assertEqual(list(product.option_groups.values_list('pk', flat=True)), groups)
        self.assertEqual(product.price, Decimal('12.25'))
        self.assertFalse(product.promotional)

    def test_failed_edit_keeps_the_previous_photo_file(self):
        product = Product.objects.get(pk=6)
        product.photo.save('previous.png', image_upload())
        old_name = product.photo.name
        old_path = product.photo.path
        data = self.product_data(product)
        data.update({'price': '-1', 'photo': image_upload('new.png')})
        self.assertEqual(self.client.post(self.url('product_edit', product.pk), data).status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.photo.name, old_name)
        self.assertTrue(Path(old_path).is_file())

    def test_replacing_a_photo_persists_new_file_and_updates_public_catalog(self):
        product = Product.objects.get(pk=6)
        product.photo.save('previous.png', image_upload())
        old_name, old_path = product.photo.name, product.photo.path
        original_name, original_price = product.name, product.price
        data = self.product_data(product)
        data['photo'] = image_upload('replacement.png', size=(36, 22))

        response = self.client.post(self.url('product_edit', product.pk), data)
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertNotEqual(product.photo.name, old_name)
        self.assertRegex(Path(product.photo.name).name, r'^[a-f0-9-]{32,36}\.jpg$')
        with product.photo.open('rb') as file:
            image = Image.open(file)
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (36, 22))
            image.verify()
        self.assertTrue(Path(old_path).is_file(), 'Replacing a photo must not delete an existing file blindly.')
        self.assertEqual((product.name, product.price), (original_name, original_price))

        form_response = self.client.get(self.url('product_edit', product.pk))
        self.assertEqual(form_response.context['photo_url'], product.photo.url)
        public = APIClient().get('/api/products/').data
        image_url = next(row for row in public if row['id'] == product.pk)['image']
        self.assertTrue(image_url.endswith('/media/' + product.photo.name))
        self.assertNotIn(old_name, image_url)

    def test_availability_is_explicit_repeatable_and_public(self):
        product = Product.objects.get(pk=6)
        for _ in range(2):
            data = self.product_data(product)
            response = self.client.post(self.url('product_availability', product.pk), {'available': '0', 'revision': data['revision']})
            self.assertEqual(response.status_code, 302)
            product.refresh_from_db()
            self.assertFalse(product.available)
        public = APIClient().get('/api/products/').data
        self.assertFalse(next(row for row in public if row['id'] == product.pk)['available'])
        self.client.post(self.url('product_availability', product.pk), {'available': 'perhaps', 'revision': self.product_data(product)['revision']})
        product.refresh_from_db()
        self.assertFalse(product.available)

    def test_product_form_does_not_allow_technical_fields_or_html_execution(self):
        product = Product.objects.get(pk=6)
        data = self.product_data(product)
        data.update({'name': '<script>alert("crm")</script>', 'promotional': 'on', 'discount_percent': '100', 'is_staff': 'on'})
        self.assertEqual(self.client.post(self.url('product_edit', product.pk), data).status_code, 302)
        product.refresh_from_db()
        self.assertFalse(product.promotional)
        self.assertEqual(product.discount_percent, 0)
        response = self.client.get(self.url('menu'))
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert("crm")</script>')

    def test_multi_service_and_overnight_hours_are_persisted(self):
        periods = [{'weekday': 0, 'opens': '11:30', 'closes': '14:30'}, {'weekday': 0, 'opens': '18:30', 'closes': '23:00'}, {'weekday': 6, 'opens': '22:00', 'closes': '02:00'}]
        response = self.client.post(self.url('restaurant'), self.restaurant_data(periods))
        self.assertEqual(response.status_code, 302)
        restaurant = Restaurant.objects.get(pk=1)
        self.assertEqual(restaurant.opening_hours.count(), 3)
        self.assertTrue(restaurant.is_open(datetime(2026, 11, 2, 1, tzinfo=ZoneInfo('Europe/Paris'))))
        self.assertFalse(restaurant.is_open(datetime(2026, 11, 2, 15, tzinfo=ZoneInfo('Europe/Paris'))))

    def test_invalid_schedule_rolls_back_the_whole_restaurant_form(self):
        original = list(OpeningHour.objects.values_list('weekday', 'opens', 'closes'))
        address = Restaurant.objects.get(pk=1).address
        cases = [[{'weekday': 0, 'opens': '11:00', 'closes': '15:00'}, {'weekday': 0, 'opens': '14:00', 'closes': '17:00'}], [{'weekday': 0, 'opens': '12:00', 'closes': '12:00'}], [{'weekday': 7, 'opens': '12:00', 'closes': '14:00'}], [{'weekday': 6, 'opens': '22:00', 'closes': '02:00'}, {'weekday': 0, 'opens': '01:00', 'closes': '03:00'}]]
        for periods in cases:
            with self.subTest(periods=periods):
                data = self.restaurant_data(periods)
                data['address'] = 'Adresse à ne pas enregistrer'
                response = self.client.post(self.url('restaurant'), data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(list(OpeningHour.objects.values_list('weekday', 'opens', 'closes')), original)
                self.assertEqual(Restaurant.objects.get(pk=1).address, address)

    def test_adjacent_hours_are_allowed_but_missing_management_form_is_not(self):
        periods = [{'weekday': 0, 'opens': '11:00', 'closes': '14:00'}, {'weekday': 0, 'opens': '14:00', 'closes': '17:00'}]
        self.assertEqual(self.client.post(self.url('restaurant'), self.restaurant_data(periods)).status_code, 302)
        original = list(OpeningHour.objects.values_list('weekday', 'opens', 'closes'))
        data = self.restaurant_data()
        data.pop('hours-TOTAL_FORMS')
        self.assertEqual(self.client.post(self.url('restaurant'), data).status_code, 200)
        self.assertEqual(list(OpeningHour.objects.values_list('weekday', 'opens', 'closes')), original)

    def test_delivery_zone_and_negative_fee_are_validated(self):
        original = Restaurant.objects.get(pk=1).delivery_fee
        for changes in [{'delivery_fee': '-1'}, {'delivery_enabled': 'on', 'postal_codes_text': ''}, {'postal_codes_text': '123,ABCDE'}]:
            with self.subTest(changes=changes):
                data = self.restaurant_data()
                data.update(changes)
                self.assertEqual(self.client.post(self.url('restaurant'), data).status_code, 200)
                self.assertEqual(Restaurant.objects.get(pk=1).delivery_fee, original)

    def test_stale_settings_and_forged_hour_ids_cannot_overwrite_data(self):
        data = self.restaurant_data()
        data['address'] = 'Ancienne saisie'
        Restaurant.objects.filter(pk=1).update(address='Adresse enregistrée ailleurs')
        response = self.client.post(self.url('restaurant'), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Restaurant.objects.get(pk=1).address, 'Adresse enregistrée ailleurs')
        other = Restaurant.objects.create(pk=2, name='Autre périmètre', delivery_enabled=False)
        foreign_hour = OpeningHour.objects.create(restaurant=other, weekday=0, opens='09:00', closes='10:00')
        data = self.restaurant_data()
        data['hours-0-id'] = str(foreign_hour.pk)
        data['hours-0-opens'] = '01:00'
        self.assertEqual(self.client.post(self.url('restaurant'), data).status_code, 200)
        foreign_hour.refresh_from_db()
        self.assertEqual(foreign_hour.opens.strftime('%H:%M'), '09:00')

    def test_schedule_preserves_seconds_and_detects_subminute_overlap(self):
        OpeningHour.objects.all().delete()
        period = OpeningHour.objects.create(restaurant_id=1, weekday=0, opens='11:00:45', closes='12:00:45')
        response = self.client.get(self.url('restaurant'))
        self.assertContains(response, '11:00:45')
        data = self.restaurant_data()
        data['address'] = 'Une adresse mise à jour'
        self.assertEqual(self.client.post(self.url('restaurant'), data).status_code, 302)
        period.refresh_from_db()
        self.assertEqual(period.opens.strftime('%H:%M:%S'), '11:00:45')
        self.assertEqual(period.closes.strftime('%H:%M:%S'), '12:00:45')
        overlapping = [{'weekday': 0, 'opens': '11:00:45', 'closes': '12:00:45'}, {'weekday': 0, 'opens': '12:00:30', 'closes': '13:00:30'}]
        self.assertEqual(self.client.post(self.url('restaurant'), self.restaurant_data(overlapping)).status_code, 200)
        self.assertEqual(OpeningHour.objects.count(), 1)

    def test_overnight_closures_only_block_the_service_they_actually_close(self):
        restaurant = Restaurant.objects.get(pk=1)
        restaurant.opening_hours.all().delete()
        restaurant.closures.all().delete()
        OpeningHour.objects.create(restaurant=restaurant, weekday=6, opens='18:00', closes='02:00')
        OpeningHour.objects.create(restaurant=restaurant, weekday=0, opens='11:00', closes='14:00')
        OpeningHour.objects.create(restaurant=restaurant, weekday=0, opens='18:00', closes='02:00')
        sunday = Closure.objects.create(restaurant=restaurant, date='2026-11-01')

        def at(day, hour):
            return datetime(2026, 11, day, hour, tzinfo=ZoneInfo('Europe/Paris'))

        self.assertFalse(restaurant.is_open(at(1, 19)), 'Une fermeture du jour bloque son service du soir.')
        self.assertFalse(restaurant.is_open(at(2, 1)), 'La suite du service du dimanche fermé reste fermée.')
        self.assertTrue(restaurant.is_open(at(2, 12)), 'Le service normal du lundi reste indépendant du dimanche.')
        self.assertTrue(restaurant.is_open(at(2, 19)), 'Le nouveau service du lundi ne doit pas être bloqué par dimanche fermé.')
        self.assertTrue(restaurant.is_open(at(3, 1)), 'Le service du lundi ouvert continue le mardi matin.')
        monday = Closure.objects.create(restaurant=restaurant, date='2026-11-02')
        self.assertFalse(restaurant.is_open(at(2, 19)))
        self.assertFalse(restaurant.is_open(at(3, 1)), 'La suite d’un service du lundi fermé reste fermée.')
        monday.delete()
        Closure.objects.create(restaurant=restaurant, date='2026-11-03')
        self.assertTrue(restaurant.is_open(at(2, 19)))
        self.assertFalse(restaurant.is_open(at(3, 1)), 'Une fermeture du mardi coupe aussi une continuation de nuit.')
        sunday.delete()
        self.assertTrue(restaurant.is_open(at(9, 1)), 'La semaine suivante sans fermeture reste ouverte la nuit.')

    @override_settings(DEMO_MODE=False)
    def test_exceptional_closure_overrides_a_uniform_week_in_public_hours_summary(self):
        restaurant = Restaurant.objects.get(pk=1)
        restaurant.opening_hours.all().delete()
        restaurant.closures.all().delete()
        for day in range(7):
            OpeningHour.objects.create(restaurant=restaurant, weekday=day, opens='11:00', closes='23:00')
        Closure.objects.create(restaurant=restaurant, date='2026-11-02', reason='Fermeture prévue')
        fixed = datetime(2026, 11, 2, 12, tzinfo=ZoneInfo('Europe/Paris'))
        with patch('django.utils.timezone.now', return_value=fixed):
            response = APIClient().get('/api/restaurant/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['isOpen'])
        self.assertEqual(response.data['days'], 'Aujourd’hui')
        self.assertEqual(response.data['hours'], 'Fermé exceptionnellement')

    def test_manual_pause_is_persisted_and_blocks_real_order_creation(self):
        data = self.restaurant_data()
        data.pop('ordering_enabled', None)
        self.assertEqual(self.client.post(self.url('restaurant'), data).status_code, 302)
        self.assertFalse(Restaurant.objects.get(pk=1).ordering_enabled)
        api = APIClient(enforce_csrf_checks=True)
        self.assertFalse(api.get('/api/restaurant/').data['orderingEnabled'])
        api.get('/api/auth/csrf/')
        api.credentials(HTTP_X_CSRFTOKEN=api.cookies['csrftoken'].value)
        payload = {'mode': 'À emporter', 'items': [{'productId': 6, 'quantity': 1, 'choices': []}], 'customer': {'name': 'Camille Pause', 'email': 'pause@example.com', 'phone': '0612345678'}, 'paymentMethod': 'simulation'}
        self.assertEqual(api.post('/api/orders/', payload, format='json', HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex).status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_closure_creation_duplicate_and_deletion(self):
        data = {'date': '2030-03-05', 'reason': 'Travaux'}
        self.assertEqual(self.client.post(self.url('closure_add'), data).status_code, 302)
        closure = Closure.objects.get(restaurant_id=1, date=data['date'])
        response = self.client.post(self.url('closure_add'), data)
        self.assertIn(response.status_code, [200, 409])
        self.assertEqual(Closure.objects.filter(restaurant_id=1, date=data['date']).count(), 1)
        self.assertEqual(self.client.post(self.url('closure_delete', closure.pk)).status_code, 302)
        self.assertFalse(Closure.objects.filter(pk=closure.pk).exists())

    def test_order_transitions_keep_history_prices_and_customer_snapshot(self):
        order = self.order()
        for previous, target in [('confirmed', 'preparing'), ('preparing', 'ready'), ('ready', 'completed')]:
            self.assertEqual(self.client.post(self.url('order_status', order.pk), {'status': target, 'expected_status': previous}).status_code, 302)
            order.refresh_from_db()
            self.assertEqual(order.status, target)
        self.assertEqual(list(order.history.values_list('status', flat=True)), ['confirmed', 'preparing', 'ready', 'completed'])
        self.assertEqual(order.total, Decimal('5.00'))
        self.assertEqual(order.lines.get().name, 'Recette historique')
        self.assertEqual(order.customer['name'], 'Client privé')

    def test_illegal_stale_and_unpaid_order_actions_are_refused(self):
        order = self.order()
        for data in [{'status': 'completed', 'expected_status': 'confirmed'}, {'status': 'preparing', 'expected_status': 'ready'}]:
            self.client.post(self.url('order_status', order.pk), data)
            order.refresh_from_db()
            self.assertEqual(order.status, 'confirmed')
            self.assertEqual(order.history.count(), 1)
        unpaid = self.order(payment='pending')
        self.client.post(self.url('order_status', unpaid.pk), {'status': 'preparing', 'expected_status': 'confirmed'})
        unpaid.refresh_from_db()
        self.assertEqual(unpaid.status, 'confirmed')
        paid = self.order(payment='paid')
        self.client.post(self.url('order_status', paid.pk), {'status': 'cancelled', 'expected_status': 'confirmed'})
        paid.refresh_from_db()
        self.assertEqual(paid.status, 'confirmed')

    def test_duplicate_order_action_does_not_duplicate_history(self):
        order = self.order()
        data = {'status': 'preparing', 'expected_status': 'confirmed'}
        self.client.post(self.url('order_status', order.pk), data)
        self.client.post(self.url('order_status', order.pk), data)
        order.refresh_from_db()
        self.assertEqual(order.status, 'preparing')
        self.assertEqual(order.history.count(), 2)

    def test_order_post_cannot_change_totals_payment_or_customer(self):
        order = self.order()
        self.client.post(self.url('order_status', order.pk), {'status': 'preparing', 'expected_status': 'confirmed', 'total': '0.01', 'payment_status': 'paid', 'customer': '{}'})
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal('5.00'))
        self.assertEqual(order.payment_status, 'simulated')
        self.assertEqual(order.customer['name'], 'Client privé')

    def test_pending_payment_cancellation_requires_successful_checkout_release(self):
        order = self.order(status='pending_payment', payment='pending')
        data = {'status': 'cancelled', 'expected_status': 'pending_payment'}
        with patch('shop.crm_views.release_checkout', side_effect=ValidationError('Session de paiement encore ouverte.')) as release:
            self.assertEqual(self.client.post(self.url('order_status', order.pk), data).status_code, 409)
            release.assert_called_once()
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending_payment')
        self.assertEqual(order.history.count(), 1)
        with patch('shop.crm_views.release_checkout') as release:
            self.assertEqual(self.client.post(self.url('order_status', order.pk), data).status_code, 302)
            release.assert_called_once()
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(order.payment_status, 'cancelled')
        self.assertEqual(order.history.count(), 2)

    def test_public_order_access_requires_staff_permission_and_hides_guest_pii(self):
        order = self.order()
        api = APIClient()
        api.force_authenticate(self.staff)
        self.assertEqual(api.get(f'/api/orders/{order.pk}/').status_code, 404)
        api.force_authenticate(self.reader)
        response = api.get(f'/api/orders/{order.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['customer']['email'], 'prive@example.com')
        api.force_authenticate(None)
        response = api.get(f'/api/orders/{order.pk}/?token={order.access_token}')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('customer', response.data)

    def test_nonstaff_permission_and_inactive_staff_do_not_grant_order_access(self):
        order = self.order()
        permission = Permission.objects.get(content_type__app_label='shop', codename='view_order')
        self.customer.user_permissions.add(permission)
        api = APIClient()
        api.force_authenticate(self.customer)
        self.assertEqual(api.get(f'/api/orders/{order.pk}/').status_code, 404)
        self.reader.is_active = False
        self.reader.save(update_fields=['is_active'])
        api.force_authenticate(self.reader)
        self.assertEqual(api.get(f'/api/orders/{order.pk}/').status_code, 404)
        order.user = self.customer
        order.save(update_fields=['user'])
        api.force_authenticate(self.customer)
        self.assertEqual(api.get(f'/api/orders/{order.pk}/').status_code, 200)

    @override_settings(PAYMENT_MODE='stripe', STRIPE_SECRET_KEY='sk_test_crm_placeholder')
    def test_read_only_staff_cannot_initiate_another_customers_payment(self):
        order = self.order(status='pending_payment', payment='pending')
        api = APIClient(enforce_csrf_checks=True)
        api.get('/api/auth/csrf/')
        api.credentials(HTTP_X_CSRFTOKEN=api.cookies['csrftoken'].value)
        api.force_authenticate(self.reader)
        with patch('shop.payments.stripe.checkout.Session.create') as create:
            self.assertEqual(api.post(f'/api/orders/{order.pk}/payment/', {}, format='json').status_code, 404)
            create.assert_not_called()
