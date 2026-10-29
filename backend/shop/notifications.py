import logging
from django.conf import settings
from django.core.mail import send_mail
from .models import Order, Restaurant

logger = logging.getLogger('shop.notifications')

def euro(value):
    return f'{value:.2f}'.replace('.', ',') + ' €'

def tracking_url(order):
    return f'{settings.FRONTEND_URL}/?order_id={order.id}&token={order.access_token}'

def order_summary(order):
    rows = []
    for line in order.lines.all():
        detail = f' ({", ".join(line.choices)})' if line.choices else ''
        rows.append(f'- {line.quantity} × {line.name}{detail} : {euro(line.total)}')
    if order.delivery_fee:
        rows.append(f'- Livraison : {euro(order.delivery_fee)}')
    rows.append(f'Total TTC : {euro(order.total)}')
    return '\n'.join(rows)

def send(subject, body, recipients):
    """Never let an e-mail failure undo or block an order; the failure is logged for the team."""
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
        return True
    except Exception:
        logger.exception('Échec de l’envoi de l’e-mail « %s ».', subject)
        return False

def order_confirmed(order_id):
    """Customer confirmation and restaurant alert, sent once the order is confirmed (created or paid)."""
    order = Order.objects.prefetch_related('lines').get(pk=order_id)
    restaurant = Restaurant.objects.filter(pk=1).first()
    name = restaurant.name if restaurant else 'STC'
    customer = order.customer
    if order.mode == 'Livraison':
        where = f"Livraison à : {customer.get('address','')}, {customer.get('postal','')} {customer.get('city','')}"
    else:
        where = f'Retrait au restaurant : {restaurant.address}, {restaurant.city}' if restaurant else 'Retrait au restaurant'
    payment = 'Paiement simulé : aucun prélèvement.' if order.payment_status == 'simulated' else 'Paiement confirmé par carte (Stripe, mode test).'
    demo = 'Commande de démonstration : aucun repas ne sera préparé.\n\n' if order.demo_mode else ''
    send(f'{name} — Commande {order.id} confirmée',
         f"Bonjour {customer.get('name','')},\n\nNous avons bien reçu votre commande {order.id}.\n\n{demo}{order_summary(order)}\n\n{where}\n{payment}\n\n"
         f"Suivre votre commande : {tracking_url(order)}\nCe lien est personnel : ne le partagez pas.\n\n{name}",
         [customer['email']])
    if settings.ORDER_NOTIFICATION_EMAILS:
        note = customer.get('note') or '—'
        send(f'Nouvelle commande {order.id} · {order.mode} · {euro(order.total)}',
             f"{demo}Client : {customer.get('name','')}\nTéléphone : {customer.get('phone','')}\nE-mail : {customer.get('email','')}\n{where}\nPrécision : {note}\n\n"
             f"{order_summary(order)}\n{payment}\n\nAdministration : {settings.FRONTEND_URL}/admin/shop/order/{order.id}/change/",
             settings.ORDER_NOTIFICATION_EMAILS)
