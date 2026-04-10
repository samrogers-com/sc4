# src/non_sports_cards/views.py

from django.shortcuts import render
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
