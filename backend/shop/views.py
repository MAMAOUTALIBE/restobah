import logging
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.urls import Resolver404, resolve, reverse
from django.utils.cache import add_never_cache_headers
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from .models import Product, Address, Favorite, Order
from .serializers import AddressSerializer, RegisterSerializer, ProfileSerializer, LoginSerializer, ResetSerializer, ResetConfirmSerializer, OrderInputSerializer, DeleteAccountSerializer
from .services import restaurant_data, categories_data, product_data, order_data, authorized_order, create_order
from .account_links import password_reset_available, password_reset_link

User = get_user_model()
logger = logging.getLogger('shop.accounts')

def csrf_failure(request,reason=''):
    if request.path_info == '/crm' or request.path_info.startswith('/crm/'):
        destination, label, kwargs = 'crm:dashboard', 'Revenir à l’accueil', None
        try:
            match = resolve(request.path_info)
        except Resolver404:
            match = None
        if match and match.namespace == 'crm':
            recovery = {
                'login': ('crm:login', 'Revenir à la connexion'),
                'product_add': ('crm:product_add', 'Actualiser le formulaire'),
                'product_edit': ('crm:product_edit', 'Actualiser le formulaire'),
                'product_availability': ('crm:menu', 'Revenir à ma carte'),
                'order_status': ('crm:orders', 'Revenir aux commandes'),
                'order_collect': ('crm:orders', 'Revenir aux commandes'),
                'order_refund': ('crm:orders', 'Revenir aux commandes'),
                'restaurant': ('crm:restaurant', 'Actualiser le formulaire'),
                'closure_add': ('crm:restaurant', 'Revenir à mon restaurant'),
                'closure_delete': ('crm:restaurant', 'Revenir à mon restaurant'),
            }
            destination, label = recovery.get(match.url_name, (destination, label))
            if destination == 'crm:product_edit':
                kwargs = {'pk': match.kwargs['pk']}
        response = render(request, 'shop/crm/csrf_failure.html', {
            'return_url': reverse(destination, kwargs=kwargs),
            'return_label': label,
            'show_login': destination != 'crm:login',
        }, status=403)
        add_never_cache_headers(response)
        return response
    response = JsonResponse({'detail':'Session de sécurité expirée. Actualisez la page et réessayez.'},status=403)
    # CSRF can reject a request before the private view's dispatch decorator runs.
    add_never_cache_headers(response)
    return response

def user_data(user):
    return {'id':user.id,'name':user.first_name,'email':user.email,'phone':user.phone}

@method_decorator(never_cache,name='dispatch')
class PrivateAPIView(APIView):
    """Session and personal responses must not be retained by HTTP caches."""

@method_decorator(csrf_protect,name='dispatch')
class ProtectedView(PrivateAPIView):
    pass

class HealthView(APIView):
    throttle_classes = []
    def get(self,request):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            return Response({'status':'ok','service':'stc-api'})
        except Exception:
            return Response({'status':'unavailable'},status=503)

@method_decorator(ensure_csrf_cookie,name='dispatch')
class CsrfView(PrivateAPIView):
    def get(self,request):
        get_token(request)
        if not request.session.session_key or not request.session.exists(request.session.session_key):
            request.session.create()
        return Response({'detail':'Protection de session initialisée.'})

class ProductsView(APIView):
    def get(self,request):
        products = Product.objects.select_related('category','promotion_source').prefetch_related('option_groups__choices')
        return Response([product_data(p,request) for p in products])

class CategoriesView(APIView):
    def get(self,request):
        return Response(categories_data())

class RestaurantView(APIView):
    def get(self,request):
        return Response(restaurant_data())

class MeView(ProtectedView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get(self,request):
        return Response({'user':user_data(request.user) if request.user.is_authenticated else None})

    def patch(self,request):
        serializer = ProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = []
        for key, field in [('name', 'first_name'), ('phone', 'phone')]:
            if key in serializer.validated_data:
                setattr(request.user, field, serializer.validated_data[key])
                fields.append(field)
        if fields:
            request.user.save(update_fields=fields)
        return Response({'user':user_data(request.user)})

class AuthView(ProtectedView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'

class AuthCapabilitiesView(PrivateAPIView):
    def get(self,request):
        return Response({'passwordResetAvailable': password_reset_available()})

class RegisterView(AuthView):
    def post(self,request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User(email=data['email'],first_name=data['name'])
        try:
            validate_password(data['password'],user)
        except DjangoValidationError as error:
            raise ValidationError({'password':error.messages})
        try:
            user.set_password(data['password'])
            user.save()
        except IntegrityError:
            raise ValidationError('Cette adresse est déjà utilisée.')
        login(request,user,backend='django.contrib.auth.backends.ModelBackend')
        return Response({'user':user_data(user)},status=201)

class LoginView(AuthView):
    def post(self,request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = authenticate(request,email=data['email'].strip().lower(),password=data['password'])
        if not user:
            raise AuthenticationFailed('Adresse e-mail ou mot de passe incorrect.')
        login(request,user)
        return Response({'user':user_data(user)})

class LogoutView(ProtectedView):
    def post(self,request):
        logout(request)
        return Response({'detail':'Vous êtes déconnecté.'})

class ResetView(AuthView):
    def post(self,request):
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email,is_active=True).first()
        if user and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            try:
                url = password_reset_link(uid, token)
                send_mail('STC — Réinitialiser votre mot de passe',f'Bonjour,\n\nPour choisir un nouveau mot de passe, ouvrez ce lien valable une heure :\n{url}\n\nSi vous n’êtes pas à l’origine de cette demande, ignorez cet e-mail.\n\nSTC',settings.DEFAULT_FROM_EMAIL,[user.email],fail_silently=False)
            except Exception:
                # Keep the public response identical, but let the team see SMTP failures.
                logger.exception('Échec de l’envoi de l’e-mail de réinitialisation.')
        return Response({'detail':'Si un compte correspond à cette adresse, un lien de réinitialisation a été envoyé.'})

class ResetConfirmView(AuthView):
    def post(self,request):
        serializer = ResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data['uid'])),is_active=True)
        except (ValueError,TypeError,OverflowError,User.DoesNotExist,UnicodeDecodeError):
            raise ValidationError('Ce lien de réinitialisation est invalide ou expiré.')
        if not default_token_generator.check_token(user,data['token']):
            raise ValidationError('Ce lien de réinitialisation est invalide ou expiré.')
        try:
            validate_password(data['password'],user)
        except DjangoValidationError as error:
            raise ValidationError({'password':error.messages})
        user.set_password(data['password'])
        user.save(update_fields=['password'])
        return Response({'detail':'Votre mot de passe a été modifié. Vous pouvez vous connecter.'})

