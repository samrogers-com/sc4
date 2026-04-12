# src/samscollectibles/restoration_views.py
"""
Private restoration dashboard — only visible to staff/authorized users.
"""

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.conf import settings

from non_sports_cards.models import NonSportsCards
from movie_posters.models import MoviePosters
from comic_books.models import StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic


IMAGE_BASE_URL = getattr(settings, 'IMAGE_BASE_URL', 'https://media.samscollectibles.net/')

# Map poster title fragments to R2 thumbnail paths
POSTER_THUMBNAIL_MAP = {
    'Style D%Copy 1': 'posters/star-wars/anh/style-d-copy-1/front.jpg',
    'Style D%Copy 2': 'posters/star-wars/anh/style-d-copy-2/front.jpg',
    'Advance Teaser%Coming': 'posters/star-wars/anh/style-a-advance-teaser/front.jpg',
    'Style B Teaser': 'posters/star-wars/anh/style-b-teaser/front.jpg',
    'Style C%Chantrell%Copy 1': 'posters/star-wars/anh/style-c-copy-1/front.jpg',
    'Style C%Chantrell%Copy 2': 'posters/star-wars/anh/style-c-copy-2/front.jpg',
    'Style C%Chantrell': 'posters/star-wars/anh/style-c-copy-1/front.jpg',
    'Style A%Copy 1': 'posters/star-wars/anh/style-a-copy-1/front.jpg',
    'Style A%Copy 2': 'posters/star-wars/anh/style-a-copy-2/front.jpg',
    'Style A%Copy 3': 'posters/star-wars/anh/style-a-copy-3/front.jpg',
    'Style A%Copy 4': 'posters/star-wars/anh/style-a-copy-4/front.jpg',
    'Its Back': 'posters/star-wars/anh/its-back-1979/front.jpg',
    'First Ten Years': 'posters/star-wars/anh/first-ten-years-signed-struzan/front.jpg',
    'French': 'posters/star-wars/anh/french-la-guerre-des-etoiles/front.jpg',
    'Soundtrack Banner': 'posters/star-wars/anh/style-a-soundtrack-banner/front.jpg',
    'Advance%GWTW%Copy 1': 'posters/star-wars/esb/advance-gwtw-copy-1/front.jpg',
    'Advance%GWTW%Copy 2': 'posters/star-wars/esb/advance-gwtw-copy-2/front.jpg',
    'GWTW%Copy 1': 'posters/star-wars/esb/style-a-gwtw-copy-1/front.jpg',
    'GWTW%Copy 2': 'posters/star-wars/esb/style-a-gwtw-copy-2/front.jpg',
    'GWTW%Copy 3': 'posters/star-wars/esb/style-a-gwtw-copy-3/front.jpg',
    'Style B%Tom Jung%1980': 'posters/star-wars/esb/style-b-copy-1/front.jpg',
    'Re-release%1982': 'posters/star-wars/esb/re-release-1982/front.jpg',
    'ROTJ%Style A': 'posters/star-wars/rotj/style-a/front.jpg',
    'ROTJ%Style B%Copy 1': 'posters/star-wars/rotj/style-b-copy-1/front.jpg',
    'ROTJ%Style B%Copy 2': 'posters/star-wars/rotj/style-b-copy-2/front.jpg',
    'Landscape': 'posters/star-wars/rotj/landscape-variant/front.jpg',
    'Borg City': 'posters/star-trek/new-borg-city-le-725-of-1701/front.jpg',
    'Way of the Warrior': 'posters/star-trek/ds9-way-of-the-warrior/front.jpg',
}


def _get_poster_thumbnail(title):
    """Find the R2 thumbnail URL for a poster by matching title fragments."""
    title_lower = title.lower()
    for pattern, path in POSTER_THUMBNAIL_MAP.items():
        parts = pattern.lower().split('%')
        if all(part in title_lower for part in parts):
            return f"{IMAGE_BASE_URL}{path}"
    return None


def _get_comic_cover_url(issue_number):
    """Get the R2 cover URL for a SW Marvel comic."""
    return f"{IMAGE_BASE_URL}comic-books/star-wars-marvel/StarWarsMarvel-{issue_number:03d}.webp"


def is_restoration_user(user):
    return user.is_staff or user.groups.filter(name='restoration').exists()


def _calc_roi(item):
    cost = float(item.restoration_cost or 0)
    pre_val = float(item.pre_restoration_value or 0)
    post_val = float(item.post_restoration_value or 0)
    if cost > 0 and pre_val > 0:
        gain = post_val - pre_val
        return round((gain / cost) * 100)
    return None


@login_required
@user_passes_test(is_restoration_user)
def restoration_dashboard(request):
    # Posters
    poster_items = []
    for p in MoviePosters.objects.exclude(restoration_status='none').order_by('restoration_priority', 'title'):
        p.roi = _calc_roi(p)
        p.thumbnail_url = _get_poster_thumbnail(p.title)
        poster_items.append(p)

    # Comics
    comic_items = []
    for Model in [StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic]:
        for c in Model.objects.exclude(restoration_status='none').order_by('restoration_priority', 'issue_number'):
            c.roi = _calc_roi(c)
            c.cover_url = _get_comic_cover_url(c.issue_number) if hasattr(c, 'issue_number') else None
            comic_items.append(c)

    # Trading cards
    card_items = []
    for c in NonSportsCards.objects.exclude(restoration_status='none').order_by('restoration_priority', 'title'):
        c.roi = _calc_roi(c)
        card_items.append(c)

    # Add admin edit URLs to each item
    for item in poster_items:
        item.admin_url = f"/admin/movie_posters/movieposters/{item.pk}/change/"
    for item in comic_items:
        model_name = item.__class__.__name__.lower()
        item.admin_url = f"/admin/comic_books/{model_name}/{item.pk}/change/"
    for item in card_items:
        item.admin_url = f"/admin/non_sports_cards/nonsportscards/{item.pk}/change/"

    # Section totals
    def _section_totals(items):
        return {
            'cost': sum(float(i.restoration_cost or 0) for i in items),
            'before': sum(float(i.pre_restoration_value or 0) for i in items),
            'after': sum(float(i.post_restoration_value or 0) for i in items),
        }

    poster_totals = _section_totals(poster_items)
    comic_totals = _section_totals(comic_items)
    card_totals = _section_totals(card_items)

    # Stats
    all_items = poster_items + comic_items + card_items
    total_before = sum(float(i.pre_restoration_value or 0) for i in all_items)
    total_after = sum(float(i.post_restoration_value or 0) for i in all_items)
    stats = {
        'recommended': sum(1 for i in all_items if i.restoration_status == 'recommended'),
        'in_progress': sum(1 for i in all_items if i.restoration_status == 'in_progress'),
        'completed': sum(1 for i in all_items if i.restoration_status == 'completed'),
        'total_cost': sum(float(i.restoration_cost or 0) for i in all_items if i.restoration_status in ('recommended', 'in_progress')),
        'total_before': total_before,
        'total_after': total_after,
        'total_value_gain': total_after - total_before,
    }

    return render(request, 'restoration/dashboard.html', {
        'poster_items': poster_items,
        'poster_totals': poster_totals,
        'comic_items': comic_items,
        'comic_totals': comic_totals,
        'card_items': card_items,
        'card_totals': card_totals,
        'stats': stats,
    })
