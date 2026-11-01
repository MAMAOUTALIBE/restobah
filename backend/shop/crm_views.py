"""Restaurant manager pages. Every mutation is checked and persisted server-side."""
from decimal import Decimal
from functools import wraps
from urllib.parse import quote, urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max, Q, Sum, Value
from django.db.models.functions import Replace
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .crm_forms import (
    AvailabilityForm, ClosureForm, OpeningFormSet, OrderStatusForm, OnSitePaymentForm, ProductForm,
    RestaurantForm, StaffLoginForm, has_crm_access, product_fingerprint,
    product_revision, revision_matches,
)
from .models import Category, Closure, Order, Product, Restaurant, User
from .payments import release_checkout
from .onsite_payments import record_payment
from .services import product_data


def _restaurant():
    # A read does not silently create or alter restaurant settings.
    return Restaurant.objects.prefetch_related('opening_hours', 'closures').filter(pk=1).first() \
        or Restaurant(pk=1, delivery_enabled=False)


def _permissions(user):
    def allowed(*permissions):
        return user.is_active and user.is_staff and user.has_perms(permissions)
    return {
        'view_products': allowed('shop.view_product'),
        'add_product': allowed('shop.view_product', 'shop.add_product'),
        'change_products': allowed('shop.view_product', 'shop.change_product'),
        'view_orders': allowed('shop.view_order'),
        'change_orders': allowed('shop.view_order', 'shop.change_order'),
        'record_onsite_payment': allowed('shop.view_order', 'shop.change_order', 'shop.record_onsite_payment'),
        'view_restaurant': allowed('shop.view_restaurant'),
        'change_restaurant': allowed('shop.view_restaurant', 'shop.change_restaurant'),
        'view_customers': allowed('shop.view_customer', 'shop.view_order'),
    }


def _base(request, section, restaurant=None):
    restaurant = restaurant or _restaurant()
    return {
        'section': section, 'restaurant': restaurant,
        'operator_name': request.user.get_short_name() or request.user.email,
        'demo_mode': settings.DEMO_MODE, 'ordering_enabled': restaurant.ordering_enabled,
        'is_open': bool(restaurant.ordering_enabled and (settings.DEMO_MODE or restaurant.is_open())),
        'permissions': _permissions(request.user),
        'crm_updated_at': timezone.now().isoformat(),
    }


def _forbidden(request):
    return render(request, 'shop/crm/forbidden.html', _base(request, ''), status=403)


def crm_required(*permissions):
    def decorate(view):
        @wraps(view)
        @never_cache
        def checked(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), login_url=reverse('crm:login'))
            if not has_crm_access(request.user) or not request.user.has_perms(permissions):
                return _forbidden(request)
            return view(request, *args, **kwargs)
        return checked
    return decorate


def _safe_next(request):
    candidate = (request.POST.get('next') or request.GET.get('next') or '')[:2000]
    return candidate if url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()},
                                                        require_https=request.is_secure()) else reverse('crm:dashboard')


