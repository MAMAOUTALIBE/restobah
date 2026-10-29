import hashlib
import hmac
import json
import time
from decimal import Decimal
from django.conf import settings
from django.db import transaction, IntegrityError, OperationalError, connection
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError, NotFound
from .models import Restaurant, Category, Product, OptionGroup, Choice, Order, OrderLine, OrderHistory
from .notifications import order_confirmed

WEEKDAYS = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche']


def restaurant_instance():
    return Restaurant.objects.prefetch_related('opening_hours','closures').get_or_create(pk=1)[0]

def period_text(periods):
    return ' · '.join(f'{p.opens:%Hh%M} – {p.closes:%Hh%M}' for p in periods) or 'Fermé'

def hours_summary(restaurant, periods):
    """Footer summary: one line when every day shares the same hours, otherwise today's hours."""
    by_day = [[(p.opens,p.closes) for p in periods if p.weekday == day] for day in range(7)]
    if by_day[0] and all(day == by_day[0] for day in by_day):
        return 'Tous les jours', period_text([p for p in periods if p.weekday == 0])
    today = timezone.localdate()
    if restaurant.closures.filter(date=today).exists():
        return 'Aujourd’hui', 'Fermé exceptionnellement'
    return f'Aujourd’hui ({WEEKDAYS[today.weekday()].lower()})', period_text([p for p in periods if p.weekday == today.weekday()])

def restaurant_data():
    restaurant = restaurant_instance()
    periods = list(restaurant.opening_hours.all())
    days, hours = hours_summary(restaurant, periods)
    return {'name':restaurant.name,'address':restaurant.address,'city':restaurant.city,'hours':hours,'days':days,'deliveryFee':float(restaurant.delivery_fee),'minDeliveryTotal':float(restaurant.min_delivery_total),'deliveryPostalCodes':restaurant.delivery_postal_codes,'orderingEnabled':restaurant.ordering_enabled,'isOpen':bool(settings.DEMO_MODE or restaurant.is_open()),'demoMode':settings.DEMO_MODE,'paymentMode':settings.PAYMENT_MODE,'openingHours':[{'weekday':p.weekday,'opens':p.opens.strftime('%H:%M'),'closes':p.closes.strftime('%H:%M')} for p in periods],'pickupEnabled':restaurant.pickup_enabled,'deliveryEnabled':restaurant.delivery_enabled and bool(restaurant.delivery_postal_codes),'pickupDelay':restaurant.pickup_delay,'deliveryDelay':restaurant.delivery_delay}

def categories_data():
    return [{'name':c.name,'position':c.position} for c in Category.objects.all()]

def product_data(product, request=None):
    image = request.build_absolute_uri(product.photo.url) if product.photo and request else product.photo.url if product.photo else product.image
    groups = [{'id':g.id,'name':g.name,'min':g.minimum,'max':g.maximum,'choices':[{'id':c.id,'name':c.name,'price':float(c.price)} for c in g.choices.all() if c.available]} for g in product.option_groups.all()]
    # A required option without enough available choices makes the product impossible to order.
    orderable = product.is_available() and all(len(g['choices']) >= g['min'] for g in groups)
    regular = product.promotion_source.price if product.promotion_source_id else product.price
    return {'id':product.id,'name':product.name,'category':product.category.name,'description':product.description,'summary':product.summary,'price':float(product.current_price()),'regularPrice':float(regular),'discountPercent':product.discount_percent,'image':image,'badge':product.badge,'rating':product.rating,'vegetarian':product.vegetarian,'available':orderable,'allergens':product.allergens if isinstance(product.allergens,list) else [],'promotional':product.promotional,'options':any(g['min'] for g in groups),'optionGroups':groups}

def order_data(order, include_token=False, include_customer=False):
    lines = list(order.lines.all())
    result = {'id':order.id,'date':order.date.isoformat(),'subtotal':float(order.subtotal),'deliveryFee':float(order.delivery_fee),'total':float(order.total),'mode':order.mode,'status':order.status,'paymentStatus':order.payment_status,'demoMode':order.demo_mode,'items':[f'{line.quantity} × {line.name}' for line in lines],'lines':[{'name':line.name,'quantity':line.quantity,'unitPrice':float(line.unit_price),'total':float(line.total),'choices':line.choices} for line in lines],'history':[{'status':h.status,'date':h.date.isoformat()} for h in order.history.all()]}
    if include_token:
        result['accessToken'] = order.access_token
    if include_customer:
        result['customer'] = order.customer
    return result

def authorized_order(request,pk,token=None,lock=False):
    qs = Order.objects.select_for_update() if lock else Order.objects
    try:
        order = qs.get(pk=pk)
    except Order.DoesNotExist:
        raise NotFound('Commande introuvable.')
    provided = token or request.query_params.get('token','')
    owner = request.user.is_authenticated and (request.user.is_staff or order.user_id == request.user.id)
    guest = isinstance(provided,str) and bool(provided) and hmac.compare_digest(provided.encode('utf-8'),order.access_token.encode('utf-8'))
    if not owner and not guest:
        raise NotFound('Commande introuvable.')
    return order

def order_scope(request):
    if request.user.is_authenticated:
        return f'user:{request.user.id}'
    if not request.session.session_key or not request.session.exists(request.session.session_key):
        from rest_framework.exceptions import APIException
        error = APIException('Votre session a expiré. Actualisez la page avant de valider la commande.')
        error.status_code = 409
        raise error
    return 'guest:' + hashlib.sha256(request.session.session_key.encode()).hexdigest()

