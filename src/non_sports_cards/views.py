# src/non_sports_cards/views.py

import logging
from django.shortcuts import render
from .models import NonSportsCards
from .filters import NonSportsCardsFilter

logger = logging.getLogger(__name__)


def home(request):
    return render(request, 'non_sports_cards/home.html')


def list_cards(request):
    non_sports_cards_filter = NonSportsCardsFilter(request.GET, queryset=NonSportsCards.objects.all())

    if request.GET and non_sports_cards_filter.is_valid():
        queryset = non_sports_cards_filter.qs
    else:
        queryset = NonSportsCards.objects.all()

    context = {
        'filter': non_sports_cards_filter,
        'cards': queryset,
        'title': 'Non-Sports Cards',
    }

    # HTMX partial or full page
    if request.htmx:
        return render(request, 'non_sports_cards/partials/non_sports_cards_list_partial.html', context)

    return render(request, 'non_sports_cards/home.html', context)