@never_cache
@require_http_methods(['GET', 'POST'])
def login_view(request):
    if has_crm_access(request.user):
        return redirect(_safe_next(request))
    form = StaffLoginForm(request=request, data=request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(_safe_next(request))
    return render(request, 'shop/crm/login.html', {
        'form': form, 'next': _safe_next(request), 'demo_mode': settings.DEMO_MODE,
    })


@never_cache
@login_required(login_url='crm:login')
@require_POST
def logout_view(request):
    logout(request)
    return redirect('crm:login')


def _products():
    return Product.objects.filter(promotional=False).select_related('category').prefetch_related('option_groups__choices')


def _image_url(product):
    if product.photo:
        return product.photo.url
    if product.image.startswith(('https://', 'http://', '/')):
        return product.image
    return f'/images/{quote(product.image, safe="")}.jpg'


def _decorate_product(product):
    product.crm_image_url = _image_url(product)
    product.crm_effective_available = product_data(product)['available']
    product.crm_revision = product_revision(product)
    return product


def _decorate_order(order, can_change):
    order.crm_next_status = ''
    order.crm_next_label = ''
    order.crm_can_cancel = False
    order.crm_can_collect = order.payment_method == 'on_site' and order.payment_status == 'due' and order.status in {'confirmed','preparing','ready'}
    order.crm_can_refund = order.payment_method == 'on_site' and order.payment_status == 'paid' and any(event.kind == 'collected' for event in order.onsite_events.all())
    if not can_change:
        return order
    next_step = {'confirmed': ('preparing', 'Préparer'),
                 'preparing': ('ready', 'Marquer prête'), 'ready': ('completed', 'Terminer')}.get(order.status)
    if next_step:
        try:
            order.check_transition(next_step[0])
            order.crm_next_status, order.crm_next_label = next_step
        except ValidationError:
            pass
    if order.status not in {'completed', 'cancelled'}:
        try:
            order.check_transition('cancelled')
            order.crm_can_cancel = True
        except ValidationError:
            pass
    return order


def _dashboard_context(request):
    context = _base(request, 'accueil')
    stats = {'confirmed': None, 'preparing': None, 'ready': None,
             'today_count': None, 'today_total': None, 'unavailable_products': None}
    recent = []
    if context['permissions']['view_orders']:
        orders = Order.objects.all()
        for status in ('confirmed', 'preparing', 'ready'):
            stats[status] = orders.filter(status=status).count()
        today = orders.filter(date__date=timezone.localdate())
        stats['today_count'] = today.count()
        stats['today_total'] = today.filter(payment_status__in=['paid', 'simulated']).exclude(status='cancelled') \
            .aggregate(amount=Sum('total'))['amount'] or Decimal('0.00')
        recent = [_decorate_order(order, context['permissions']['change_orders'])
                  for order in orders.select_related('user').prefetch_related('lines', 'history', 'onsite_events__actor')[:6]]
    if context['permissions']['view_products']:
        stats['unavailable_products'] = sum(not product_data(product)['available'] for product in _products())
    context.update(stats=stats, recent_orders=recent)
    return context


@crm_required()
@require_GET
def dashboard(request):
    return render(request, 'shop/crm/dashboard.html', _dashboard_context(request))


@crm_required('shop.view_order')
@require_GET
def dashboard_fragment(request):
    response = render(request, 'shop/crm/partials/dashboard.html', _dashboard_context(request))
    response['X-STC-Fragment'] = 'dashboard'
    return response


ORDER_FILTERS = {'active', 'history', 'all', *(value for value, _label in Order.STATUS)}


def _orders_page(request):
    source = request.POST if request.method == 'POST' else request.GET
    selected = source.get('return_filter' if request.method == 'POST' else 'status', 'active')
    selected = selected if selected in ORDER_FILTERS else 'active'
    query = source.get('return_q' if request.method == 'POST' else 'q', '')[:140].strip()
    number = source.get('return_page' if request.method == 'POST' else 'page', '1')[:20]
    number = int(number) if number.isascii() and number.isdecimal() else 1
    orders = Order.objects.select_related('user').prefetch_related('lines', 'history', 'onsite_events__actor')
    if selected == 'active':
        orders = orders.filter(status__in=['pending_payment', 'confirmed', 'preparing', 'ready'])
    elif selected == 'history':
        orders = orders.filter(status__in=['completed', 'cancelled'])
    elif selected != 'all':
        orders = orders.filter(status=selected)
    if query:
        orders = orders.filter(Q(id__icontains=query) | Q(customer__name__icontains=query)
                               | Q(customer__phone__icontains=query))
    return selected, query, Paginator(orders, 30).get_page(max(number, 1))


def _orders_context(request):
    context = _base(request, 'commandes')
    selected, query, page = _orders_page(request)
    context.update(orders=[_decorate_order(order, context['permissions']['change_orders']) for order in page],
                   page_obj=page, status_filter=selected, q=query)
    return context


def _orders_return_url(request):
    selected, query, page = _orders_page(request)
    return f'{reverse("crm:orders")}?{urlencode({"status": selected, "q": query, "page": page.number})}'


@crm_required('shop.view_order')
@require_GET
def orders(request):
    return render(request, 'shop/crm/orders.html', _orders_context(request))


@crm_required('shop.view_order')
@require_GET
def orders_fragment(request):
    response = render(request, 'shop/crm/partials/orders.html', _orders_context(request))
    response['X-STC-Fragment'] = 'orders'
    return response


@crm_required('shop.view_order', 'shop.change_order')
@require_POST
def order_status(request, pk):
    form = OrderStatusForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest('Le statut demandé est invalide.')
    try:
        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), pk=pk)
            if order.status != form.cleaned_data['expected_status']:
                raise ValidationError('Cette commande a déjà été mise à jour. Vérifiez son nouvel état.')
            target = form.cleaned_data['status']
            order.check_transition(target)
            if target == 'cancelled' and order.status == 'pending_payment':
                release_checkout(order)
            order.transition(target)
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
        return render(request, 'shop/crm/orders.html', _orders_context(request), status=409)
    messages.success(request, f'Commande {order.pk} mise à jour : {order.get_status_display().lower()}.')
    return redirect(_orders_return_url(request))