def create_order(request,data,key):
    # SQLite is the local-development backend. Retry its transient writer contention
    # outside atomic blocks; the stable session/key still guarantees one order.
    for attempt in range(6):
        try:
            return _create_order(request,data,key)
        except OperationalError as error:
            if connection.vendor != 'sqlite' or 'locked' not in str(error).lower() or attempt == 5:
                raise
            time.sleep(0.025 * (2 ** attempt))

def _create_order(request,data,key):
    if not key or len(key) > 100 or not all(c.isalnum() or c in '-_' for c in key):
        raise ValidationError('Une clé d’idempotence valide est obligatoire.')
    scope = order_scope(request)
    payload_hash = hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    existing = Order.objects.filter(scope=scope,idempotency_key=key).first()
    if existing:
        if not hmac.compare_digest(existing.payload_hash,payload_hash):
            from rest_framework.exceptions import APIException
            error = APIException('Cette clé correspond déjà à une autre commande.')
            error.status_code = 409
            raise error
        return existing, False
    restaurant = restaurant_instance()
    if not restaurant.ordering_enabled or (not settings.DEMO_MODE and not restaurant.is_open()):
        raise ValidationError('Le restaurant n’accepte pas de commandes actuellement.')
    # Without a configured zone, delivery is closed rather than accepted everywhere.
    if (data['mode'] == 'Livraison' and (not restaurant.delivery_enabled or not restaurant.delivery_postal_codes)) or (data['mode'] == 'À emporter' and not restaurant.pickup_enabled):
        raise ValidationError('Ce mode de commande n’est pas disponible.')
    if data['paymentMethod'] != settings.PAYMENT_MODE:
        raise ValidationError('Le mode de paiement a changé. Actualisez votre panier.')
    if data['mode'] == 'Livraison' and data['customer']['postal'] not in restaurant.delivery_postal_codes:
        raise ValidationError('Cette adresse est en dehors de notre zone de livraison.')
    try:
        with transaction.atomic():
            # Lock selected products and promotion sources in a consistent order.
            ids = {i['productId'] for i in data['items']}
            source_ids = Product.objects.filter(pk__in=ids).values('promotion_source_id')
            locked = {p.id:p for p in Product.objects.select_for_update(of=('self',)).filter(Q(pk__in=ids)|Q(pk__in=source_ids)).order_by('id').prefetch_related('option_groups')}
            products = {pk:p for pk,p in locked.items() if pk in ids}
            for product in products.values():
                if product.promotion_source_id:
                    if product.promotion_source_id not in locked:
                        raise ValidationError('Le catalogue a changé. Actualisez le panier et réessayez.')
                    product.promotion_source = locked[product.promotion_source_id]
            group_ids = {g.id for p in products.values() for g in p.option_groups.all()}
            locked_groups = {g.id:g for g in OptionGroup.objects.select_for_update().filter(pk__in=group_ids).order_by('id')}
            locked_choices = list(Choice.objects.select_for_update().filter(group_id__in=group_ids).order_by('id'))
            lines = []
            subtotal = Decimal('0.00')
            for item in data['items']:
                product = products.get(item['productId'])
                if not product or not product.is_available():
                    raise ValidationError('Un produit n’est plus disponible. Actualisez votre panier.')
                groups = [locked_groups[g.id] for g in product.option_groups.all() if g.id in locked_groups]
                product_group_ids = {g.id for g in groups}
                allowed_choices = {c.id:c for c in locked_choices if c.group_id in product_group_ids and c.available}
                if any(c not in allowed_choices for c in item['choices']):
                    raise ValidationError(f'Une option de « {product.name} » n’est plus disponible.')
                for group in groups:
                    count = sum(1 for c in item['choices'] if allowed_choices[c].group_id == group.id)
                    if not group.minimum <= count <= group.maximum:
                        raise ValidationError(f'Choisissez entre {group.minimum} et {group.maximum} option(s) pour « {group.name} » de « {product.name} ».')
                unit = product.current_price()+sum((allowed_choices[c].price for c in item['choices']),Decimal(0))
                total = unit*item['quantity']
                subtotal += total
                lines.append({'product':product,'name':product.name,'quantity':item['quantity'],'unit_price':unit,'total':total,'choices':[allowed_choices[c].name for c in item['choices']]})
            if subtotal > Decimal('10000'):
                raise ValidationError('Le montant dépasse la limite de commande en ligne.')
            if data['mode'] == 'Livraison' and subtotal < restaurant.min_delivery_total:
                raise ValidationError(f'Le minimum de livraison est de {restaurant.min_delivery_total} €.')
            delivery_fee = restaurant.delivery_fee if data['mode'] == 'Livraison' else Decimal('0.00')
            simulated = data['paymentMethod'] == 'simulation'
            order = Order.objects.create(user=request.user if request.user.is_authenticated else None,scope=scope,idempotency_key=key,payload_hash=payload_hash,mode=data['mode'],status='confirmed' if simulated else 'pending_payment',payment_status='simulated' if simulated else 'pending',demo_mode=settings.DEMO_MODE,subtotal=subtotal,delivery_fee=delivery_fee,total=subtotal+delivery_fee,customer=data['customer'])
            OrderLine.objects.bulk_create([OrderLine(order=order,**line) for line in lines])
            OrderHistory.objects.create(order=order,status=order.status)
            if simulated:
                # Stripe orders are confirmed, and e-mailed, by the verified webhook.
                transaction.on_commit(lambda: order_confirmed(order.id))
            return order, True
    except IntegrityError:
        existing = Order.objects.filter(scope=scope,idempotency_key=key).first()
        if existing and hmac.compare_digest(existing.payload_hash,payload_hash):
            return existing, False
        raise ValidationError('La commande a été modifiée. Vérifiez votre panier et réessayez.')
