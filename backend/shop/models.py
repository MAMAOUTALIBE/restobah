import secrets
import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


def order_reference():
    return 'STC-' + uuid.uuid4().hex[:12].upper()

def guest_token():
    return secrets.token_urlsafe(32)

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('Adresse e-mail requise.')
        user = self.model(email=email.strip().lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user
    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        if not extra['is_staff'] or not extra['is_superuser']:
            raise ValueError('Un administrateur doit avoir les droits requis.')
        return self.create_user(email, password, **extra)

class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()
    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'),name='unique_user_email_ci')]
    def clean(self):
        super().clean()
        self.email=self.email.strip().lower()
    def save(self,*args,**kwargs):
        self.email=self.email.strip().lower()
        return super().save(*args,**kwargs)
    def __str__(self):
        return self.email

class Restaurant(models.Model):
    name = models.CharField(max_length=80, default='STC')
    address = models.CharField(max_length=200, default='24 rue des Gourmands')
    city = models.CharField(max_length=100, default='Paris, 11e')
    delivery_fee = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('3.90'), validators=[MinValueValidator(0)])
    min_delivery_total = models.DecimalField(max_digits=7, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    # Required by clean() only while delivery is enabled.
    delivery_postal_codes = models.JSONField(default=list, blank=True)
    ordering_enabled = models.BooleanField(default=True)
    pickup_enabled = models.BooleanField(default=True)
    delivery_enabled = models.BooleanField(default=True)
    pickup_delay = models.CharField('délai de retrait affiché', max_length=30, default='15–20 min')
    delivery_delay = models.CharField('délai de livraison affiché', max_length=30, default='30–40 min')
    def clean(self):
        if self.pk != 1 and Restaurant.objects.exclude(pk=self.pk).exists():
            raise ValidationError('Un seul restaurant peut être configuré.')
        if not isinstance(self.delivery_postal_codes, list) or any(not isinstance(x, str) or len(x) != 5 or not x.isdigit() for x in self.delivery_postal_codes):
            raise ValidationError('Les codes postaux doivent être une liste de chaînes à cinq chiffres.')
        if self.delivery_enabled and not self.delivery_postal_codes:
            raise ValidationError({'delivery_postal_codes': 'Renseignez au moins un code postal livré, ou désactivez la livraison.'})
    def is_open(self, at=None):
        at = timezone.localtime(at or timezone.now())
        if self.closures.filter(date=at.date()).exists():
            return False
        from datetime import timedelta
        previous_date = at.date() - timedelta(days=1)
        for period in self.opening_hours.all():
            if period.opens < period.closes:
                if period.weekday == at.weekday() and period.opens <= at.time().replace(tzinfo=None) < period.closes:
                    return True
            else:
                if period.weekday == at.weekday() and at.time().replace(tzinfo=None) >= period.opens:
                    return True
                if period.weekday == previous_date.weekday() and at.time().replace(tzinfo=None) < period.closes and not self.closures.filter(date=previous_date).exists():
                    return True
        return False
    def __str__(self):
        return self.name

class OpeningHour(models.Model):
    restaurant = models.ForeignKey(Restaurant, related_name='opening_hours', on_delete=models.CASCADE)
    weekday = models.PositiveSmallIntegerField(choices=list(enumerate(['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'])))
    opens = models.TimeField()
    closes = models.TimeField()
    class Meta:
        ordering = ['weekday', 'opens']
    def clean(self):
        if self.opens == self.closes:
            raise ValidationError('Les heures d’ouverture et de fermeture doivent être différentes.')
    def __str__(self):
        return f'{self.get_weekday_display()} {self.opens}–{self.closes}'

class Closure(models.Model):
    restaurant = models.ForeignKey(Restaurant, related_name='closures', on_delete=models.CASCADE)
    date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['restaurant','date'], name='unique_restaurant_closure')]
    def __str__(self):
        return str(self.date)

class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    class Meta:
        ordering = ['position','id']
        verbose_name_plural = 'Catégories'
    def __str__(self):
        return self.name

