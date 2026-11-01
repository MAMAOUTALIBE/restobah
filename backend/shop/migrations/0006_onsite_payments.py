from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


def backfill_payment_method(apps, schema_editor):
    Order = apps.get_model('shop', 'Order')
    Payment = apps.get_model('shop', 'Payment')
    alias = schema_editor.connection.alias
    orders = Order.objects.using(alias)
    known = {'simulated', 'pending', 'paid', 'failed', 'cancelled', 'refunded'}
    if orders.exclude(payment_status__in=known).exists():
        raise RuntimeError('Migration interrompue : état financier historique inconnu. Aucune origine ne sera déduite.')
    if Payment.objects.using(alias).filter(order__payment_status='simulated').exists():
        raise RuntimeError('Migration interrompue : une commande simulée possède un paiement Stripe. Corrigez cette incohérence avant de reprendre.')
    orders.filter(payment_status='simulated').update(payment_method='simulation')
    orders.exclude(payment_status='simulated').update(payment_method='stripe')


class Migration(migrations.Migration):
    dependencies = [('shop', '0005_restaurant_delays_shared_cache'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='order', name='payment_method', field=models.CharField(choices=[('simulation','Simulation'),('stripe','Stripe test'),('on_site','Sur place')], editable=False, max_length=20, null=True)),
        migrations.RunPython(backfill_payment_method, migrations.RunPython.noop),
        # Retain a SQL default for INSERTs from the previous demonstration/simulation
        # image, which does not include this column. This does not make a legacy
        # Stripe or on-site application compatible with the new payment contract.
        migrations.AlterField(model_name='order', name='payment_method', field=models.CharField(choices=[('simulation','Simulation'),('stripe','Stripe test'),('on_site','Sur place')], default='simulation', db_default='simulation', editable=False, max_length=20)),
        migrations.AlterField(model_name='order', name='payment_status', field=models.CharField(choices=[('simulated','Simulé'),('pending','En attente'),('due','À régler sur place'),('paid','Payé'),('failed','Échoué'),('cancelled','Annulé'),('refunded','Remboursé')], default='simulated', max_length=20)),
        migrations.AlterModelOptions(name='order', options={'ordering':['-date'], 'permissions':[('record_onsite_payment','Peut enregistrer les règlements et remboursements sur place')]}),
        migrations.CreateModel(name='OnSitePaymentEvent', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('kind', models.CharField(choices=[('collected','Encaissement enregistré'),('refunded','Remboursement enregistré')], max_length=20)),
            ('amount', models.DecimalField(decimal_places=2, max_digits=9, validators=[django.core.validators.MinValueValidator(0)])),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='onsite_payment_events', to=settings.AUTH_USER_MODEL)),
            ('order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='onsite_events', to='shop.order')),
        ], options={'ordering':['created_at','id'], 'constraints':[
            models.UniqueConstraint(fields=('order','kind'), name='unique_onsite_payment_kind'),
            models.CheckConstraint(condition=models.Q(('amount__gte',0)), name='onsite_payment_nonnegative'),
        ]}),
    ]
