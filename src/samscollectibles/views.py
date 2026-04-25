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
    """Public contact form with layered anti-spam (honeypot, rate-limit,
    Turnstile, content filter). See ``samscollectibles.spam_filters``.
    """
    import logging
    from samscollectibles.spam_filters import (
        get_client_ip,
        is_rate_limited,
        is_spam_content,
        verify_turnstile,
    )
    logger = logging.getLogger(__name__)

    turnstile_site_key = getattr(settings, 'TURNSTILE_SITE_KEY', '')
    ctx = {'turnstile_site_key': turnstile_site_key}

    if request.method == 'POST':
        ip = get_client_ip(request)

        # Layer 1 — honeypot. Bots auto-fill the hidden "website" field.
        if request.POST.get('website', ''):
            logger.warning('Contact honeypot tripped from IP %s', ip)
            messages.success(request, 'Your message has been sent successfully!')
            return redirect('contact')

        # Layer 2 — rate limit (3 / 5 min / IP)
        if is_rate_limited(ip):
            logger.warning('Contact rate limit hit for IP %s', ip)
            messages.error(request, "You've sent too many messages. Please try again in a few minutes.")
            return redirect('contact')

        # Layer 3 — Cloudflare Turnstile (skipped silently if not configured)
        token = request.POST.get('cf-turnstile-response', '')
        if not verify_turnstile(token, ip):
            logger.warning('Contact Turnstile verification failed for IP %s', ip)
            messages.error(request, 'Verification failed. Please try again.')
            return redirect('contact')

        name = (request.POST.get('name') or '').strip()
        email = (request.POST.get('email') or '').strip()
        message = (request.POST.get('message') or '').strip()

        # Layer 4 — content filter, silent drop on match
        if is_spam_content(name, '', message):
            logger.warning('Contact content filter matched from IP %s (name=%r)', ip, name)
            messages.success(request, 'Your message has been sent successfully!')
            return redirect('contact')

        if name and email and message:
            from django.core.mail import EmailMessage
            msg = EmailMessage(
                subject=f'Contact Form Submission from {name}',
                body=f'Name: {name}\nEmail: {email}\n\nMessage:\n{message}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.DEFAULT_FROM_EMAIL],
                reply_to=[email],
            )
            msg.send()

        messages.success(request, 'Your message has been sent successfully!')
        return redirect('contact')

    return render(request, 'contact.html', ctx)


def about(request):
    return render(request, 'about.html')
