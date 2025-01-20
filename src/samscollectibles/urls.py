# file: src/samscollectibles/urls.py

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView, LogoutView
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),

    # Authentication URLs
    path('accounts/login/', LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', LogoutView.as_view(next_page='home'), name='logout'),
    path('accounts/register/', views.register, name='register'),  # Custom registration view

    # Other app URLs
    path('comic_books/', include('comic_books.urls', namespace='comic_books')),
    path('ebay_templates/', include('ebay_templates.urls', namespace='ebay_templates')),
    path('non_sports_cards/', include('non_sports_cards.urls', namespace='non_sports_cards')),
    path('movie_posters/', include('movie_posters.urls', namespace='movie_posters')),
]