# src/movie_posters/views.py

from django.shortcuts import render
from .models import MoviePosters

def home(request):
    return render(request, 'movie_posters/home.html')

def list_posters(request):
    """Returns the movie posters list via HTMX."""
    movie_posters = MoviePosters.objects.all()
    return render(request, 'movie_posters/partials/movie_posters_list_partial.html', {'movie_posters': movie_posters})