class OptionGroup(models.Model):
    id = models.SlugField(primary_key=True)
    name = models.CharField(max_length=100)
    minimum = models.PositiveSmallIntegerField(default=0)
    maximum = models.PositiveSmallIntegerField(default=1)
    class Meta:
        ordering = ['-minimum','id']
    def clean(self):
        if self.minimum > self.maximum:
            raise ValidationError('Le minimum ne peut pas dépasser le maximum.')
    def __str__(self):
        return self.name

class Choice(models.Model):
    id = models.SlugField(primary_key=True)
    group = models.ForeignKey(OptionGroup, related_name='choices', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=6, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    available = models.BooleanField(default=True)
    class Meta:
        ordering = ['id']
    def __str__(self):
        return f'{self.group}: {self.name}'

class Product(models.Model):
    name = models.CharField(max_length=140)
    category = models.ForeignKey(Category, related_name='products', on_delete=models.PROTECT)
    description = models.TextField()
    summary = models.CharField(max_length=200, blank=True)
    price = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    image = models.CharField(max_length=300, default='burger')
    photo = models.ImageField(upload_to='products/', blank=True)
    badge = models.CharField(max_length=40, blank=True)
    # Display only verified ratings; leave blank to hide the star.
    rating = models.CharField(max_length=5, blank=True, default='')
    vegetarian = models.BooleanField(default=False)
    available = models.BooleanField(default=True)
    allergens = models.JSONField(default=list)
    option_groups = models.ManyToManyField(OptionGroup, blank=True)
    promotional = models.BooleanField(default=False)
    promotion_source = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    discount_percent = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    promotion_starts = models.DateTimeField(null=True, blank=True)
    promotion_ends = models.DateTimeField(null=True, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    class Meta:
        ordering = ['position','id']
    def clean(self):
        if self.promotion_source_id == self.pk and self.pk:
            raise ValidationError('Une promotion ne peut pas se référencer elle-même.')
        if self.promotion_source_id and self.promotion_source.promotional:
            raise ValidationError('Une promotion doit référencer un produit sans promotion.')
        if self.promotional and not self.promotion_source_id:
            raise ValidationError('Sélectionnez le produit d’origine de la promotion.')
        if self.promotion_starts and self.promotion_ends and self.promotion_starts >= self.promotion_ends:
            raise ValidationError('La fin de promotion doit suivre son début.')
        if not isinstance(self.allergens, list) or any(not isinstance(x, str) or not x.strip() or len(x) > 60 for x in self.allergens):
            raise ValidationError({'allergens': 'Saisissez une liste JSON de noms, par exemple ["gluten", "lait"].'})
    def is_available(self):
        now = timezone.now()
        return self.available and (not self.promotion_starts or now >= self.promotion_starts) and (not self.promotion_ends or now < self.promotion_ends) and (not self.promotion_source_id or self.promotion_source.available)
    def current_price(self):
        price = self.promotion_source.price if self.promotion_source_id else self.price
        return (price * (Decimal(100)-self.discount_percent)/100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    def __str__(self):
        return self.name

class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='addresses', on_delete=models.CASCADE)
    label = models.CharField(max_length=60, default='Domicile')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=25)
    address = models.CharField(max_length=200)
    postal = models.CharField(max_length=5)
    city = models.CharField(max_length=100)
    def __str__(self):
        return f'{self.label} — {self.user_id}'

class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','product'],name='unique_favorite')]

class OrderQuerySet(models.QuerySet):
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False, update_fields=None, unique_fields=None):
        if update_conflicts and update_fields and 'payment_method' in update_fields:
            raise ValidationError('Le mode de paiement d’une commande ne peut pas être modifié.')
        return super().bulk_create(objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
                                   update_conflicts=update_conflicts, update_fields=update_fields, unique_fields=unique_fields)

    def update(self, **kwargs):
        if 'payment_method' in kwargs:
            raise ValidationError('Le mode de paiement d’une commande ne peut pas être modifié.')
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if 'payment_method' in fields:
            raise ValidationError('Le mode de paiement d’une commande ne peut pas être modifié.')
        return super().bulk_update(objs, fields, **kwargs)


