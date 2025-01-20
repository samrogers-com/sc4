# file: src/ebay_templates/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.text import slugify
from django.forms import modelformset_factory
from django.http import JsonResponse
from django.db.models import Prefetch
from django.views.decorators.csrf import csrf_exempt

from itertools import groupby
from collections import defaultdict
from datetime import datetime
from .models import GeneratedEbayTemplate, SavedTemplate
from non_sports_cards.models import NonSportsCards, NonSportsCardImage
from comic_books.models import StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic
from movie_posters.models import MoviePosters
from .forms import NonSportsCardForm, ComicBookForm, MoviePostersForm

# Centralized configuration for templates
TEMPLATE_CONFIG = {
    'non_sports_cards': {
        'model': NonSportsCards,
        'form': NonSportsCardForm,
        'template': 'ebay_templates/generated_template.html',
    },
    'starwars_marvel_comic': {
        'model': StarWarsMarvelComic,
        'form': ComicBookForm,
        'template': 'ebay_templates/generated_template.html',
    },
    'starwars_darkhorse_comic': {
        'model': StarWarsDarkHorseComic,
        'form': ComicBookForm,
        'template': 'ebay_templates/generated_template.html',
    },
    'startrek_dc_comic': {
        'model': StarTrekDcComic,
        'form': ComicBookForm,
        'template': 'ebay_templates/generated_template.html',
    },
    'movie_posters': {
        'model': MoviePosters,
        'form': MoviePostersForm,
        'template': 'ebay_templates/generated_template.html',
    },
}


@login_required
def ebay_templates_home(request):
    """Homepage for eBay templates."""
    return render(request, 'ebay_templates/home.html')


@login_required
def non_sports_cards_home(request):
    """Homepage for Non-Sports Cards."""
    templates = SavedTemplate.objects.filter(user=request.user, category='non_sports_cards')
    return render(request, 'non_sports_cards/non_sports_cards_home.html', {
        'templates': templates,
        'has_templates': templates.exists(),
    })

@login_required
def create_template(request, template_type):
    """Create a new eBay template with image upload functionality."""
    # Get template configuration
    config = TEMPLATE_CONFIG.get(template_type)
    if not config:
        return HttpResponse("Invalid template type.", status=400)

    model_class = config['model']
    template_name = config['template']

    # Fetch all items of the selected model class and group them by the first letter of the title
    items = model_class.objects.prefetch_related(
        Prefetch('images', queryset=NonSportsCardImage.objects.filter(uploaded_by=request.user))
    ).order_by('title')

    grouped_items = defaultdict(list)
    for item in items:
        first_letter = item.title[0].upper() if item.title else "#"
        grouped_items[first_letter].append(item)

    # Define the formset
    ImageFormSet = modelformset_factory(
        NonSportsCardImage,
        fields=['image_name', 'image_type', 's3_path'],
        extra=1,  # Allow one additional blank form
        can_delete=True
    )

    if request.method == 'POST':
        # Get selected item ID from the form
        selected_item_id = request.POST.get('selected_item')
        formset = ImageFormSet(request.POST)

        if not selected_item_id:
            return render(request, 'ebay_templates/create_template.html', {
                'grouped_items': grouped_items,
                'template_type': template_type,
                'formset': formset,
                'error': 'Please select an item.',
            })

        try:
            # Get the selected item
            item = model_class.objects.get(id=selected_item_id)
        except model_class.DoesNotExist:
            return HttpResponse("Item not found.", status=404)

        if formset.is_valid():
            # Save all valid forms in the formset
            images = formset.save(commit=False)
            for image in images:
                image.non_sports_card = item  # Link the image to the selected item
                image.uploaded_by = request.user  # Ensure image is linked to the logged-in user
                image.save()

            # Generate HTML content for the template
            html_content = render_to_string(template_name, {
                'item': item,
                'card_images': item.images.all(),
                'base_url': request.build_absolute_uri('/')
            })

            # Save the generated eBay template
            ebay_template = GeneratedEbayTemplate.objects.create(
                user=request.user,
                template_type=template_type,
                title=item.title,
                content_object_id=item.id,
                html_content=html_content,
            )

            return redirect('ebay_templates:download_template', template_id=ebay_template.id)

    else:
        # Initialize an empty formset for a GET request
        formset = ImageFormSet(queryset=NonSportsCardImage.objects.none())

    return render(request, 'ebay_templates/create_template.html', {
        'grouped_items': grouped_items,  # Pass grouped_items to the template
        'template_type': template_type,
        'formset': formset,
    })

@login_required
def update_s3_path(request, item_id):
    """HTMX view to update the S3 path for a specific item."""
    if request.method == "POST":
        image_name = request.POST.get('image_name')
        image_type = request.POST.get('image_type')
        s3_path = request.POST.get('s3_path')

        # Validate inputs
        if not image_name or not image_type or not s3_path:
            return JsonResponse({'error': 'All fields are required'}, status=400)

        # Get or create the `NonSportsCardImage` for the item
        item = get_object_or_404(NonSportsCards, id=item_id)
        image, created = NonSportsCardImage.objects.get_or_create(
            non_sports_card=item,
            image_name=image_name,
            defaults={
                'image_type': image_type,
                's3_path': s3_path
            }
        )

        if not created:
            # If the image already exists, update its fields
            image.image_type = image_type
            image.s3_path = s3_path
            image.save()

        # Render the updated images section
        images_html = render_to_string('ebay_templates/partials/item_images.html', {'item': item}, request=request)
        return JsonResponse({'html': images_html})

    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def download_template(request, template_id):
    """Download a generated template as an HTML file."""
    template = get_object_or_404(GeneratedEbayTemplate, id=template_id, user=request.user)
    filename = f"{slugify(template.title)}-{datetime.now().strftime('%Y%m%d')}.html"
    response = HttpResponse(template.html_content, content_type='text/html')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def list_user_templates(request):
    """List templates created by the user."""
    templates = GeneratedEbayTemplate.objects.filter(user=request.user)
    return render(request, 'list_templates.html', {'templates': templates})


@login_required
def download_template(request, template_id):
    """Download a generated template."""
    template = get_object_or_404(GeneratedEbayTemplate, id=template_id, user=request.user)
    filename = f"{slugify(template.title)}-{datetime.now().strftime('%Y%m%d')}.html"
    response = HttpResponse(template.html_content, content_type='text/html')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def comic_home(request):
    """
    Home page for Comic Book templates.
    """
    templates = SavedTemplate.objects.filter(user=request.user, category='comic_books')
    return render(request, 'ebay_templates/comic_books/comic_books_home.html', {  # Adjusted path
        'templates': templates,
        'has_templates': templates.exists()
    })
@login_required
def movie_posters_home(request):
    """
    Home page for Movie Posters templates.
    """
    templates = SavedTemplate.objects.filter(user=request.user, category='movie_posters')
    return render(request, 'ebay_templates/movie_posters/movie_posters_home.html', {
        'templates': templates,
        'has_templates': templates.exists()
    })

from django.shortcuts import get_object_or_404

@login_required
def template_detail(request, template_id):
    """
    Display the details of a saved template.
    """
    template = get_object_or_404(SavedTemplate, id=template_id, user=request.user)
    return render(request, 'template_detail.html', {'template': template})

@login_required
def template_delete(request, template_id):
    """
    Delete a saved template.
    """
    template = get_object_or_404(SavedTemplate, id=template_id, user=request.user)
    
    if request.method == "POST":
        template.delete()
        return HttpResponseRedirect(reverse('ebay_templates:list_templates'))
    
    return render(request, 'template_delete.html', {'template': template})

