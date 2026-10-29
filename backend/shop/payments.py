import logging
import time
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
import stripe
from .models import Payment, Order, OrderHistory, StripeEvent
from .notifications import order_confirmed
from .services import authorized_order
from .views import ProtectedView

logger = logging.getLogger('shop.payments')
SESSION_EVENTS = {'checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.expired','checkout.session.async_payment_failed'}
PAID_EVENTS = {'checkout.session.completed','checkout.session.async_payment_succeeded'}
# Retries inside the same window reuse one Stripe idempotency key, hence identical parameters.
CHECKOUT_WINDOW = 600
# Stripe accepts 30 minutes to 24 hours; a short lifetime frees unpaid orders quickly.
CHECKOUT_LIFETIME = 1800 + 60

def cents(amount):
    return int(amount*100)

def checkout_expiry(now=None):
    bucket = int(now if now is not None else time.time()) // CHECKOUT_WINDOW
    return bucket, (bucket+1)*CHECKOUT_WINDOW + CHECKOUT_LIFETIME

def release_checkout(order):
    """Close the order's Stripe session so that it can no longer be paid, before a cancellation."""
    payment = Payment.objects.filter(order=order).exclude(session_id__isnull=True).exclude(session_id='').first()
    if not payment:
        return
    if not settings.STRIPE_SECRET_KEY:
        raise ModelValidationError('La clé Stripe de test est nécessaire pour fermer la session de paiement avant l’annulation.')
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.retrieve(payment.session_id)
        if session.get('status') == 'open':
            try:
                session = stripe.checkout.Session.expire(payment.session_id)
            except stripe.InvalidRequestError:
                # The customer may have completed the payment in the meantime.
                session = stripe.checkout.Session.retrieve(payment.session_id)
    except stripe.StripeError:
        logger.exception('Session Stripe %s impossible à fermer pour %s.', payment.session_id, order.id)
        raise ModelValidationError('Stripe est injoignable : la session de paiement n’a pas pu être fermée. Réessayez avant d’annuler.')
    if session.get('status') != 'expired':
        raise ModelValidationError('Le client a peut-être déjà payé : attendez la confirmation du paiement, puis remboursez-le dans Stripe avant d’annuler.')

class PaymentView(ProtectedView):
    def post(self,request,pk):
        if settings.PAYMENT_MODE != 'stripe' or not settings.STRIPE_SECRET_KEY:
            return Response({'detail':'Le paiement Stripe de test n’est pas configuré.'},status=503)
        token = request.data.get('token','') if isinstance(request.data,dict) else ''
        with transaction.atomic():
            order = authorized_order(request,pk,token=token,lock=True)
            if order.status != 'pending_payment' or order.payment_status not in {'pending','failed'}:
                raise ValidationError('Cette commande ne peut pas être payée dans son état actuel.')
            payment,_ = Payment.objects.get_or_create(order=order)
            stripe.api_key = settings.STRIPE_SECRET_KEY
            try:
                if payment.session_id:
                    existing = stripe.checkout.Session.retrieve(payment.session_id)
                    if existing.get('status') == 'open' and existing.get('url'):
                        return Response({'url':existing['url']})
                    if existing.get('status') == 'expired':
                        order.transition('cancelled')
                        return Response({'detail':'La session de paiement a expiré. Cette commande est annulée ; vous pouvez en créer une nouvelle.'},status=409)
                    return Response({'detail':'Le paiement est en cours de confirmation. Consultez le suivi de votre commande.'},status=409)
                if order.date < timezone.now()-timedelta(minutes=settings.PENDING_PAYMENT_MINUTES):
                    order.transition('cancelled')
                    return Response({'detail':'Cette commande a expiré avant son paiement. Votre panier est conservé : validez une nouvelle commande.'},status=409)
                bucket,expires_at = checkout_expiry()
                checkout = stripe.checkout.Session.create(mode='payment',payment_method_types=['card'],line_items=[{'price_data':{'currency':'eur','product_data':{'name':f'Commande STC {order.id}'},'unit_amount':cents(order.total)},'quantity':1}],client_reference_id=order.id,metadata={'order_id':order.id},payment_intent_data={'metadata':{'order_id':order.id}},expires_at=expires_at,success_url=f'{settings.FRONTEND_URL}/?order={order.id}&payment=return',cancel_url=f'{settings.FRONTEND_URL}/?order={order.id}&payment=cancelled',idempotency_key=f'stc-checkout-{order.id}-{bucket}')
                payment.session_id = checkout['id']
                payment.checkout_url = checkout['url']
                payment.save(update_fields=['session_id','checkout_url'])
                return Response({'url':checkout['url']})
            except stripe.StripeError:
                logger.exception('Création ou reprise de la session Stripe impossible pour %s.', order.id)
                return Response({'detail':'Le service de paiement de test est momentanément indisponible. Votre commande reste en attente.'},status=502)

