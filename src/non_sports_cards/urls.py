# file: src/non_sports_cards/urls.py

from django.urls import path
from . import views

app_name = 'non_sports_cards'

urlpatterns = [
    path('', views.home, name='non_sports_cards_home'),
    path('list/', views.list_cards, name='list_cards'),
    path('<int:pk>/', views.card_detail, name='card_detail'),
    # Star Wars hierarchical navigation
    path('star-wars/', views.sw_hub, name='sw_hub'),
    path('star-wars/<str:movie>/', views.sw_movie, name='sw_movie'),
    path('star-wars/<str:movie>/series-<int:series>/', views.sw_series, name='sw_series'),
    path('star-wars/<str:movie>/series-<int:series>/<str:variant>/', views.sw_variant, name='sw_variant'),
    # R2 Gallery — auto-generated from R2 bucket images
    path('gallery/<str:product_type>/', views.r2_gallery, name='r2_gallery_root'),
    path('gallery/<str:product_type>/<path:path>/', views.r2_gallery, name='r2_gallery'),
    path('gallery/<str:product_type>/<path:path>/detail/', views.r2_gallery_detail, name='r2_gallery_detail'),
]

