"""Record staff declarations of physical payments. Never debit a payment instrument."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import OnSitePaymentEvent, Order, OrderHistory

PAYMENT_PERMISSIONS = ('shop.view_order', 'shop.change_order', 'shop.record_onsite_payment')
ACTIVE_STATUSES = {'confirmed', 'preparing', 'ready'}


def record_payment(order_id, actor, kind, *, expected_status, expected_payment_status):
    """Lock before deciding; identical retries are harmless, stale/conflicting actions fail."""
    if not actor.is_active or not actor.is_staff or not actor.has_perms(PAYMENT_PERMISSIONS):
        raise PermissionDenied('Vous ne pouvez pas enregistrer les règlements sur place.')
    if kind not in {'collected', 'refunded'}:
        raise ValidationError('Opération de règlement inconnue.')
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.payment_method != 'on_site':
            raise ValidationError('Cette commande ne prévoit pas de règlement sur place.')
        events = {event.kind: event for event in order.onsite_events.all()}
        if any(event.amount != order.total for event in events.values()):
            raise ValidationError('Le registre de règlement est incohérent. Contactez le responsable.')
        if ('refunded' in events and ('collected' not in events or order.payment_status != 'refunded')) or \
                ('collected' in events and order.payment_status not in {'paid', 'refunded'}):
            raise ValidationError('Le registre de règlement est incohérent. Contactez le responsable.')
        target = 'paid' if kind == 'collected' else 'refunded'
        if kind in events and order.payment_status == target:
            return order, False
        if order.status != expected_status or order.payment_status != expected_payment_status:
            raise ValidationError('Cette commande a déjà été mise à jour. Vérifiez son nouvel état avant de recommencer.')
        if kind == 'collected':
            if order.status not in ACTIVE_STATUSES or order.payment_status != 'due' or events:
                raise ValidationError('L’encaissement ne peut pas être enregistré dans cet état.')
        elif order.payment_status != 'paid' or 'collected' not in events or 'refunded' in events:
            raise ValidationError('Un encaissement sur place doit avoir été enregistré avant le remboursement.')
        OnSitePaymentEvent.objects.create(order=order, kind=kind, amount=order.total, actor=actor)
        order.payment_status = target
        if kind == 'refunded' and order.status not in {'completed', 'cancelled'}:
            order.status = 'cancelled'
            OrderHistory.objects.create(order=order, status='cancelled')
        order.save(update_fields=['payment_status', 'status'])
        return order, True
