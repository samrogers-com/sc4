# src/non_sports_cards/views.py

from django.shortcuts import render, get_object_or_404
from .models import NonSportsCards
from .filters import NonSportsCardsFilter


def home(request):
    # Get category counts for the page
    from django.db.models import Count
    categories = (
        NonSportsCards.objects
        .values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    total = NonSportsCards.objects.count()
    return render(request, 'non_sports_cards/home.html', {
        'categories': categories,
        'total': total,
    })


def list_cards(request):
    queryset = NonSportsCards.objects.all().order_by('title')

    # Category filter from URL param
    category = request.GET.get('category', '')
    if category:
        queryset = queryset.filter(category=category)

    # Text search
    search = request.GET.get('q', '')
    if search:
        queryset = queryset.filter(title__icontains=search)

    # Get all categories for filter buttons
    from django.db.models import Count
    categories = (
        NonSportsCards.objects
        .values('category')
        .annotate(count=Count('id'))
        .order_by('category')
    )

    context = {
        'cards': queryset,
        'categories': categories,
        'active_category': category,
        'search_query': search,
        'result_count': queryset.count(),
    }

    if request.htmx:
        return render(request, 'non_sports_cards/partials/non_sports_cards_list_partial.html', context)

    return render(request, 'non_sports_cards/home.html', context)


def card_detail(request, pk):
    card = get_object_or_404(NonSportsCards, pk=pk)
    images = card.images.all() if hasattr(card, 'images') else []
    return render(request, 'non_sports_cards/card_detail.html', {
        'card': card,
        'images': images,
    })


# =============================================================================
# Star Wars Hierarchical Views
# =============================================================================

SW_MOVIES = {
    'anh': {
        'title': 'Star Wars: A New Hope',
        'parent_set': 'SW 77 ANH',
        'year': '1977',
        'total_series': 5,
        'series_colors': {
            1: {'name': 'Blue', 'bg': 'linear-gradient(135deg, #2563eb, #1d4ed8)'},
            2: {'name': 'Red', 'bg': 'linear-gradient(135deg, #dc2626, #b91c1c)'},
            3: {'name': 'Yellow', 'bg': 'linear-gradient(135deg, #ca8a04, #a16207)'},
            4: {'name': 'Green', 'bg': 'linear-gradient(135deg, #16a34a, #15803d)'},
            5: {'name': 'Orange', 'bg': 'linear-gradient(135deg, #ea580c, #c2410c)'},
        },
    },
    'esb': {
        'title': 'Star Wars: Empire Strikes Back',
        'parent_set': 'SW 80 ESB',
        'year': '1980',
        'total_series': 3,
        'series_colors': {
            1: {'name': 'Silver/Red', 'bg': 'linear-gradient(135deg, #9ca3af, #dc2626)'},
            2: {'name': 'Silver/Blue', 'bg': 'linear-gradient(135deg, #9ca3af, #2563eb)'},
            3: {'name': 'Yellow/Green', 'bg': 'linear-gradient(135deg, #ca8a04, #16a34a)'},
        },
    },
    'rotj': {
        'title': 'Star Wars: Return of the Jedi',
        'parent_set': 'SW 83 ROTJ',
        'year': '1983',
        'total_series': 2,
        'series_colors': {
            1: {'name': 'Red', 'bg': 'linear-gradient(135deg, #dc2626, #b91c1c)'},
            2: {'name': 'Blue', 'bg': 'linear-gradient(135deg, #2563eb, #1d4ed8)'},
        },
    },
}

VARIANT_MAP = {
    '1-star': ('1_star', '1 Star'),
    '2-star': ('2_star', '2 Star'),
    'mixed': ('mixed', 'Mixed Stars'),
    'stickers': ('sticker', 'Sticker Set'),
}


def sw_hub(request):
    """Star Wars trading cards hub page."""
    from django.db.models import Sum

    def get_total(parent_set):
        return NonSportsCards.objects.filter(parent_set=parent_set).aggregate(
            total=Sum('quantity_owned'))['total'] or 0

    other_sw = NonSportsCards.objects.filter(
        category='Star Wars', parent_set__isnull=True
    ).order_by('title')

    return render(request, 'non_sports_cards/star_wars_hub.html', {
        'anh_total': get_total('SW 77 ANH'),
        'esb_total': get_total('SW 80 ESB'),
        'rotj_total': get_total('SW 83 ROTJ'),
        'other_sw_sets': other_sw,
    })


def sw_movie(request, movie):
    """Star Wars movie overview — shows all series for that movie."""
    movie_data = SW_MOVIES.get(movie)
    if not movie_data:
        from django.http import Http404
        raise Http404

    series_list = []
    for num, color_info in movie_data['series_colors'].items():
        items = NonSportsCards.objects.filter(
            parent_set=movie_data['parent_set'],
            series_number=num,
        )
        qty = {v[0]: 0 for v in VARIANT_MAP.values()}
        for item in items:
            if item.star_variant in qty:
                qty[item.star_variant] = item.quantity_owned

        series_list.append({
            'number': num,
            'color_name': color_info['name'],
            'bg_style': color_info['bg'],
            'qty_1star': qty.get('1_star', 0),
            'qty_2star': qty.get('2_star', 0),
            'qty_mixed': qty.get('mixed', 0),
            'qty_sticker': qty.get('sticker', 0),
        })

    return render(request, 'non_sports_cards/star_wars_movie.html', {
        'movie_title': movie_data['title'],
        'movie_slug': movie,
        'year': movie_data['year'],
        'total_series': movie_data['total_series'],
        'series_list': series_list,
    })


def sw_series(request, movie, series):
    """Star Wars series overview — shows star variants for a series."""
    movie_data = SW_MOVIES.get(movie)
    if not movie_data or series not in movie_data['series_colors']:
        from django.http import Http404
        raise Http404

    color_info = movie_data['series_colors'][series]
    items = NonSportsCards.objects.filter(
        parent_set=movie_data['parent_set'],
        series_number=series,
    )
    qty = {v[0]: 0 for v in VARIANT_MAP.values()}
    for item in items:
        if item.star_variant in qty:
            qty[item.star_variant] = item.quantity_owned

    return render(request, 'non_sports_cards/star_wars_series.html', {
        'movie_title': movie_data['title'],
        'movie_slug': movie,
        'series_number': series,
        'series_color': color_info['name'],
        'series_bg': color_info['bg'],
        'qty_1star': qty.get('1_star', 0),
        'qty_2star': qty.get('2_star', 0),
        'qty_mixed': qty.get('mixed', 0),
        'qty_sticker': qty.get('sticker', 0),
    })


def sw_variant(request, movie, series, variant):
    """Star Wars variant detail — the actual listing page."""
    movie_data = SW_MOVIES.get(movie)
    variant_info = VARIANT_MAP.get(variant)
    if not movie_data or series not in movie_data['series_colors'] or not variant_info:
        from django.http import Http404
        raise Http404

    variant_key, variant_name = variant_info
    color_info = movie_data['series_colors'][series]

    card = NonSportsCards.objects.filter(
        parent_set=movie_data['parent_set'],
        series_number=series,
        star_variant=variant_key,
    ).first()

    quantity = card.quantity_owned if card else 0

    return render(request, 'non_sports_cards/star_wars_variant_detail.html', {
        'movie_title': movie_data['title'],
        'movie_slug': movie,
        'series_number': series,
        'series_color': color_info['name'],
        'series_bg': color_info['bg'],
        'variant_key': variant_key,
        'variant_name': variant_name,
        'quantity': quantity,
        'year': movie_data['year'],
        'card': card,
    })
