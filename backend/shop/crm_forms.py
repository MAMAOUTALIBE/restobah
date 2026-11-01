"""Short, server-validated forms for the restaurant management interface."""
import hashlib
import hmac
import io
import json
import re
import uuid
import warnings

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.forms import BaseInlineFormSet, inlineformset_factory
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Category, Closure, OpeningHour, OptionGroup, Order, Product, Restaurant


CRM_PERMISSIONS = (
    'shop.view_product', 'shop.add_product', 'shop.change_product',
    'shop.view_order', 'shop.change_order',
    'shop.view_restaurant', 'shop.change_restaurant',
    'shop.view_customer',
)
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_SIDE = 6000
MAX_PHOTO_PIXELS = 20_000_000
REVISION_AGE = 12 * 60 * 60


def has_crm_access(user):
    return user.is_authenticated and user.is_active and user.is_staff and any(
        user.has_perm(permission) for permission in CRM_PERMISSIONS
    )


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def product_fingerprint(product):
    fields = ('name', 'category_id', 'price', 'description', 'summary', 'photo',
              'available', 'badge', 'vegetarian', 'allergens')
    data = {field: str(getattr(product, field)) if field == 'photo' else getattr(product, field)
            for field in fields}
    data['option_groups'] = sorted(group.pk for group in product.option_groups.all()) if product.pk else []
    return _digest(data)


def restaurant_fingerprint(restaurant):
    fields = ('name', 'address', 'city', 'ordering_enabled', 'pickup_enabled',
              'delivery_enabled', 'pickup_delay', 'delivery_delay', 'delivery_fee',
              'min_delivery_total', 'delivery_postal_codes')
    data = {field: getattr(restaurant, field) for field in fields}
    data['hours'] = list(OpeningHour.objects.filter(restaurant_id=restaurant.pk)
                         .order_by('pk').values_list('pk', 'weekday', 'opens', 'closes')) if restaurant.pk else []
    return _digest(data)


def product_revision(product):
    return signing.dumps({'id': product.pk, 'state': product_fingerprint(product)}, salt='stc.crm.product')


def restaurant_revision(restaurant):
    return signing.dumps({'id': restaurant.pk, 'state': restaurant_fingerprint(restaurant)}, salt='stc.crm.restaurant')


def revision_matches(token, instance, fingerprint, salt):
    try:
        data = signing.loads(token, salt=salt, max_age=REVISION_AGE)
        return data.get('id') == instance.pk and hmac.compare_digest(data.get('state', ''), fingerprint)
    except (signing.BadSignature, TypeError, ValueError, AttributeError):
        return False


class StaffLoginForm(AuthenticationForm):
    username = forms.EmailField(label='Adresse e-mail', widget=forms.EmailInput(attrs={
        'autocomplete': 'username', 'autofocus': True,
    }))
    password = forms.CharField(label='Mot de passe', strip=False,
                              widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))
    error_messages = {
        'invalid_login': 'Connexion impossible. Vérifiez vos accès gérant.',
        'inactive': 'Connexion impossible. Vérifiez vos accès gérant.',
    }

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not has_crm_access(user):
            raise forms.ValidationError(self.error_messages['invalid_login'], code='invalid_login')


class AliasedModelErrorsMixin:
    model_error_aliases = {}

    def _update_errors(self, errors):
        if hasattr(errors, 'error_dict'):
            errors = ValidationError({self.model_error_aliases.get(key, key): value
                                      for key, value in errors.error_dict.items()})
        return super()._update_errors(errors)


class PhotoUploadField(forms.ImageField):
    def to_python(self, data):
        if data and getattr(data, 'size', 0) > MAX_PHOTO_BYTES:
            raise forms.ValidationError('Choisissez une photo de 5 Mo maximum.')
        return super().to_python(data)