class DeleteAccountView(AuthView):
    """Self-service erasure: account, addresses and favourites; placed orders stay with the restaurant."""
    permission_classes = [permissions.IsAuthenticated]
    def post(self,request):
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data['password']):
            raise ValidationError({'password':['Mot de passe incorrect.']})
        if request.user.is_staff:
            raise ValidationError('Les comptes de l’équipe se suppriment depuis l’administration.')
        try:
            with transaction.atomic():
                # Orders keep their contact snapshot but are detached from the account (on_delete=SET_NULL).
                User.objects.select_for_update().get(pk=request.user.pk).delete()
        except ProtectedError:
            # Former staff can still be protected actors in the financial register.
            # Handle refusal after the transaction has rolled back every related change.
            raise ValidationError('Ce compte ne peut pas être supprimé. Contactez le restaurant.')
        logout(request)
        return Response({'detail':'Votre compte a été supprimé. Les commandes déjà passées restent enregistrées par le restaurant.'})

class AddressesView(ProtectedView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self,request):
        return Response(AddressSerializer(Address.objects.filter(user=request.user).order_by('id'),many=True).data)
    def post(self,request):
        if Address.objects.filter(user=request.user).count() >= 20:
            raise ValidationError('Vous avez atteint la limite de 20 adresses.')
        serializer = AddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data,status=201)

class AddressView(ProtectedView):
    permission_classes = [permissions.IsAuthenticated]
    def get_address(self,request,pk):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(Address,user=request.user,pk=pk)
    def patch(self,request,pk):
        serializer = AddressSerializer(self.get_address(request,pk),data=request.data,partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    def delete(self,request,pk):
        self.get_address(request,pk).delete()
        return Response(status=204)

class FavoritesView(ProtectedView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self,request):
        return Response(list(Favorite.objects.filter(user=request.user).order_by('product_id').values_list('product_id',flat=True)))
    def put(self,request):
        values = request.data.get('productIds') if isinstance(request.data,dict) else None
        if not isinstance(values,list) or len(values)>500 or any(type(i) is not int for i in values):
            raise ValidationError('La liste de favoris est invalide.')
        ids = set(values)
        if Product.objects.filter(pk__in=ids,promotional=False).count()!=len(ids):
            raise ValidationError('Un produit favori est introuvable.')
        with transaction.atomic():
            # Serialize concurrent replacements of the same account favorites.
            User.objects.select_for_update().get(pk=request.user.pk)
            Favorite.objects.filter(user=request.user).exclude(product_id__in=ids).delete()
            Favorite.objects.bulk_create([Favorite(user=request.user,product_id=i) for i in ids],ignore_conflicts=True)
        return self.get(request)

class OrdersView(ProtectedView):
    throttle_scope = 'orders'
    def get_throttles(self):
        # Only order creation is scoped; history polling must never block a later order.
        return [ScopedRateThrottle()] if self.request.method == 'POST' else super().get_throttles()
    def get(self,request):
        if not request.user.is_authenticated:
            from rest_framework.exceptions import NotAuthenticated
            raise NotAuthenticated('Connectez-vous pour consulter vos commandes.')
        orders = Order.objects.filter(user=request.user).prefetch_related('lines','history')[:100]
        return Response([order_data(o,include_customer=True) for o in orders])
    def post(self,request):
        serializer = OrderInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order,created = create_order(request,serializer.validated_data,request.headers.get('Idempotency-Key',''))
        return Response(order_data(order,include_token=True),status=201 if created else 200)

class OrderView(PrivateAPIView):
    def get(self,request,pk):
        order = authorized_order(request,pk,allow_staff=True)
        # Guest token grants access to totals and tracking, not contact PII.
        owner = request.user.is_authenticated and request.user.is_active and (
            order.user_id==request.user.id or request.user.is_staff and request.user.has_perm('shop.view_order')
        )
        return Response(order_data(order,include_customer=owner))
