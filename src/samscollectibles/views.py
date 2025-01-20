# file: src/samscollectibles/views.py

import random
from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.contrib import messages
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required

from comic_books.models import StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic  # Import all the subclasses
from non_sports_cards.models import NonSportsCards
from movie_posters.models import MoviePosters

from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Log in the user after registration
            return redirect('home')  # Redirect to home page or wherever you want after login
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

def home(request):
    # Get 2 random comic books from each subclass
    # all_comic_books = list(StarWarsMarvelComic.objects.all()) + \
    #                   list(StarWarsDarkHorseComic.objects.all()) + \
    #                   list(StarTrekDcComic.objects.all())

    # Use later Randomly sample 2 starwars_marvel_comic_books from the combined list
    starwars_marvel_comic_books = list(StarWarsMarvelComic.objects.all())
    random_starwars_marvel_comic_books = random.sample(starwars_marvel_comic_books, min(len(starwars_marvel_comic_books), 2))

    # Use later Randomly sample 2 starwars_darhorse_comic_books from the combined list
    starwars_darhorse_comic_books = list(StarWarsDarkHorseComic.objects.all())
    if starwars_darhorse_comic_books:
        random_starwars_darkhorse_comic_books = random.sample(starwars_darhorse_comic_books, min(len(starwars_darhorse_comic_books), 2))
    else:
        random_starwars_darkhorse_comic_books = [] # Empty list if there are no comic books

    # Use later Randomly sample 2 startrek_dc_comic_books from the combined list
    startrek_dc_comic_books = list(StarTrekDcComic.objects.all())
    if startrek_dc_comic_books:
        random_startrek_dc_comic_books = random.sample(startrek_dc_comic_books, min(len(startrek_dc_comic_books), 2))
    else:
        random_startrek_dc_comic_books = [] # Empty list if there are no comic books
    
    # Get 2 random comic books from each subclass
    all_comic_books = list(StarWarsMarvelComic.objects.all()) + \
                      list(StarWarsDarkHorseComic.objects.all()) + \
                      list(StarTrekDcComic.objects.all())
    
    # For now Randomly sample 2 comic books from the combined list
    random_comic_books = random.sample(all_comic_books, min(len(all_comic_books), 2))
    
    # Add the S3 image file link for each comic book
    for comic in random_comic_books:
      # Zero-pad the issue number to 3 digits
      issue_number_padded = f"{comic.issue_number:03}"
      comic.sw_s3image_file = f"StarWarsMarvel-{issue_number_padded}.jpg"
      comic.sw_s3image_link = f"https://samscollectibles.s3.us-west-1.amazonaws.com/ComicBooks/ebay/SW-Marvel/{comic.sw_s3image_file}"

    # Get 2 random non-sports cards
    non_sports_cards = list(NonSportsCards.objects.all())
    random_non_sports_cards = random.sample(non_sports_cards, min(len(non_sports_cards), 2))

    # Get 2 random movie posters
    movie_posters = list(MoviePosters.objects.all())
    random_movie_posters = random.sample(movie_posters, min(len(movie_posters), 2))

    # Pass data to the template
    context = {
        'welcome_message': "Welcome to Sam's Collectibles! Here are some highlights from our collection!",
        'comic_books': random_comic_books,
        'non_sports_cards': random_non_sports_cards,
        'movie_posters': random_movie_posters,
    }
    return render(request, 'home.html', context)

def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')

        # Prepare the email content
        subject = f"Contact Form Submission from {name}"
        body = f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}"
        
        # Send the email
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            ['sams.collectibles2@gmail.com'],
        )
        
        messages.success(request, 'Your message has been sent successfully!')
        return redirect('contact')
    
    return render(request, 'contact.html')


# About view
def about(request):
    return render(request, 'about.html')

