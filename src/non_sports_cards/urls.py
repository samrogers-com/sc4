# file: src/non_sports_cards/urls.py

from django.urls import path
from . import views

app_name = 'non_sports_cards'

urlpatterns = [
    path('', views.home, name='non_sports_cards_home'),   # Home page view
    path('list/', views.list_cards, name='list_cards'),    # List view
]

