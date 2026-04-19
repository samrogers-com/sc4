from django.urls import path

from . import views

app_name = 'social_manager'

urlpatterns = [
    path('', views.DraftListView.as_view(), name='drafts'),
    path('generate/', views.GenerateDraftView.as_view(), name='generate'),
    path('drafts/<int:pk>/', views.DraftReviewView.as_view(), name='review'),
    path(
        'drafts/<int:pk>/publish/<str:platform>/',
        views.PublishView.as_view(),
        name='publish',
    ),
]
