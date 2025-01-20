# src/comic_books/urls.py

from django.urls import path
from . import views

app_name = 'comic_books'

urlpatterns = [
    path('', views.comicbooks_home, name='comicbooks_home'),
    path('starwars_marvel/', views.starwars_marvel, name='starwars_marvel'),
    path('starwars_dark_horse/', views.starwars_dark_horse, name='starwars_dark_horse'),  # Correct name here
    path('startrek_dc/', views.startrek_dc, name='startrek_dc'),
]
