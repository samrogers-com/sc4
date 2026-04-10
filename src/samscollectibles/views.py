# file: src/samscollectibles/views.py

from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login

from comic_books.models import StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic
from non_sports_cards.models import NonSportsCards
from movie_posters.models import MoviePosters


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def home(request):
    context = {
        'ns_card_count': NonSportsCards.objects.count(),
        'comic_count': (
            StarWarsMarvelComic.objects.count()
            + StarWarsDarkHorseComic.objects.count()
            + StarTrekDcComic.objects.count()
        ),
        'poster_count': MoviePosters.objects.count(),
    }
    return render(request, 'home.html', context)


def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')

        send_mail(
            f"Contact Form Submission from {name}",
            f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}",
            settings.DEFAULT_FROM_EMAIL,
            [settings.DEFAULT_FROM_EMAIL],
        )

        messages.success(request, 'Your message has been sent successfully!')
        return redirect('contact')

    return render(request, 'contact.html')


def about(request):
    return render(request, 'about.html')
