# file: src/comic_books/views.py

from django.shortcuts import render
from .models import StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic


def comicbooks_home(request):
    return render(request, 'comic_books/home.html')


def starwars_marvel(request):
    starwars_marvel = StarWarsMarvelComic.objects.all().order_by('issue_number')
    return render(request, 'comic_books/starwars_marvel.html', {'starwars_marvel': starwars_marvel})


def starwars_marvel_detail(request, issue_number):
    from django.shortcuts import get_object_or_404
    comic = get_object_or_404(StarWarsMarvelComic, issue_number=issue_number)
    return render(request, 'comic_books/starwars_marvel_detail.html', {'comic': comic})


def starwars_dark_horse(request):
    starwars_dark_horse = StarWarsDarkHorseComic.objects.all().order_by('issue_number')
    return render(request, 'comic_books/starwars_dark_horse.html', {'starwars_dark_horse': starwars_dark_horse})


def startrek_dc(request):
    startrek_dc = StarTrekDcComic.objects.all().order_by('issue_number')
    return render(request, 'comic_books/startrek_dc.html', {'startrek_dc': startrek_dc})
