from django import forms
from django.contrib import admin,messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm,UserChangeForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.html import format_html_join
from .models import User,Restaurant,OpeningHour,Closure,Category,OptionGroup,Choice,Product,Address,Favorite,Order,OrderLine,OrderHistory,Payment,StripeEvent

class STCUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model=User
        fields=('email','first_name')
class STCUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model=User
        fields='__all__'
@admin.register(User)
class STCUserAdmin(UserAdmin):
    add_form=STCUserCreationForm
    form=STCUserChangeForm
    list_display=('email','first_name','is_staff','is_active')
    ordering=('email',)
    search_fields=('email','first_name')
    fieldsets=((None,{'fields':('email','password')}),('Coordonnées',{'fields':('first_name','last_name')}),('Autorisations',{'fields':('is_active','is_staff','is_superuser','groups','user_permissions')}),('Dates',{'fields':('last_login','date_joined')}))
    add_fieldsets=((None,{'classes':('wide',),'fields':('email','first_name','password1','password2')}),)

class OpeningInline(admin.TabularInline):
    model=OpeningHour
    extra=0
class ClosureInline(admin.TabularInline):
    model=Closure
    extra=0
@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    inlines=[OpeningInline,ClosureInline]
    def has_add_permission(self,request):
        return not Restaurant.objects.exists()
    def has_delete_permission(self,request,obj=None):
        return False

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display=['name','position']
    list_editable=['position']

class ChoiceInline(admin.TabularInline):
    model=Choice
    extra=0
@admin.register(OptionGroup)
class OptionGroupAdmin(admin.ModelAdmin):
    inlines=[ChoiceInline]
    list_display=['name','minimum','maximum']
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display=['name','category','price','available','promotional','position']
    list_filter=['category','available','promotional','vegetarian']
    list_editable=['available','position']
    search_fields=['name']
    filter_horizontal=['option_groups']
    fieldsets=(('Recette',{'fields':('name','category','description','summary','price','image','photo','badge','rating','vegetarian','allergens','available','position','option_groups'),'description':'Allergènes : liste JSON, par exemple ["gluten", "lait", "œufs"]. Note : laisser vide si elle ne provient pas d’avis vérifiés.'}),('Promotion',{'fields':('promotional','promotion_source','discount_percent','promotion_starts','promotion_ends')}))

class OrderLineInline(admin.TabularInline):
    model=OrderLine
    fields=['name','quantity','unit_price','total','choices']
    readonly_fields=fields
    extra=0
    can_delete=False
    def has_add_permission(self,request,obj=None):
        return False
class HistoryInline(admin.TabularInline):
    model=OrderHistory
    fields=['status','date']
    readonly_fields=fields
    extra=0
    can_delete=False
    def has_add_permission(self,request,obj=None):
        return False

class OrderForm(forms.ModelForm):
    class Meta:
        model=Order
        fields=['status']
    def clean_status(self):
        target=self.cleaned_data['status']
        if not self.instance.pk:
            return target
        from .payments import release_checkout
        current=Order.objects.get(pk=self.instance.pk)
        try:
            current.check_transition(target)
            if target=='cancelled' and current.status=='pending_payment':
                # Close the Stripe session first: a cancelled order must no longer be payable.
                release_checkout(current)
        except ValidationError as error:
            raise forms.ValidationError(error.messages)
        return target

CUSTOMER_FIELDS=[('name','Nom'),('phone','Téléphone'),('email','E-mail'),('address','Adresse'),('postal','Code postal'),('city','Ville'),('note','Précision')]

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form=OrderForm
    list_display=['id','date','mode','customer_name','customer_phone','status','payment_status','refund','total','demo_mode']
    list_filter=['status','payment_status','mode','demo_mode','date']
    search_fields=['id','customer__name','customer__email','customer__phone']
    search_help_text='Référence, nom, e-mail ou téléphone du client.'
    date_hierarchy='date'
    readonly_fields=['id','date','user','mode','customer_details','subtotal','delivery_fee','total','payment_status','refund','demo_mode']
    fields=readonly_fields+['status']
    inlines=[OrderLineInline,HistoryInline]
    actions=['prepare','ready','complete']
    class Media:
        js=['shop/admin-orders.js']
    @admin.display(description='Client')
    def customer_name(self,obj):
        return obj.customer.get('name','')
    @admin.display(description='Téléphone')
    def customer_phone(self,obj):
        return obj.customer.get('phone','')
    @admin.display(description='Coordonnées')
    def customer_details(self,obj):
        return format_html_join('','<div><strong>{}</strong> : {}</div>',((label,obj.customer.get(key) or '—') for key,label in CUSTOMER_FIELDS))
    @admin.display(description='Remboursement à effectuer',boolean=True)
    def refund(self,obj):
        return obj.refund_required
    def has_add_permission(self,request):
        return False
    def has_delete_permission(self,request,obj=None):
        return False
    def save_model(self,request,obj,form,change):
        with transaction.atomic():
            current=Order.objects.select_for_update().get(pk=obj.pk)
            try:
                current.transition(form.cleaned_data['status'])
            except ValidationError as error:
                # The order changed between validation and save (webhook, other staff member).
                self.message_user(request,f'{current.id} : {" ".join(error.messages)}',messages.ERROR)
    def transition_orders(self,request,queryset,target):
        count=0
        for pk in queryset.values_list('pk',flat=True):
            with transaction.atomic():
                order=Order.objects.select_for_update().get(pk=pk)
                try:
                    order.transition(target)
                    count+=1
                except ValidationError as error:
                    self.message_user(request,f'{order.id} : {" ".join(error.messages)}',messages.WARNING)
        self.message_user(request,f'{count} commande(s) mise(s) à jour.')
    @admin.action(description='Passer en cuisine')
    def prepare(self,request,queryset):
        self.transition_orders(request,queryset,'preparing')
    @admin.action(description='Marquer prêtes')
    def ready(self,request,queryset):
        self.transition_orders(request,queryset,'ready')
    @admin.action(description='Terminer les commandes')
    def complete(self,request,queryset):
        self.transition_orders(request,queryset,'completed')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display=['order','session_id','created_at']
    readonly_fields=['order','session_id','payment_intent','checkout_url','created_at']
    def has_add_permission(self,request):
        return False
    def has_delete_permission(self,request,obj=None):
        return False
@admin.register(StripeEvent)
class EventAdmin(admin.ModelAdmin):
    list_display=['id','event_type','date']
    readonly_fields=['id','event_type','date']
    def has_add_permission(self,request):
        return False
    def has_delete_permission(self,request,obj=None):
        return False
@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display=['label','user','city']
    search_fields=['user__email']