class Order(models.Model):
    STATUS = [('pending_payment','En attente de paiement'),('confirmed','Confirmée'),('preparing','En cuisine'),('ready','Prête'),('completed','Terminée'),('cancelled','Annulée')]
    PAYMENT = [('simulated','Simulé'),('pending','En attente'),('due','À régler sur place'),('paid','Payé'),('failed','Échoué'),('cancelled','Annulé'),('refunded','Remboursé')]
    PAYMENT_METHODS = [('simulation','Simulation'),('stripe','Stripe test'),('on_site','Sur place')]
    objects = OrderQuerySet.as_manager()
    id = models.CharField(primary_key=True,max_length=20,default=order_reference,editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    access_token = models.CharField(max_length=80,default=guest_token,unique=True,editable=False)
    scope = models.CharField(max_length=100,editable=False)
    idempotency_key = models.CharField(max_length=100,editable=False)
    payload_hash = models.CharField(max_length=64,editable=False)
    date = models.DateTimeField(auto_now_add=True)
    mode = models.CharField(max_length=20,choices=[('À emporter','À emporter'),('Livraison','Livraison')])
    status = models.CharField(max_length=20,choices=STATUS,default='confirmed')
    payment_status = models.CharField(max_length=20,choices=PAYMENT,default='simulated')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='simulation', db_default='simulation', editable=False)
    demo_mode = models.BooleanField(default=True)
    subtotal = models.DecimalField(max_digits=9,decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=6,decimal_places=2,default=0)
    total = models.DecimalField(max_digits=9,decimal_places=2)
    customer = models.JSONField()
    class Meta:
        ordering = ['-date']
        permissions = [('record_onsite_payment', 'Peut enregistrer les règlements et remboursements sur place')]
        constraints = [models.UniqueConstraint(fields=['scope','idempotency_key'],name='unique_order_idempotency')]
    TRANSITIONS = {'pending_payment': {'cancelled'}, 'confirmed': {'preparing','cancelled'}, 'preparing': {'ready','cancelled'}, 'ready': {'completed','cancelled'}, 'completed':set(),'cancelled':set()}
    def check_transition(self, status):
        if self.status == status:
            return
        if status not in self.TRANSITIONS.get(self.status,set()):
            raise ValidationError('Ce changement de statut n’est pas autorisé.')
        permitted_unpaid = self.payment_method == 'on_site' and self.payment_status == 'due' and status in {'preparing','ready'}
        if status in {'preparing','ready','completed'} and self.payment_status not in {'paid','simulated'} and not permitted_unpaid:
            if self.payment_method == 'on_site':
                raise ValidationError('Enregistrez l’encaissement avant de terminer cette commande.')
            raise ValidationError('Le paiement doit être confirmé avant la préparation.')
        if status == 'cancelled' and self.payment_status == 'paid':
            if self.payment_method == 'on_site':
                raise ValidationError('Enregistrez le remboursement avant d’annuler cette commande.')
            raise ValidationError('Remboursez d’abord le paiement dans Stripe et attendez le webhook avant d’annuler.')
    def save(self, *args, **kwargs):
        original = type(self).objects.using(kwargs.get('using') or self._state.db).filter(pk=self.pk).values_list('payment_method', flat=True).first() if self.pk else None
        if original is not None and original != self.payment_method:
            raise ValidationError('Le mode de paiement d’une commande ne peut pas être modifié.')
        return super().save(*args, **kwargs)
    @property
    def payment_label(self):
        if self.payment_method == 'on_site':
            if self.payment_status == 'due':
                return 'À régler à la livraison' if self.mode == 'Livraison' else 'À régler au restaurant'
            if self.payment_status == 'paid':
                return 'Réglé sur place'
            if self.payment_status == 'refunded':
                return 'Remboursé sur place'
        return 'Paiement simulé' if self.payment_status == 'simulated' else f'Paiement : {self.get_payment_status_display().lower()}'
    @property
    def refund_required(self):
        # A payment confirmed after cancellation (session completed during the cancel race).
        return self.status == 'cancelled' and self.payment_status == 'paid'
    def transition(self, status):
        """Database-only transition. Cancelling a Stripe order must first go through payments.release_checkout."""
        self.check_transition(status)
        if self.status == status:
            return
        self.status = status
        if status == 'cancelled' and self.payment_status in {'pending','failed','due'}:
            self.payment_status = 'cancelled'
        self.save(update_fields=['status','payment_status'])
        OrderHistory.objects.create(order=self,status=status)
    def __str__(self):
        return f'{self.id} — {self.get_status_display()}'

