from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include,path
from shop import views
from shop.payments import PaymentView,stripe_webhook
admin.site.site_header='STC · Administration'
admin.site.site_title='STC'
admin.site.index_title='Votre restaurant'
urlpatterns=[
    path('crm/',include('shop.crm_urls')),
    path('admin/',admin.site.urls),
    path('api/health/',views.HealthView.as_view()),
    path('api/restaurant/',views.RestaurantView.as_view()),
    path('api/products/',views.ProductsView.as_view()),
    path('api/categories/',views.CategoriesView.as_view()),
    path('api/auth/csrf/',views.CsrfView.as_view()),
    path('api/auth/me/',views.MeView.as_view()),
    path('api/auth/capabilities/',views.AuthCapabilitiesView.as_view()),
    path('api/auth/register/',views.RegisterView.as_view()),
    path('api/auth/login/',views.LoginView.as_view()),
    path('api/auth/logout/',views.LogoutView.as_view()),
    path('api/auth/password-reset/',views.ResetView.as_view()),
    path('api/auth/password-reset-confirm/',views.ResetConfirmView.as_view()),
    path('api/auth/delete-account/',views.DeleteAccountView.as_view()),
    path('api/addresses/',views.AddressesView.as_view()),
    path('api/addresses/<int:pk>/',views.AddressView.as_view()),
    path('api/favorites/',views.FavoritesView.as_view()),
    path('api/orders/',views.OrdersView.as_view()),
    path('api/orders/<str:pk>/',views.OrderView.as_view()),
    path('api/orders/<str:pk>/payment/',PaymentView.as_view()),
    path('api/payments/webhook/',stripe_webhook),
]
if settings.DEBUG:
    urlpatterns+=static(settings.MEDIA_URL,document_root=settings.MEDIA_ROOT)
