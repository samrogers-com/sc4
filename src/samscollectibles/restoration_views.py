# src/samscollectibles/restoration_views.py
"""
Private restoration dashboard — only visible to staff/authorized users.
Not accessible to the public.
"""

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce

from non_sports_cards.models import NonSportsCards
from movie_posters.models import MoviePosters
from comic_books.models import StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic


def is_restoration_user(user):
    """Check if user has access to restoration dashboard.
    Staff users or users in the 'restoration' group.
    """
    return user.is_staff or user.groups.filter(name='restoration').exists()


@login_required
@user_passes_test(is_restoration_user)
def restoration_dashboard(request):
    """Private dashboard for managing restoration priorities."""

    filter_status = request.GET.get('status', '')
    filter_type = request.GET.get('type', '')

    # Collect items from all models
    items = []

    # Posters
    if filter_type in ('', 'posters'):
        poster_qs = MoviePosters.objects.exclude(restoration_status='none')
        if filter_status:
            poster_qs = poster_qs.filter(restoration_status=filter_status)
        for p in poster_qs:
            p.source = 'Poster'
            p.roi = _calc_roi(p)
            items.append(p)

    # Comics
    if filter_type in ('', 'comics'):
        for Model in [StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic]:
            comic_qs = Model.objects.exclude(restoration_status='none')
            if filter_status:
                comic_qs = comic_qs.filter(restoration_status=filter_status)
            for c in comic_qs:
                c.source = 'Comic'
                c.roi = _calc_roi(c)
                items.append(c)

    # Trading cards
    if filter_type in ('', 'cards'):
        card_qs = NonSportsCards.objects.exclude(restoration_status='none')
        if filter_status:
            card_qs = card_qs.filter(restoration_status=filter_status)
        for c in card_qs:
            c.source = 'Card'
            c.roi = _calc_roi(c)
            items.append(c)

    # Sort by priority (1=highest), then status
    status_order = {'recommended': 0, 'in_progress': 1, 'completed': 2, 'none': 3}
    items.sort(key=lambda x: (
        x.restoration_priority or 99,
        status_order.get(x.restoration_status, 99),
    ))

    # Calculate summary stats
    all_items = _get_all_restoration_items()
    stats = {
        'recommended': sum(1 for i in all_items if i.restoration_status == 'recommended'),
        'in_progress': sum(1 for i in all_items if i.restoration_status == 'in_progress'),
        'completed': sum(1 for i in all_items if i.restoration_status == 'completed'),
        'total_cost': sum(float(i.restoration_cost or 0) for i in all_items if i.restoration_status in ('recommended', 'in_progress')),
        'total_value_gain': sum(
            float(i.post_restoration_value or 0) - float(i.pre_restoration_value or 0)
            for i in all_items
            if i.post_restoration_value and i.pre_restoration_value
        ),
    }

    return render(request, 'restoration/dashboard.html', {
        'items': items,
        'stats': stats,
        'filter_status': filter_status,
        'filter_type': filter_type,
    })


def _calc_roi(item):
    """Calculate ROI percentage for a restoration item."""
    cost = float(item.restoration_cost or 0)
    pre_val = float(item.pre_restoration_value or 0)
    post_val = float(item.post_restoration_value or 0)
    if cost > 0 and pre_val > 0:
        gain = post_val - pre_val
        return round((gain / cost) * 100)
    return None


def _get_all_restoration_items():
    """Get all items with any restoration status set."""
    items = []
    items.extend(MoviePosters.objects.exclude(restoration_status='none'))
    items.extend(StarWarsMarvelComic.objects.exclude(restoration_status='none'))
    items.extend(StarWarsDarkHorseComic.objects.exclude(restoration_status='none'))
    items.extend(StarTrekDcComic.objects.exclude(restoration_status='none'))
    items.extend(NonSportsCards.objects.exclude(restoration_status='none'))
    return items
