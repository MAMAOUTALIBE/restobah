from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from rest_framework import serializers
from .models import Address

phone_validator = RegexValidator(r'^\+?[0-9 ().-]{9,24}$', 'Saisissez un numéro de téléphone valide.')
postal_validator = RegexValidator(r'^\d{5}$', 'Le code postal doit contenir cinq chiffres.')

class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({'non_field_errors': ['Un objet JSON est attendu.']})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: 'Ce champ n’est pas accepté.' for key in unknown})
        return super().to_internal_value(data)

class CustomerSerializer(StrictSerializer):
    name = serializers.CharField(max_length=100,min_length=2)
    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=25,validators=[phone_validator])
    address = serializers.CharField(max_length=200,required=False,allow_blank=True,default='')
    postal = serializers.CharField(max_length=5,required=False,allow_blank=True,default='')
    city = serializers.CharField(max_length=100,required=False,allow_blank=True,default='')
    note = serializers.CharField(max_length=1000,required=False,allow_blank=True,default='')
    def validate_phone(self,value):
        digits = ''.join(c for c in value if c.isdigit())
        if not 10 <= len(digits) <= 15:
            raise serializers.ValidationError('Le téléphone doit contenir entre 10 et 15 chiffres.')
        return value

class ItemSerializer(StrictSerializer):
    productId = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1,max_value=20)
    choices = serializers.ListField(child=serializers.CharField(max_length=100),max_length=30)
    def to_internal_value(self,data):
        if not isinstance(data,dict) or type(data.get('quantity')) is not int or type(data.get('productId')) is not int:
            raise serializers.ValidationError('La quantité et le produit doivent être des entiers.')
        return super().to_internal_value(data)
    def validate(self,data):
        if len(data['choices']) != len(set(data['choices'])):
            raise serializers.ValidationError('Une option ne peut pas être sélectionnée deux fois.')
        return data

class OrderInputSerializer(StrictSerializer):
    mode = serializers.ChoiceField(choices=['À emporter','Livraison'])
    items = ItemSerializer(many=True,allow_empty=False,max_length=50)
    customer = CustomerSerializer()
    paymentMethod = serializers.ChoiceField(choices=['simulation','stripe','on_site'])
    def validate(self,data):
        if data['mode'] == 'Livraison':
            customer = data['customer']
            if any(not customer.get(key,'').strip() for key in ['address','postal','city']):
                raise serializers.ValidationError('L’adresse complète est obligatoire pour la livraison.')
            postal_validator(customer['postal'])
        return data

class AddressSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(validators=[phone_validator],max_length=25)
    postal = serializers.CharField(validators=[postal_validator],max_length=5)
    class Meta:
        model = Address
        fields = ['id','label','name','phone','address','postal','city']
        read_only_fields = ['id']
    def validate_phone(self,value):
        digits = ''.join(c for c in value if c.isdigit())
        if not 10 <= len(digits) <= 15:
            raise serializers.ValidationError('Le téléphone doit contenir entre 10 et 15 chiffres.')
        return value
    def validate(self,data):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError('Champs non acceptés.')
        return data

class RegisterSerializer(StrictSerializer):
    name = serializers.CharField(max_length=100,min_length=2)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128,write_only=True,trim_whitespace=False)
    def validate_email(self,value):
        value = value.strip().lower()
        if get_user_model().objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Cette adresse est déjà utilisée.')
        return value

class ProfileSerializer(StrictSerializer):
    name = serializers.CharField(max_length=100, min_length=2)
    phone = serializers.CharField(max_length=24, allow_blank=True, validators=[phone_validator])

    def validate_phone(self, value):
        if value and not 10 <= sum(character.isdigit() for character in value) <= 15:
            raise serializers.ValidationError('Le téléphone doit contenir entre 10 et 15 chiffres.')
        return value

class LoginSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128,trim_whitespace=False)

class ResetSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)

class ResetConfirmSerializer(StrictSerializer):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=256)
    password = serializers.CharField(max_length=128,trim_whitespace=False)

class DeleteAccountSerializer(StrictSerializer):
    password = serializers.CharField(max_length=128,trim_whitespace=False)
