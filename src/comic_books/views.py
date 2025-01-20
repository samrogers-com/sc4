# file: src/comic_books/views.py

from django.shortcuts import render
from .models import StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic

# View for the Comic Books home page
def comicbooks_home(request):
   sw_comics = StarWarsMarvelComic.objects.all()
   return render(request, 'comic_books/home.html', {'sw_comics': sw_comics})

# View for Star Wars Marvel comic books
def starwars_marvel(request):
    starwars_marvel = StarWarsMarvelComic.objects.all().order_by('issue_number')
    
    # Add the S3 image file link for each comic book
    for comic in starwars_marvel:
      # Zero-pad the issue number to 3 digits
      issue_number_padded = f"{comic.issue_number:03}"
      comic.sw_s3image_file = f"StarWarsMarvel-{issue_number_padded}.jpg"
      comic.sw_s3image_link = f"https://samscollectibles.s3.us-west-1.amazonaws.com/ComicBooks/ebay/SW-Marvel/{comic.sw_s3image_file}"
      
    return render(request, 'comic_books/starwars_marvel.html', {'starwars_marvel': starwars_marvel})

# View for Star Wars Dark Horse comic books
def starwars_dark_horse(request):
   starwars_dark_horse = StarWarsDarkHorseComic.objects.all().order_by('issue_number')
   return render(request, 'comic_books/starwars_dark_horse.html', {'starwars_dark_horse': starwars_dark_horse})

# View for Star Trek DC comic books
def startrek_dc(request):
   startrek_dc = StarTrekDcComic.objects.all().order_by('issue_number')
   return render(request, 'comic_books/startrek_dc.html', {'startrek_dc': startrek_dc})