def _record_onsite_payment(request, pk, kind):
    form = OnSitePaymentForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest('L’opération demandée est invalide. Actualisez la page et recommencez.')
    try:
        order, changed = record_payment(pk, request.user, kind, **form.cleaned_data)
    except Order.DoesNotExist:
        raise Http404('Commande introuvable.')
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
        return render(request, 'shop/crm/orders.html', _orders_context(request), status=409)
    label = 'encaissement' if kind == 'collected' else 'remboursement'
    messages.success(request, f'Commande {order.pk} : {label} enregistré.' if changed else f'Commande {order.pk} : {label} déjà enregistré.')
    return redirect(_orders_return_url(request))


@crm_required('shop.view_order', 'shop.change_order', 'shop.record_onsite_payment')
@require_POST
def order_collect(request, pk):
    return _record_onsite_payment(request, pk, 'collected')


@crm_required('shop.view_order', 'shop.change_order', 'shop.record_onsite_payment')
@require_POST
def order_refund(request, pk):
    return _record_onsite_payment(request, pk, 'refunded')


def _menu_selection(request):
    source = request.POST if request.method == 'POST' else request.GET
    query = source.get('return_q' if request.method == 'POST' else 'q', '')[:140].strip()
    category = source.get('return_category' if request.method == 'POST' else 'category', '').strip()
    # IDs emitted by the category selector are positive signed 64-bit integers.
    # str.isdigit() also accepts characters such as "²", which int() rejects.
    if (not category or len(category) > 19 or not category.isascii()
            or not category.isdecimal() or int(category) > 2**63 - 1):
        category = ''
    else:
        category = str(int(category))
    return query, category


def _menu_context(request):
    context = _base(request, 'carte')
    query, category = _menu_selection(request)
    products = _products()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category:
        products = products.filter(category_id=category)
    context.update(products=[_decorate_product(product) for product in products],
                   categories=Category.objects.all(), q=query, category_filter=category)
    return context


@crm_required('shop.view_product')
@require_GET
def menu(request):
    return render(request, 'shop/crm/menu.html', _menu_context(request))


def _product_form_response(request, form, product, photo_url, is_new):
    context = _base(request, 'carte')
    context.update(form=form, product=product, photo_url=photo_url, is_new=is_new)
    return render(request, 'shop/crm/product_form.html', context)


