from django.urls import path
from . import crm_views as views

app_name = 'crm'
urlpatterns = [
    path('connexion/', views.login_view, name='login'),
    path('deconnexion/', views.logout_view, name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('accueil-fragment/', views.dashboard_fragment, name='dashboard_fragment'),
    path('commandes/', views.orders, name='orders'),
    path('commandes/fragment/', views.orders_fragment, name='orders_fragment'),
    path('commandes/<str:pk>/statut/', views.order_status, name='order_status'),
    path('commandes/<str:pk>/encaissement/', views.order_collect, name='order_collect'),
    path('commandes/<str:pk>/remboursement/', views.order_refund, name='order_refund'),
    path('carte/', views.menu, name='menu'),
    path('carte/ajouter/', views.product_add, name='product_add'),
    path('carte/<int:pk>/modifier/', views.product_edit, name='product_edit'),
    path('carte/<int:pk>/disponibilite/', views.product_availability, name='product_availability'),
    path('restaurant/', views.restaurant, name='restaurant'),
    path('restaurant/fermetures/ajouter/', views.closure_add, name='closure_add'),
    path('restaurant/fermetures/<int:pk>/supprimer/', views.closure_delete, name='closure_delete'),
]