class ProductForm(AliasedModelErrorsMixin, forms.ModelForm):
    model_error_aliases = {'allergens': 'allergens_text'}
    price = forms.DecimalField(label='Prix (€)', max_digits=7, decimal_places=2,
                               min_value=0, localize=True,
                               widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': '11,90'}))
    photo = PhotoUploadField(label='Photo du plat', required=False,
                             widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}))
    allergens_text = forms.CharField(label='Allergènes', required=False, max_length=2000,
                                     help_text='Séparez les noms par des virgules, par exemple : gluten, lait.')
    revision = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Product
        fields = ('name', 'category', 'price', 'description', 'photo', 'available',
                  'summary', 'badge', 'vegetarian', 'option_groups')
        labels = {
            'name': 'Nom du plat', 'category': 'Catégorie', 'description': 'Description',
            'available': 'Disponible à la commande', 'summary': 'Description courte',
            'badge': 'Petit badge', 'vegetarian': 'Végétarien', 'option_groups': 'Choix proposés au client',
        }
        widgets = {'description': forms.Textarea(attrs={'rows': 3}),
                   'summary': forms.TextInput(attrs={'placeholder': 'Une courte phrase suffit'}),
                   'option_groups': forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.all()
        self.fields['option_groups'].queryset = OptionGroup.objects.all()
        self._original_fingerprint = product_fingerprint(self.instance) if self.instance.pk else None
        if self.instance.pk and not self.is_bound:
            self.initial['allergens_text'] = ', '.join(self.instance.allergens or [])
            self.initial['revision'] = product_revision(self.instance)

    def clean_name(self):
        value = self.cleaned_data['name'].strip()
        if not value:
            raise forms.ValidationError('Donnez un nom à ce plat.')
        return value

    def clean_description(self):
        value = self.cleaned_data['description'].strip()
        if not value:
            raise forms.ValidationError('Ajoutez une courte description.')
        return value

    def clean_allergens_text(self):
        values = list(dict.fromkeys(part.strip() for part in self.cleaned_data['allergens_text'].split(',') if part.strip()))
        if len(values) > 30 or any(len(value) > 60 for value in values):
            raise forms.ValidationError('Indiquez au plus 30 allergènes, avec des noms de 60 caractères maximum.')
        return values

    def clean_revision(self):
        value = self.cleaned_data.get('revision', '')
        if self.instance.pk and not revision_matches(value, self.instance, self._original_fingerprint, 'stc.crm.product'):
            raise forms.ValidationError('Ce plat a changé depuis son ouverture. Rechargez sa fiche avant de réessayer.')
        return value

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if not photo or not hasattr(photo, 'content_type'):
            return photo
        if photo.size > MAX_PHOTO_BYTES:
            raise forms.ValidationError('Choisissez une photo de 5 Mo maximum.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                photo.seek(0)
                image = Image.open(photo)
                if image.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise forms.ValidationError('Utilisez une photo JPEG, PNG ou WebP.')
                width, height = image.size
                if max(width, height) > MAX_PHOTO_SIDE or width * height > MAX_PHOTO_PIXELS:
                    raise forms.ValidationError('Cette photo est trop grande. Maximum : 6 000 pixels de côté et 20 millions de pixels.')
                if getattr(image, 'n_frames', 1) != 1:
                    raise forms.ValidationError('Choisissez une photo fixe, sans animation.')
                image.verify()
                photo.seek(0)
                image = ImageOps.exif_transpose(Image.open(photo))
                image.load()
                if image.mode in {'RGBA', 'LA'} or (image.mode == 'P' and 'transparency' in image.info):
                    rgba = image.convert('RGBA')
                    clean = Image.new('RGB', rgba.size, 'white')
                    clean.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    clean = image.convert('RGB')
                output = io.BytesIO()
                clean.save(output, format='JPEG', quality=88, optimize=True)
        except forms.ValidationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError('La photo est illisible. Choisissez une image JPEG, PNG ou WebP valide.')
        return ContentFile(output.getvalue(), name=f'{uuid.uuid4().hex}.jpg')

    def clean(self):
        cleaned = super().clean()
        if 'allergens_text' in cleaned:
            self.instance.allergens = cleaned['allergens_text']
        return cleaned


class AvailabilityForm(forms.Form):
    available = forms.TypedChoiceField(choices=(('1', 'Disponible'), ('0', 'Épuisé')),
                                        coerce=lambda value: value == '1')
    revision = forms.CharField(widget=forms.HiddenInput)


class RestaurantForm(AliasedModelErrorsMixin, forms.ModelForm):
    model_error_aliases = {'delivery_postal_codes': 'postal_codes_text'}
    delivery_fee = forms.DecimalField(label='Frais de livraison (€)', max_digits=6, decimal_places=2,
                                      min_value=0, localize=True, widget=forms.TextInput(attrs={'inputmode': 'decimal'}))
    min_delivery_total = forms.DecimalField(label='Minimum de livraison (€)', max_digits=7, decimal_places=2,
                                           min_value=0, localize=True, widget=forms.TextInput(attrs={'inputmode': 'decimal'}))
    postal_codes_text = forms.CharField(label='Codes postaux livrés', required=False, max_length=2000,
                                        help_text='Séparez les codes par des virgules ou des espaces.')
    revision = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Restaurant
        fields = ('name', 'address', 'city', 'ordering_enabled', 'pickup_enabled', 'delivery_enabled',
                  'pickup_delay', 'delivery_delay', 'delivery_fee', 'min_delivery_total')
        labels = {'name': 'Nom du restaurant', 'address': 'Adresse', 'city': 'Ville',
                  'ordering_enabled': 'Accepter les commandes en ligne', 'pickup_enabled': 'À emporter',
                  'delivery_enabled': 'Livraison', 'pickup_delay': 'Délai à emporter', 'delivery_delay': 'Délai de livraison'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_fingerprint = restaurant_fingerprint(self.instance)
        if not self.is_bound:
            self.initial['postal_codes_text'] = ', '.join(self.instance.delivery_postal_codes or [])
            self.initial['revision'] = restaurant_revision(self.instance)

    def clean_revision(self):
        value = self.cleaned_data.get('revision', '')
        if not revision_matches(value, self.instance, self._original_fingerprint, 'stc.crm.restaurant'):
            raise forms.ValidationError('Les réglages ou les horaires ont changé ailleurs. Rechargez cette page avant de réessayer.')
        return value

    def clean_postal_codes_text(self):
        values = list(dict.fromkeys(value for value in re.split(r'[,;\s]+', self.cleaned_data['postal_codes_text'].strip()) if value))
        if any(not re.fullmatch(r'[0-9]{5}', value) for value in values):
            raise forms.ValidationError('Chaque code postal doit contenir 5 chiffres, par exemple 75011.')
        return values

    def clean(self):
        cleaned = super().clean()
        if 'postal_codes_text' in cleaned:
            self.instance.delivery_postal_codes = cleaned['postal_codes_text']
            if cleaned.get('delivery_enabled') and not cleaned['postal_codes_text']:
                self.add_error('postal_codes_text', 'Indiquez au moins un code postal livré, ou désactivez la livraison.')
        return cleaned


class OpeningHourForm(forms.ModelForm):
    class Meta:
        model = OpeningHour
        fields = ('weekday', 'opens', 'closes')
        labels = {'weekday': 'Jour', 'opens': 'Ouverture', 'closes': 'Fermeture'}
        widgets = {'opens': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
                   'closes': forms.TimeInput(format='%H:%M', attrs={'type': 'time'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Preserve existing precise periods without adding seconds to ordinary forms.
        for name in ('opens', 'closes'):
            value = getattr(self.instance, name, None)
            if value and (value.second or value.microsecond):
                self.fields[name].widget.format = '%H:%M:%S.%f' if value.microsecond else '%H:%M:%S'
                self.fields[name].widget.attrs['step'] = '0.000001' if value.microsecond else '1'


class OpeningHoursFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if self.is_bound:
            expected_ids = set(self.queryset.values_list('pk', flat=True))
            initial = self.initial_form_count()
            supplied_ids = [form.cleaned_data.get('id').pk for form in self.forms[:initial]
                            if form.cleaned_data.get('id')]
            if initial != len(expected_ids) or len(supplied_ids) != len(expected_ids) or set(supplied_ids) != expected_ids:
                raise forms.ValidationError('La liste des horaires a changé. Rechargez la page avant de réessayer.')
        periods = []
        day = 24 * 60 * 60 * 1_000_000
        week = 7 * day
        def clock(value):
            return ((value.hour * 60 + value.minute) * 60 + value.second) * 1_000_000 + value.microsecond
        for form in self.forms:
            data = form.cleaned_data
            if not data or data.get('DELETE'):
                continue
            weekday, opens, closes = data.get('weekday'), data.get('opens'), data.get('closes')
            if weekday is None or opens is None or closes is None:
                continue
            start = weekday * day + clock(opens)
            end = weekday * day + clock(closes)
            if end <= start:
                end += day
            if end > week:
                periods.extend(((start, week), (0, end - week)))
            else:
                periods.append((start, end))
        periods.sort()
        if any(current[0] < previous[1] for previous, current in zip(periods, periods[1:])):
            raise forms.ValidationError('Deux créneaux se chevauchent. Corrigez les horaires avant d’enregistrer.')


OpeningFormSet = inlineformset_factory(
    Restaurant, OpeningHour, form=OpeningHourForm, formset=OpeningHoursFormSet,
    extra=0, can_delete=True, max_num=35, validate_max=True, absolute_max=70,
)


class ClosureForm(forms.ModelForm):
    class Meta:
        model = Closure
        fields = ('date', 'reason')
        labels = {'date': 'Jour de fermeture', 'reason': 'Motif (facultatif)'}
        widgets = {'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})}

    def __init__(self, *args, restaurant, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.restaurant = restaurant

    def clean_date(self):
        from django.utils import timezone
        value = self.cleaned_data['date']
        if value < timezone.localdate():
            raise forms.ValidationError('Choisissez aujourd’hui ou une date à venir.')
        if Closure.objects.filter(restaurant=self.instance.restaurant, date=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Cette journée est déjà indiquée comme fermée.')
        return value


class OrderStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Order.STATUS)
    expected_status = forms.ChoiceField(choices=Order.STATUS)


class OnSitePaymentForm(forms.Form):
    expected_status = forms.ChoiceField(choices=Order.STATUS)
    expected_payment_status = forms.ChoiceField(choices=Order.PAYMENT)

    def clean(self):
        data = super().clean()
        allowed = {'expected_status', 'expected_payment_status', 'csrfmiddlewaretoken',
                   'return_filter', 'return_q', 'return_page'}
        if set(self.data) - allowed:
            raise forms.ValidationError('Les champs de cette opération ne sont pas acceptés.')
        return data
