from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.contrib import messages

from .models import EbayListing, EbayOrder, EbayOrderItem


def is_staff(user):
    return user.is_staff


@login_required
@user_passes_test(is_staff)
def dashboard(request):
    """Main eBay Manager dashboard."""
    total_listings = EbayListing.objects.count()
    active_listings = EbayListing.objects.filter(status='active').count()
    draft_listings = EbayListing.objects.filter(status='draft').count()
    sold_listings = EbayListing.objects.filter(status='sold').count()

    total_orders = EbayOrder.objects.count()
    revenue = EbayOrder.objects.aggregate(total=Sum('order_total'))['total'] or 0
    total_profit = EbayOrder.objects.aggregate(total=Sum('net_profit'))['total'] or 0

    recent_orders = EbayOrder.objects.order_by('-creation_date')[:10]
    recent_listings = EbayListing.objects.order_by('-created_at')[:10]

    # API status
    api_status = _get_api_status()

    return render(request, 'ebay_manager/dashboard.html', {
        'total_listings': total_listings,
        'active_listings': active_listings,
        'draft_listings': draft_listings,
        'sold_listings': sold_listings,
        'total_orders': total_orders,
        'revenue': revenue,
        'total_profit': total_profit,
        'recent_orders': recent_orders,
        'recent_listings': recent_listings,
        'api_status': api_status,
    })


LISTING_SORT_FIELDS = {
    'title': 'title', '-title': '-title',
    'sku': 'sku', '-sku': '-sku',
    'price': 'price', '-price': '-price',
    'status': 'status', '-status': '-status',
    'views': 'view_count', '-views': '-view_count',
    'watchers': 'watch_count', '-watchers': '-watch_count',
    'created': 'created_at', '-created': '-created_at',
}


@login_required
@user_passes_test(is_staff)
def listings(request):
    """All eBay listings with filters."""
    status_filter = request.GET.get('status', '')
    sort = request.GET.get('sort', '-created')
    qs = EbayListing.objects.all()
    if status_filter:
        qs = qs.filter(status=status_filter)
    order_field = LISTING_SORT_FIELDS.get(sort, '-created_at')
    qs = qs.order_by(order_field)

    return render(request, 'ebay_manager/listings.html', {
        'listings': qs,
        'status_filter': status_filter,
        'status_choices': EbayListing.STATUS_CHOICES,
        'current_sort': sort,
    })


