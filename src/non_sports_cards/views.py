# src/non_sports_cards/views.py

import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import NonSportsCards
from .filters import NonSportsCardsFilter

# Create your views here.

# def home(request):
#     return render(request, 'non_sports_cards/home.html')

# Set up a logger
logger = logging.getLogger(__name__)

# Create a custom handler
handler = logging.StreamHandler()

# Create a formatter that adds newlines before and after each log message
formatter = logging.Formatter('\n%(asctime)s - %(levelname)s - %(message)s\n')

# Set the formatter to the handler
handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(handler)

# Optionally, set the logging level if not already set
logger.setLevel(logging.DEBUG)

# file: src/non_sports_cards/views.py

@login_required
def home(request):
    return render(request, 'non_sports_cards/home.html')
@login_required
def list_cards(request):
    logger.debug(f"Request GET parameters: {request.GET}")

    # Apply filters based on GET parameters
    non_sports_cards_filter = NonSportsCardsFilter(request.GET, queryset=NonSportsCards.objects.all())

    # Check if any GET parameters are present and apply filter
    if request.GET and non_sports_cards_filter.is_valid():
        queryset = non_sports_cards_filter.qs
        logger.info(f"Filtered queryset: {list(queryset)}")
    else:
        # If no GET parameters, return the full queryset
        queryset = NonSportsCards.objects.all()
        logger.info("No filter parameters applied, returning full queryset.")

        # Check for title in GET parameters, and default to an empty string if it's not provided
        title = request.GET.get('title', '')

        # Log the value of request.GET.title to see what is passed when rendering the form
        logger.debug(f"Title in GET parameters: {request.GET.get('title', 'No title provided')}")

        # Prepare context with a default title value
        context = {
            'filter': non_sports_cards_filter,
            'cards': queryset,
            'title': 'Non-Sports Cards List',  # Static page title
            'filter_title': title  # Dynamic filter title value
        }

    # Check if HTMX request and return partial template
    if request.htmx:
        logger.info("HTMX request detected, returning partial view.")
        return render(request, 'partials/non_sports_cards_list_partial.html', context)

    # For full page load
    logger.info("Full page load")
    return render(request, 'non_sports_cards/home.html', context)