class OrderLine(models.Model):
    order = models.ForeignKey(Order,related_name='lines',on_delete=models.CASCADE)
    product = models.ForeignKey(Product,null=True,on_delete=models.SET_NULL)
    name = models.CharField(max_length=140)
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(max_digits=8,decimal_places=2)
    total = models.DecimalField(max_digits=9,decimal_places=2)
    choices = models.JSONField(default=list)

class OrderHistory(models.Model):
    order = models.ForeignKey(Order,related_name='history',on_delete=models.CASCADE)
    status = models.CharField(max_length=20,choices=Order.STATUS)
    date = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['date','id']

class Payment(models.Model):
    order = models.OneToOneField(Order,related_name='payment',on_delete=models.PROTECT)
    session_id = models.CharField(max_length=255,blank=True,unique=True,null=True)
    payment_intent = models.CharField(max_length=255,blank=True)
    checkout_url = models.URLField(max_length=2000,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OnSitePaymentEventQuerySet(models.QuerySet):
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False, update_fields=None, unique_fields=None):
        if update_conflicts:
            raise ValidationError('Un événement de règlement ne peut pas être modifié.')
        return super().bulk_create(objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts,
                                   update_conflicts=False, update_fields=update_fields, unique_fields=unique_fields)

    def update(self, **kwargs):
        raise ValidationError('Un événement de règlement ne peut pas être modifié.')

    def delete(self):
        raise ValidationError('Un événement de règlement ne peut pas être supprimé.')


class OnSitePaymentEvent(models.Model):
    KINDS = [('collected', 'Encaissement enregistré'), ('refunded', 'Remboursement enregistré')]
    objects = OnSitePaymentEventQuerySet.as_manager()
    order = models.ForeignKey(Order, related_name='onsite_events', on_delete=models.PROTECT)
    kind = models.CharField(max_length=20, choices=KINDS)
    amount = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(0)])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='onsite_payment_events', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [models.UniqueConstraint(fields=['order', 'kind'], name='unique_onsite_payment_kind'),
                       models.CheckConstraint(condition=models.Q(amount__gte=0), name='onsite_payment_nonnegative')]

    def save(self, *args, **kwargs):
        existing = self.pk is not None and type(self).objects.using(kwargs.get('using') or self._state.db).filter(pk=self.pk).exists()
        if not self._state.adding or existing or kwargs.get('force_update') or kwargs.get('update_fields') is not None:
            raise ValidationError('Un événement de règlement ne peut pas être modifié.')
        # Never let Django's normal UPDATE-then-INSERT fallback rewrite a row,
        # including if another insert claims an explicitly supplied PK after the check.
        kwargs['force_insert'] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Un événement de règlement ne peut pas être supprimé.')

class StripeEvent(models.Model):
    id = models.CharField(primary_key=True,max_length=255)
    event_type = models.CharField(max_length=120)
    date = models.DateTimeField(auto_now_add=True)

class AdminLoginAttempt(models.Model):
    """Shared worker-safe login counter; only a keyed hash of the IP is stored."""
    key=models.CharField(primary_key=True,max_length=64,editable=False)
    count=models.PositiveIntegerField(default=0)
    window_started=models.DateTimeField(default=timezone.now,db_index=True)