@login_required
@user_passes_test(is_staff)
def listing_create(request):
    """Create a new eBay draft listing.

    Supports two modes:
    - Manual: fill in the form fields directly
    - Pre-populated: pass GET params from gap report or R2 gallery:
        ?r2_prefix=trading-cards/boxes/007-goldeneye
        &title=007+GoldenEye+Sealed+Box
        &product_type=boxes

    When r2_prefix is provided, images are loaded from R2 CDN and
    a matching pre-built HTML description is searched in ebay_uploads/.
    """
    import json

    if request.method == 'POST':
        # Parse optional inventory link (GenericFK) — empty means unlinked
        content_type_id = request.POST.get('content_type_id') or None
        object_id = request.POST.get('object_id') or None

        # Parse image URLs from hidden JSON field — normalize to plain strings
        image_urls_json = request.POST.get('image_urls_json', '[]')
        try:
            raw_urls = json.loads(image_urls_json)
            image_urls = _normalize_image_urls(raw_urls)
        except (json.JSONDecodeError, TypeError):
            image_urls = []

        listing = EbayListing(
            title=request.POST.get('title', ''),
            price=request.POST.get('price', 0),
            sku=request.POST.get('sku', ''),
            category_id=request.POST.get('category_id', ''),
            condition_id=request.POST.get('condition_id', '7000'),
            description_html=request.POST.get('description_html', ''),
            image_urls=image_urls,
            packaging_config=request.POST.get('packaging_config', 'sealed_box'),
            weight_lbs=int(request.POST.get('weight_lbs', 0) or 0),
            weight_oz=int(request.POST.get('weight_oz', 0) or 0),
            shipping_service='USPSGroundAdvantage',
            shipping_cost=0,
            status='draft',
            created_by=request.user,
            content_type_id=content_type_id,
            object_id=object_id,
        )
        listing.save()
        messages.success(request, f'Draft listing created: {listing.title}')
        return redirect('ebay_manager:listing_detail', pk=listing.pk)

    # GET — pre-populate from R2 gallery or gap report params
    r2_prefix = request.GET.get('r2_prefix', '')
    title = request.GET.get('title', '')
    product_type = request.GET.get('product_type', '')

    image_urls = []
    description_html = ''
    description_files = []
    category_id = ''

    if r2_prefix:
        # Load R2 images for this product (ensure trailing slash)
        try:
            from non_sports_cards.r2_utils import get_r2_images
            prefix = r2_prefix if r2_prefix.endswith('/') else r2_prefix + '/'
            raw_images = get_r2_images(prefix)
            image_urls = _normalize_image_urls(raw_images)
        except Exception:
            pass

        # Default category for sealed boxes
        if product_type == 'boxes' or 'box' in r2_prefix:
            category_id = '261035'

        # Try to find a matching pre-built HTML description
        try:
            from .services.description_files import find_matching_description, list_description_files
            match = find_matching_description(r2_prefix)
            if match:
                description_html = match['content']
            description_files = list_description_files()
        except Exception:
            pass

    # Derive title from r2_prefix if not provided
    if not title and r2_prefix:
        slug = r2_prefix.rstrip('/').split('/')[-1]
        title = slug.replace('-', ' ').title()

    return render(request, 'ebay_manager/listing_create.html', {
        'r2_prefix': r2_prefix,
        'title': title,
        'product_type': product_type,
        'image_urls': image_urls,
        'image_urls_json': json.dumps(image_urls),
        'description_html': description_html,
        'description_files': description_files,
        'category_id': category_id,
    })


@login_required
@user_passes_test(is_staff)
def listing_detail(request, pk):
    """Single listing detail."""
    listing = get_object_or_404(EbayListing, pk=pk)
    order_items = listing.order_items.select_related('order').all()

    return render(request, 'ebay_manager/listing_detail.html', {
        'listing': listing,
        'order_items': order_items,
    })


ORDER_SORT_FIELDS = {
    'buyer': 'buyer_username', '-buyer': '-buyer_username',
    'total': 'order_total', '-total': '-order_total',
    'fees': 'ebay_fees', '-fees': '-ebay_fees',
    'status': 'order_status', '-status': '-order_status',
    'date': 'creation_date', '-date': '-creation_date',
    'tracking': 'tracking_number', '-tracking': '-tracking_number',
}


@login_required
@user_passes_test(is_staff)
def orders(request):
    """Order history."""
    status_filter = request.GET.get('status', '')
    sort = request.GET.get('sort', '-date')
    qs = EbayOrder.objects.prefetch_related('items').all()
    if status_filter:
        qs = qs.filter(order_status=status_filter)
    order_field = ORDER_SORT_FIELDS.get(sort, '-creation_date')
    qs = qs.order_by(order_field)

    return render(request, 'ebay_manager/orders.html', {
        'orders': qs,
        'status_filter': status_filter,
        'status_choices': EbayOrder.ORDER_STATUSES,
        'current_sort': sort,
    })


@login_required
@user_passes_test(is_staff)
def order_detail(request, pk):
    """Single order detail."""
    order = get_object_or_404(EbayOrder.objects.prefetch_related('items'), pk=pk)

    return render(request, 'ebay_manager/order_detail.html', {
        'order': order,
    })


