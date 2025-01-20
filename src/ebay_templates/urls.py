# file: src/ebay_templates/urls.py

from django.urls import path
from . import views

app_name = 'ebay_templates'

urlpatterns = [
    # Home Pages for Different Categories
    path('', views.ebay_templates_home, name='home'),
    path('non_sports_cards/', views.non_sports_cards_home, name='non_sports_cards_home'),
    path('comic_books/', views.comic_home, name='comic_home'),
    path('movie_posters/', views.movie_posters_home, name='movie_posters_home'),
    
    # Template Management
    path('create/<str:template_type>/', views.create_template, name='create_template'),
    path('list/', views.list_user_templates, name='list_templates'),
    path('update-s3-path/<int:item_id>/', views.update_s3_path, name='update_s3_path'),
    path('download/<int:template_id>/', views.download_template, name='download_template'),
    
    # Template Actions
    path('detail/<int:template_id>/', views.template_detail, name='template_detail'),
    path('delete/<int:template_id>/', views.template_delete, name='template_delete'),
]