@crm_required('shop.view_product', 'shop.add_product')
@require_http_methods(['GET', 'POST'])
def product_add(request):
    form = ProductForm(request.POST if request.method == 'POST' else None,
                       request.FILES if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            product = form.save()
        messages.success(request, f'Plat « {product.name} » ajouté.')
        return redirect('crm:menu')
    return _product_form_response(request, form, None, '', True)


@crm_required('shop.view_product', 'shop.change_product')
@require_http_methods(['GET', 'POST'])
def product_edit(request, pk):
    if request.method == 'POST':
        with transaction.atomic():
            product = get_object_or_404(_products().select_for_update(), pk=pk)
            photo_url = _image_url(product)
            form = ProductForm(request.POST, request.FILES, instance=product)
            if form.is_valid():
                form.save()
                messages.success(request, f'Plat « {product.name} » enregistré.')
                return redirect('crm:menu')
    else:
        product = get_object_or_404(_products(), pk=pk)
        photo_url = _image_url(product)
        form = ProductForm(instance=product)
    return _product_form_response(request, form, product, photo_url, False)


@crm_required('shop.view_product', 'shop.change_product')
@require_POST
def product_availability(request, pk):
    form = AvailabilityForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest('Choisissez « disponible » ou « épuisé ».')
    with transaction.atomic():
        product = get_object_or_404(_products().select_for_update(), pk=pk)
        if not revision_matches(form.cleaned_data['revision'], product, product_fingerprint(product), 'stc.crm.product'):
            messages.error(request, 'Ce plat a changé ailleurs. Vérifiez son état avant de réessayer.')
            return render(request, 'shop/crm/menu.html', _menu_context(request), status=409)
        product.available = form.cleaned_data['available']
        product.save(update_fields=['available'])
    messages.success(request, f'« {product.name} » : {"disponible" if product.available else "épuisé"}.')
    query, category = _menu_selection(request)
    parameters = {key: value for key, value in (('q', query), ('category', category)) if value}
    return redirect(f'{reverse("crm:menu")}?{urlencode(parameters)}' if parameters else reverse('crm:menu'))


def _restaurant_context(request, restaurant, form=None, opening_formset=None, closure_form=None):
    context = _base(request, 'restaurant', restaurant)
    context.update(
        form=form if form is not None else RestaurantForm(instance=restaurant),
        opening_formset=opening_formset if opening_formset is not None else OpeningFormSet(instance=restaurant, prefix='hours'),
        closure_form=closure_form if closure_form is not None else ClosureForm(restaurant=restaurant),
        closures=Closure.objects.filter(restaurant_id=restaurant.pk, date__gte=timezone.localdate()).order_by('date'),
        restaurant_tab='settings',
    )
    return context


def _customers():
    # Only the authenticated account link identifies a customer's orders. An
    # unverified e-mail or telephone must never attach a guest's order to them.
    settled = Q(order__payment_status='paid', order__payment_method='on_site', order__demo_mode=False) \
        & ~Q(order__status='cancelled')
    simulated = (Q(order__payment_status='simulated')
                 | Q(order__demo_mode=True, order__payment_status='paid')
                 | Q(order__payment_method='stripe', order__payment_status='paid')) \
        & ~Q(order__status='cancelled')
    return User.objects.filter(is_staff=False, is_superuser=False).annotate(
        crm_order_count=Count('order'),
        crm_last_order_at=Max('order__date'),
        crm_paid_total=Sum('order__total', filter=settled, default=Decimal('0.00')),
        crm_simulated_total=Sum('order__total', filter=simulated, default=Decimal('0.00')),
    ).order_by('first_name', 'last_name', 'pk')


def _customer_page_number(value):
    value = value[:20]
    return max(int(value), 1) if value.isascii() and value.isdecimal() else 1


PHONE_SEARCH_SEPARATORS = ' -().+\u00a0\u202f'


@crm_required('shop.view_customer', 'shop.view_order')
@require_GET
def customers(request):
    context = _base(request, 'restaurant')
    query = request.GET.get('q', '')[:140].strip()
    accounts = _customers()
    if query:
        matches = Q(first_name__icontains=query) | Q(last_name__icontains=query) \
            | Q(email__icontains=query) | Q(phone__icontains=query)
        compact_phone = ''.join(character for character in query if character not in PHONE_SEARCH_SEPARATORS)
        # Normalize phone-shaped searches only: extracting digits from a name or
        # e-mail would incorrectly broaden that search to unrelated customers.
        if compact_phone.isascii() and compact_phone.isdecimal():
            phone_expression = F('phone')
            for separator in PHONE_SEARCH_SEPARATORS:
                phone_expression = Replace(phone_expression, Value(separator), Value(''))
            accounts = accounts.alias(crm_search_phone=phone_expression)
            matches |= Q(crm_search_phone__contains=compact_phone)
        accounts = accounts.filter(matches)
    page = Paginator(accounts, 20).get_page(_customer_page_number(request.GET.get('page', '1')))
    context.update(customers=page, page_obj=page, q=query, restaurant_tab='customers')
    return render(request, 'shop/crm/customers.html', context)


@crm_required('shop.view_customer', 'shop.view_order')
@require_GET
def customer_detail(request, pk):
    account = _customers().filter(pk=pk).first()
    if account is None:
        return render(request, 'shop/crm/customer_not_found.html', _base(request, 'restaurant'), status=404)
    linked_orders = Order.objects.filter(user_id=account.pk).order_by('-date', '-pk')
    latest = linked_orders.first()
    snapshot = latest.customer if latest and isinstance(latest.customer, dict) else {}
    order_phone = snapshot.get('phone', '')
    order_phone = order_phone.strip()[:24] if isinstance(order_phone, str) else ''
    query = request.GET.get('q', '')[:140].strip()
    customer_page = _customer_page_number(request.GET.get('customer_page', '1'))
    page = Paginator(linked_orders, 20).get_page(_customer_page_number(request.GET.get('page', '1')))
    context = _base(request, 'restaurant')
    context.update(
        customer_account=account, customer_phone=account.phone or order_phone,
        phone_from_order=not account.phone and bool(order_phone), phone_order=latest,
        customer_orders=page, page_obj=page, q=query, customer_page=customer_page,
        customer_list_url=f'{reverse("crm:customers")}?{urlencode({"q": query, "page": customer_page})}',
        restaurant_tab='customers',
    )
    return render(request, 'shop/crm/customer_detail.html', context)


@crm_required('shop.view_restaurant')
@require_http_methods(['GET', 'POST'])
def restaurant(request):
    if request.method == 'POST':
        if not request.user.has_perm('shop.change_restaurant'):
            return _forbidden(request)
        with transaction.atomic():
            instance = Restaurant.objects.select_for_update().filter(pk=1).first() or Restaurant(pk=1, delivery_enabled=False)
            form = RestaurantForm(request.POST, instance=instance)
            opening_formset = OpeningFormSet(request.POST, instance=instance, prefix='hours')
            valid_form = form.is_valid()
            valid_hours = opening_formset.is_valid()
            if valid_form and valid_hours:
                form.save()
                opening_formset.save()
                messages.success(request, 'Les réglages et les horaires sont enregistrés.')
                return redirect('crm:restaurant')
        # ModelForm validation mutates its instance even when nothing is saved.
        # Keep the bound draft, but derive service badges from persisted settings.
        return render(request, 'shop/crm/restaurant.html', _restaurant_context(request, _restaurant(), form, opening_formset))
    instance = _restaurant()
    return render(request, 'shop/crm/restaurant.html', _restaurant_context(request, instance))


@crm_required('shop.view_restaurant', 'shop.change_restaurant')
@require_POST
def closure_add(request):
    instance = _restaurant()
    form = ClosureForm(request.POST, restaurant=instance)
    if form.is_valid():
        try:
            with transaction.atomic():
                # A closure cannot create a partial restaurant configuration.
                if not Restaurant.objects.filter(pk=instance.pk).exists():
                    form.add_error(None, 'Enregistrez d’abord les coordonnées du restaurant.')
                else:
                    form.save()
                    messages.success(request, 'La fermeture exceptionnelle est enregistrée.')
                    return redirect('crm:restaurant')
        except IntegrityError:
            form.add_error('date', 'Cette journée est déjà indiquée comme fermée.')
    return render(request, 'shop/crm/restaurant.html', _restaurant_context(request, instance, closure_form=form))


@crm_required('shop.view_restaurant', 'shop.change_restaurant')
@require_POST
def closure_delete(request, pk):
    closure = get_object_or_404(Closure, pk=pk, restaurant_id=1)
    closure.delete()
    messages.success(request, 'La fermeture exceptionnelle a été retirée.')
    return redirect('crm:restaurant')
