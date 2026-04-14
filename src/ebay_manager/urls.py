from django.urls import path
from . import views

app_name = 'ebay_manager'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('listings/', views.listings, name='listings'),
    path('listings/create/', views.listing_create, name='listing_create'),
    path('listings/<int:pk>/', views.listing_detail, name='listing_detail'),
    path('listings/<int:pk>/edit/', views.listing_edit, name='listing_edit'),
    path('listings/<int:pk>/preview/', views.listing_preview, name='listing_preview'),
    path('listings/<int:pk>/publish-draft/', views.publish_draft, name='publish_draft'),
    path('listings/<int:pk>/publish-active/', views.publish_active, name='publish_active'),
    path('listings/<int:pk>/delete/', views.listing_delete, name='listing_delete'),
    path('orders/', views.orders, name='orders'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('analytics/', views.analytics, name='analytics'),
    path('settings/', views.settings_view, name='settings'),
    path('sync/listings/', views.sync_listings, name='sync_listings'),
    path('sync/orders/', views.sync_orders, name='sync_orders'),
    path('sync/all/', views.sync_all, name='sync_all'),
    path('gap-report/', views.gap_report, name='gap_report'),
    path('listings/create-multi/', views.multi_variant_create, name='multi_variant_create'),
    path('listings/load-description/', views.load_description_html, name='load_description_html'),
]