def handle_session(event_type,obj):
    order_id = (obj.get('metadata') or {}).get('order_id')
    order = Order.objects.select_for_update().filter(pk=order_id).first() if order_id else None
    payment = Payment.objects.select_for_update().filter(order_id=order_id,session_id=obj.get('id')).first() if order else None
    if not order or not payment:
        logger.warning('Événement Stripe %s ignoré : session %s inconnue.',event_type,obj.get('id'))
        return
    if event_type in PAID_EVENTS and obj.get('payment_status') == 'paid':
        if obj.get('amount_total') != cents(order.total) or obj.get('currency') != 'eur':
            logger.error('Paiement Stripe %s non appliqué à %s : montant ou devise inattendu (%s %s).',obj.get('id'),order.id,obj.get('amount_total'),obj.get('currency'))
            return
        if order.payment_status in {'paid','refunded'}:
            return
        payment.payment_intent = obj.get('payment_intent') or ''
        payment.save(update_fields=['payment_intent'])
        order.payment_status = 'paid'
        if order.status == 'pending_payment':
            order.status = 'confirmed'
            order.save(update_fields=['payment_status','status'])
            OrderHistory.objects.create(order=order,status='confirmed')
            transaction.on_commit(lambda: order_confirmed(order.id))
        else:
            # Paid while being cancelled: the money is recorded and flagged for refund.
            order.save(update_fields=['payment_status'])
            logger.error('Paiement Stripe reçu pour la commande annulée %s : remboursement à effectuer.',order.id)
        return
    if order.status != 'pending_payment' or order.payment_status not in {'pending','failed'}:
        return
    if event_type == 'checkout.session.expired':
        order.transition('cancelled')
    elif event_type == 'checkout.session.async_payment_failed':
        order.payment_status = 'failed'
        order.save(update_fields=['payment_status'])

def handle_refund(obj):
    intent_id = obj.get('payment_intent')
    payment = Payment.objects.filter(payment_intent=intent_id).first() if intent_id else None
    # Stripe copies payment_intent_data.metadata to its Charge. This permits
    # refund reconciliation even when the checkout-completed event is delayed.
    order_id = payment.order_id if payment else (obj.get('metadata') or {}).get('order_id')
    order = Order.objects.select_for_update().filter(pk=order_id).first() if order_id else None
    payment = Payment.objects.select_for_update().filter(order=order).first() if order else None
    if not (order and payment and intent_id and (not payment.payment_intent or payment.payment_intent == intent_id)):
        logger.warning('Remboursement Stripe %s ignoré : paiement inconnu.',intent_id)
        return
    if order.payment_status not in {'pending','failed','paid','cancelled'} or obj.get('amount_refunded') != cents(order.total) or obj.get('currency') != 'eur':
        return
    payment.payment_intent = intent_id
    payment.save(update_fields=['payment_intent'])
    order.payment_status = 'refunded'
    if order.status not in {'completed','cancelled'}:
        order.status = 'cancelled'
        OrderHistory.objects.create(order=order,status='cancelled')
    order.save(update_fields=['payment_status','status'])

@csrf_exempt
def stripe_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'detail':'Méthode non autorisée.'},status=405)
    if not settings.STRIPE_WEBHOOK_SECRET:
        return JsonResponse({'detail':'Le webhook de paiement n’est pas configuré.'},status=503)
    try:
        event = stripe.Webhook.construct_event(request.body,request.headers.get('Stripe-Signature',''),settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError,stripe.SignatureVerificationError):
        return JsonResponse({'detail':'Signature de paiement invalide.'},status=400)
    if event.get('livemode'):
        return JsonResponse({'detail':'Les paiements réels ne sont pas activés.'},status=400)
    event_type = event['type']
    obj = event['data']['object']
    with transaction.atomic():
        _,created = StripeEvent.objects.get_or_create(id=event['id'],defaults={'event_type':event_type})
        if not created:
            return JsonResponse({'received':True})
        if event_type in SESSION_EVENTS:
            handle_session(event_type,obj)
        elif event_type == 'charge.refunded' and obj.get('refunded'):
            handle_refund(obj)
    return JsonResponse({'received':True})
