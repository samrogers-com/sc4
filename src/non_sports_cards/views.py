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

        total = sum(qty.values())
        series_list.append({
            'number': num,
            'color_name': color_info['name'],
            'bg_style': color_info['bg'],
            'qty_1star': qty.get('1_star', 0),
            'qty_2star': qty.get('2_star', 0),
            'qty_mixed': qty.get('mixed', 0),
            'qty_sticker': qty.get('sticker', 0),
            'total_qty': total,
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


# =============================================================================
# R2 Gallery Views — auto-generated from R2 bucket images
# =============================================================================

from django.urls import reverse

from .r2_utils import (
    get_r2_folders,
    get_r2_images,
    get_r2_folder_thumbnails,
    folder_display_name,
    parse_sw_filename,
    group_sw_images_by_sku,
    PRODUCT_TYPE_NAMES,
    CDN_BASE,
)


NON_TRADING_CARD_TYPES = ('posters', 'comic-books', 'reference')


def _r2_prefix(product_type, path=''):
    """Build the R2 prefix from product type and path.
    Posters and comic-books live at root level on R2, not under trading-cards/.
    """
    if product_type in NON_TRADING_CARD_TYPES:
        prefix = f"{product_type}/"
    else:
        prefix = f"trading-cards/{product_type}/"
    if path:
        prefix += f"{path}/"
    return prefix


def r2_gallery(request, product_type, path=''):
    """
    Browse R2 gallery — shows subfolders or images under a product type path.

    URL: /non_sports_cards/gallery/<product_type>/
         /non_sports_cards/gallery/<product_type>/<path>/
    """
    prefix = _r2_prefix(product_type, path)

    # Check for subfolders first
    subfolders = get_r2_folders(prefix)

    if subfolders:
        # Show folder browsing view with thumbnails
        folder_data = get_r2_folder_thumbnails(prefix)

        # Enrich each folder with display name and URL
        for f in folder_data:
            f['display_name'] = folder_display_name(f['folder'])
            sub_path = f"{path}/{f['folder']}" if path else f['folder']
            browse_url = reverse(
                'non_sports_cards:r2_gallery',
                kwargs={'product_type': product_type, 'path': sub_path},
            )
            detail_url = reverse(
                'non_sports_cards:r2_gallery',
                kwargs={'product_type': product_type, 'path': sub_path},
            )
            # Check if this folder has subfolders — if so, link to browse, else detail
            child_prefix = f"{prefix}{f['folder']}/"
            child_folders = get_r2_folders(child_prefix)
            f['url'] = browse_url if child_folders else detail_url

        context = {
            'product_type': product_type,
            'product_type_name': PRODUCT_TYPE_NAMES.get(product_type, product_type.title()),
            'path': path,
            'breadcrumbs': _build_breadcrumbs(product_type, path),
            'folders': folder_data,
        }
        return render(request, 'non_sports_cards/r2_gallery.html', context)
    else:
        # No subfolders — show images directly (redirect to detail view logic)
        images = get_r2_images(prefix)
        if images:
            # Render as a detail/product page
            return _render_gallery_detail(request, product_type, path, images)

        # Empty — show gallery page with empty state
        context = {
            'product_type': product_type,
            'product_type_name': PRODUCT_TYPE_NAMES.get(product_type, product_type.title()),
            'path': path,
            'breadcrumbs': _build_breadcrumbs(product_type, path),
            'folders': [],
            'folder_display': {},
        }
        return render(request, 'non_sports_cards/r2_gallery.html', context)


def r2_gallery_detail(request, product_type, path):
    """
    Product detail gallery — shows all images for a specific product folder.

    URL: /trading-cards/gallery/<product_type>/<path>/detail/
    """
    prefix = _r2_prefix(product_type, path)
    images = get_r2_images(prefix)
    return _render_gallery_detail(request, product_type, path, images)


def _render_gallery_detail(request, product_type, path, images):
    """Shared renderer for the gallery detail page."""
    # Check if these are SW ANH set photos with SKU naming
    sw_groups = None
    has_sw_data = False
    if images:
        parsed = parse_sw_filename(images[0]['filename'])
        if parsed:
            has_sw_data = True
            sw_groups = group_sw_images_by_sku(images)

    # Build a display name from the last path segment
    last_segment = path.rstrip('/').split('/')[-1] if path else product_type
    display_name = folder_display_name(last_segment)

    context = {
        'product_type': product_type,
        'product_type_name': PRODUCT_TYPE_NAMES.get(product_type, product_type.title()),
        'path': path,
        'breadcrumbs': _build_breadcrumbs(product_type, path),
        'display_name': display_name,
        'images': images,
        'image_count': len(images),
        'has_sw_data': has_sw_data,
        'sw_groups': sw_groups,
    }
    return render(request, 'non_sports_cards/r2_gallery_detail.html', context)


def _build_breadcrumbs(product_type, path):
    """
    Build breadcrumb list from product_type and path.

    Returns: [{'label': 'Trading Cards', 'url': '...'}, {'label': 'Boxes', 'url': '...'}, ...]
    """
    crumbs = [
        {'label': 'Trading Cards', 'url': reverse('non_sports_cards:non_sports_cards_home')},
        {'label': PRODUCT_TYPE_NAMES.get(product_type, product_type.title()),
         'url': reverse('non_sports_cards:r2_gallery_root', kwargs={'product_type': product_type})},
    ]

    if path:
        parts = [p for p in path.split('/') if p]
        accumulated = ''
        for part in parts:
            accumulated = f"{accumulated}/{part}" if accumulated else part
            crumbs.append({
                'label': folder_display_name(part),
                'url': reverse('non_sports_cards:r2_gallery',
                               kwargs={'product_type': product_type, 'path': accumulated}),
            })

    return crumbs
