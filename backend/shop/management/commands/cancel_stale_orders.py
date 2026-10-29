from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from shop.models import Order
from shop.payments import release_checkout

class Command(BaseCommand):
    help='Annule les commandes Stripe restées sans paiement, après fermeture de leur session. À planifier (cron) en production.'
    def add_arguments(self,parser):
        parser.add_argument('--minutes',type=int,default=settings.PENDING_PAYMENT_MINUTES)
    def handle(self,*args,**options):
        limit=timezone.now()-timedelta(minutes=options['minutes'])
        cancelled=kept=0
        for pk in Order.objects.filter(status='pending_payment',date__lt=limit).values_list('pk',flat=True):
            with transaction.atomic():
                order=Order.objects.select_for_update().get(pk=pk)
                if order.status!='pending_payment':
                    continue
                try:
                    release_checkout(order)
                    order.transition('cancelled')
                    cancelled+=1
                except ValidationError as error:
                    kept+=1
                    self.stderr.write(f'{order.id} conservée : {" ".join(error.messages)}')
        self.stdout.write(f'{cancelled} commande(s) impayée(s) annulée(s), {kept} conservée(s).')