@login_required
@user_passes_test(is_staff)
def analytics(request):
    """Performance analytics."""
    total_revenue = EbayOrder.objects.aggregate(total=Sum('order_total'))['total'] or 0
    total_profit = EbayOrder.objects.aggregate(total=Sum('net_profit'))['total'] or 0
    total_fees = EbayOrder.objects.aggregate(total=Sum('ebay_fees'))['total'] or 0
    total_orders = EbayOrder.objects.count()

    top_items = (
        EbayOrderItem.objects
        .values('title')
        .annotate(total_sold=Sum('quantity'), total_revenue=Sum('price'))
        .order_by('-total_revenue')[:20]
    )

    status_breakdown = (
        EbayOrder.objects
        .values('order_status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return render(request, 'ebay_manager/analytics.html', {
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'total_fees': total_fees,
        'total_orders': total_orders,
        'top_items': top_items,
        'status_breakdown': status_breakdown,
    })


@login_required
@user_passes_test(is_staff)
def settings_view(request):
    """API connection status and setup."""
    api_status = _get_api_status()

    return render(request, 'ebay_manager/settings.html', {
        'api_status': api_status,
    })


@login_required
@user_passes_test(is_staff)
def sync_listings(request):
    """Import active listings from eBay."""
    if request.method == 'POST':
        try:
            from .services.listing_sync import sync_active_listings
            result = sync_active_listings()
            messages.success(request, f"Listings synced: {result['created']} new, {result['updated']} updated ({result['total']} total from eBay)")
        except Exception as e:
            messages.error(request, f'Listing sync failed: {e}')
        return redirect('ebay_manager:dashboard')
    return redirect('ebay_manager:dashboard')


@login_required
@user_passes_test(is_staff)
def sync_orders(request):
    """Import sold history from eBay."""
    if request.method == 'POST':
        try:
            from .services.fulfillment import sync_orders_to_db
            result = sync_orders_to_db(days=365)
            messages.success(request, f"Orders synced: {result['created']} new, {result['updated']} updated ({result['total']} total from eBay)")
        except Exception as e:
            messages.error(request, f'Order sync failed: {e}')
        return redirect('ebay_manager:dashboard')
    return redirect('ebay_manager:dashboard')


@login_required
@user_passes_test(is_staff)
def sync_all(request):
    """Sync both listings and orders from eBay."""
    if request.method == 'POST':
        results = []
        try:
            from .services.listing_sync import sync_active_listings
            lr = sync_active_listings()
            results.append(f"Listings: {lr['created']} new, {lr['updated']} updated")
        except Exception as e:
            results.append(f"Listings failed: {e}")
        try:
            from .services.fulfillment import sync_orders_to_db
            orr = sync_orders_to_db(days=365)
            results.append(f"Orders: {orr['created']} new, {orr['updated']} updated")
        except Exception as e:
            results.append(f"Orders failed: {e}")
        messages.success(request, ' | '.join(results))
        return redirect('ebay_manager:dashboard')
    return redirect('ebay_manager:dashboard')


@login_required
@user_passes_test(is_staff)
def publish_draft(request, pk):
    """Send a listing to eBay as a draft (appears in Seller Hub Drafts)."""
    if request.method == 'POST':
        listing = get_object_or_404(EbayListing, pk=pk)
        try:
            from .services.publish import send_to_ebay_drafts
            result = send_to_ebay_drafts(listing)
            messages.success(request, f'Sent to eBay Drafts: {listing.title} (SKU: {result["sku"]})')
        except Exception as e:
            messages.error(request, f'Failed to send to eBay: {e}')
        return redirect('ebay_manager:listing_detail', pk=pk)
    return redirect('ebay_manager:listing_detail', pk=pk)


@login_required
@user_passes_test(is_staff)
def publish_active(request, pk):
    """Publish a listing to eBay as a live active listing."""
    if request.method == 'POST':
        listing = get_object_or_404(EbayListing, pk=pk)
        try:
            from .services.publish import publish_to_ebay
            result = publish_to_ebay(listing)
            messages.success(request, f'Published to eBay! Item #{result["listing_id"]} — {listing.title}')
        except Exception as e:
            messages.error(request, f'Failed to publish: {e}')
        return redirect('ebay_manager:listing_detail', pk=pk)
    return redirect('ebay_manager:listing_detail', pk=pk)


