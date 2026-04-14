from django.urls import path
from . import views

app_name = 'ebay_manager'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('listings/', views.listings, name='listings'),
    path('listings/create/', views.listing_create, name='listing_create'),
    path('listings/<int:pk>/', views.listing_detail, name='listing_detail'),
    path('orders/', views.orders, name='orders'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('analytics/', views.analytics, name='analytics'),
    path('settings/', views.settings_view, name='settings'),
    path('sync/listings/', views.sync_listings, name='sync_listings'),
    path('sync/orders/', views.sync_orders, name='sync_orders'),
    path('sync/all/', views.sync_all, name='sync_all'),
]
