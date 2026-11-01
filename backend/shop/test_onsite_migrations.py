"""Exercise 0005 -> 0006 on the disposable test database, without a demo seed."""
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class OnSiteMigrationTests(TransactionTestCase):
    migrate_from = [('shop', '0005_restaurant_delays_shared_cache')]
    migrate_to = [('shop', '0006_onsite_payments')]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.apps = executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        # Return to the latest schema even when deliberately testing a refused backfill.
        Order = self.apps.get_model('shop', 'Order')
        Payment = self.apps.get_model('shop', 'Payment')
        Payment.objects.filter(order__payment_status='simulated').delete()
        Order.objects.exclude(payment_status__in=['simulated','pending','paid','failed','cancelled','refunded']).update(payment_status='failed')
        MigrationExecutor(connection).migrate(self.migrate_to)
        super().tearDown()

    def old_order(self, index, status, payment):
        return self.apps.get_model('shop', 'Order').objects.create(
            id=f'STC-OLD-{index}', scope='old', idempotency_key=f'old-{index}', payload_hash='a'*64,
            access_token=f'private-old-{index}', mode='À emporter', status=status, payment_status=payment,
            demo_mode=True, subtotal=Decimal('12.30'), delivery_fee=Decimal('0.00'), total=Decimal('12.30'),
            customer={'name':'Ancien client','email':'old@example.com','note':'Texte intact'})

    @staticmethod
    def snapshot(apps, names, fields=None):
        result={}
        field_names={}
        for name in names:
            model=apps.get_model('shop',name)
            selected=fields[name] if fields else [field.attname for field in model._meta.concrete_fields]
            field_names[name]=selected
            result[name]=list(model.objects.order_by('pk').values(*selected))
        return result,field_names

    def test_backfill_preserves_every_historical_field_and_creates_no_events(self):
        for index,(status,payment) in enumerate([('confirmed','simulated'),('cancelled','simulated'),
                ('pending_payment','pending'),('confirmed','paid'),('pending_payment','failed'),
                ('cancelled','cancelled'),('completed','refunded')]):
            order=self.old_order(index,status,payment)
            self.apps.get_model('shop','OrderLine').objects.create(order_id=order.pk,name='Ancienne recette',quantity=2,
                unit_price=Decimal('6.15'),total=Decimal('12.30'),choices=['Ancienne option'])
            self.apps.get_model('shop','OrderHistory').objects.create(order_id=order.pk,status=status)
            if payment!='simulated':
                self.apps.get_model('shop','Payment').objects.create(order_id=order.pk,session_id=f'cs_old_{index}',payment_intent=f'pi_old_{index}')
        names=['Order','OrderLine','OrderHistory','Payment','User','Restaurant','Product']
        before,fields=self.snapshot(self.apps,names)
        executor=MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps=executor.loader.project_state(self.migrate_to).apps
        after,_=self.snapshot(apps,names,fields)
        self.assertEqual(before,after)
        for order in apps.get_model('shop','Order').objects.all():
            self.assertEqual(order.payment_method,'simulation' if order.payment_status=='simulated' else 'stripe')
        self.assertFalse(apps.get_model('shop','OnSitePaymentEvent').objects.exists())
        # Auto-increment sequence remains usable after migration on PostgreSQL as well as SQLite.
        first=apps.get_model('shop','User').objects.create(email='migration-actor@example.com',password='!')
        on_site=apps.get_model('shop','Order').objects.create(scope='new',idempotency_key='new',payload_hash='b'*64,
            mode='À emporter',payment_method='on_site',payment_status='due',subtotal=0,total=0,customer={})
        event=apps.get_model('shop','OnSitePaymentEvent').objects.create(order=on_site,actor=first,kind='collected',amount=0)
        self.assertGreater(event.pk,0)

    def test_unknown_historical_financial_status_stops_before_backfill(self):
        self.old_order(1,'confirmed','unknown')
        with self.assertRaisesMessage(RuntimeError,'état financier historique inconnu'):
            MigrationExecutor(connection).migrate(self.migrate_to)

    def test_legacy_simulation_insert_after_migration_uses_durable_sql_default(self):
        executor=MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps=executor.loader.project_state(self.migrate_to).apps
        OldOrder=self.apps.get_model('shop','Order')
        self.assertNotIn('payment_method',[field.name for field in OldOrder._meta.fields])
        # Execute the actual legacy INSERT: no payment_method column is supplied.
        legacy=self.old_order(999,'confirmed','simulated')
        current=apps.get_model('shop','Order').objects.get(pk=legacy.pk)
        self.assertEqual((current.payment_method,current.payment_status,current.status,current.demo_mode),
                         ('simulation','simulated','confirmed',True))
        fields=[field.attname for field in OldOrder._meta.concrete_fields]
        self.assertEqual(OldOrder.objects.filter(pk=legacy.pk).values(*fields).get(),
                         apps.get_model('shop','Order').objects.filter(pk=legacy.pk).values(*fields).get())
        self.assertFalse(apps.get_model('shop','OnSitePaymentEvent').objects.exists())

    def test_simulated_order_with_stripe_relation_stops_before_backfill(self):
        order=self.old_order(1,'confirmed','simulated')
        self.apps.get_model('shop','Payment').objects.create(order_id=order.pk,session_id='cs_contradiction')
        with self.assertRaisesMessage(RuntimeError,'commande simulée possède un paiement Stripe'):
            MigrationExecutor(connection).migrate(self.migrate_to)