@login_required
@user_passes_test(is_staff)
def gap_report(request):
    """Web-based gap report comparing R2 photos with active eBay listings.

    Shows two sections:
    1. R2 products with photos but no active/draft listing — with "Create Listing" buttons
    2. Active listings with no R2 photos — may need photos taken

    This is the web equivalent of `manage.py ebay_sync --report`.
    """
    from .services.gap_report import get_gap_report
    report = get_gap_report()
    return render(request, 'ebay_manager/gap_report.html', {
        'r2_without_listing': report['r2_without_listing'],
        'listings_without_photos': report['listings_without_photos'],
        'stats': report['stats'],
    })


@login_required
@user_passes_test(is_staff)
def load_description_html(request):
    """HTMX endpoint: load a pre-built HTML description file.

    Called via HTMX when user selects a description file from the
    dropdown on the listing create form. Returns the HTML content
    for insertion into the description textarea.

    GET params:
        file: relative path within ebay_uploads/ (e.g. 'ns_cards/box/1995-007-goldeneye.html')
    """
    from .services.description_files import read_description_file
    filepath = request.GET.get('file', '')
    content = read_description_file(filepath) if filepath else ''
    return JsonResponse({'html': content or ''})


def _normalize_image_urls(raw_urls):
    """Convert image URLs from various formats to plain URL strings.

    get_r2_images() returns dicts like {'key': '...', 'url': '...', 'filename': '...'}
    but we store plain URL strings in the database. This handles both formats.
    """
    urls = []
    for item in raw_urls:
        if isinstance(item, dict):
            urls.append(item.get('url', ''))
        elif isinstance(item, str):
            urls.append(item)
    return [u for u in urls if u]


@login_required
@user_passes_test(is_staff)
def listing_edit(request, pk):
    """Edit an existing eBay listing draft.

    Allows editing all fields: title, price, SKU, category, condition,
    description HTML, shipping, and images. For draft listings, also
    provides a button to submit to eBay (future).
    """
    import json
    listing = get_object_or_404(EbayListing, pk=pk)

    if request.method == 'POST':
        listing.title = request.POST.get('title', listing.title)
        listing.price = request.POST.get('price', listing.price)
        listing.sku = request.POST.get('sku', listing.sku)
        listing.category_id = request.POST.get('category_id', listing.category_id)
        listing.condition_id = request.POST.get('condition_id', listing.condition_id)
        listing.description_html = request.POST.get('description_html', listing.description_html)
        listing.packaging_config = request.POST.get('packaging_config', listing.packaging_config)
        listing.weight_lbs = int(request.POST.get('weight_lbs', listing.weight_lbs) or 0)
        listing.weight_oz = int(request.POST.get('weight_oz', listing.weight_oz) or 0)

        # Parse image URLs
        image_urls_json = request.POST.get('image_urls_json', '')
        if image_urls_json:
            try:
                raw_urls = json.loads(image_urls_json)
                listing.image_urls = _normalize_image_urls(raw_urls)
            except (json.JSONDecodeError, TypeError):
                pass

        listing.save()
        messages.success(request, f'Listing updated: {listing.title}')
        return redirect('ebay_manager:listing_detail', pk=listing.pk)

    # Normalize image URLs for display
    image_urls = _normalize_image_urls(listing.image_urls) if listing.image_urls else []

    # Load available description files
    try:
        from .services.description_files import list_description_files
        description_files = list_description_files()
    except Exception:
        description_files = []

    return render(request, 'ebay_manager/listing_edit.html', {
        'listing': listing,
        'image_urls': image_urls,
        'image_urls_json': json.dumps(image_urls),
        'description_files': description_files,
    })


def _get_api_status():
    """Check eBay API connection status."""
    import os
    from pathlib import Path

    app_id = os.environ.get('EBAY_APP_ID', '')
    cert_id = os.environ.get('EBAY_CERT_ID', '')
    token_file = Path(__file__).parent.parent / 'tools' / 'ebay_user_token.json'

    return {
        'browse_api': bool(app_id and cert_id),
        'app_id_set': bool(app_id),
        'cert_id_set': bool(cert_id),
        'user_oauth': token_file.exists(),
        'token_file': str(token_file),
    }
