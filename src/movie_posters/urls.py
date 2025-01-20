# src/movie_posters/urls.py

from django.urls import path
from . import views

app_name = 'movie_posters'

urlpatterns = [
    path('', views.home, name='home'),  # Full page
    path('list/', views.list_posters, name='list_posters'),  # HTMX partial
]

