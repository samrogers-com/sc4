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
    """All eBay listings with filters.

    Variant groups are collapsed: one row per group_key showing the group
    title, variant count, and total value. Clicking links to the group detail.
    Non-variant listings show as individual rows.
    """
    status_filter = request.GET.get('status', '')
    sort = request.GET.get('sort', '-created')
    qs = EbayListing.objects.all()
    if status_filter:
        qs = qs.filter(status=status_filter)
    order_field = LISTING_SORT_FIELDS.get(sort, '-created_at')
    qs = qs.order_by(order_field)

    # Collapse variant groups into single rows
    seen_groups = set()
    rows = []
    for listing in qs:
        if listing.is_variant and listing.group_key:
            if listing.group_key in seen_groups:
                continue
            seen_groups.add(listing.group_key)
            group_qs = EbayListing.objects.filter(group_key=listing.group_key)
            rows.append({
                'listing': listing,
                'is_group': True,
                'group_key': listing.group_key,
                'variant_count': group_qs.count(),
                'total_price': sum(float(v.price) for v in group_qs),
            })
        else:
            rows.append({'listing': listing, 'is_group': False})

    return render(request, 'ebay_manager/listings.html', {
        'rows': rows,
        'listings': qs,  # kept for empty state
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
            market_mean_price=request.POST.get('market_mean_price') or None,
            suggested_price=request.POST.get('suggested_price') or None,
            sku=request.POST.get('sku', ''),
            quantity=int(request.POST.get('quantity', 1) or 1),
            category_id=request.POST.get('category_id', ''),
            condition_id=request.POST.get('condition_id', '7000'),
            description_html=request.POST.get('description_html', ''),
            image_urls=image_urls,
            item_specifics=_parse_item_specifics(request.POST),
            packaging_config=request.POST.get('packaging_config', 'sealed_box'),
            package_length=int(request.POST.get('package_length', 0) or 0),
            package_width=int(request.POST.get('package_width', 0) or 0),
            package_height=int(request.POST.get('package_height', 0) or 0),
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
    item_specs = {}
    price_data = {}
    weight_lbs = 0
    weight_oz = 0
    package_length = 9  # default box dims
    package_width = 6
    package_height = 4

    if r2_prefix:
        # Load R2 images for this product (ensure trailing slash)
        try:
            from non_sports_cards.r2_utils import get_r2_images
            prefix = r2_prefix if r2_prefix.endswith('/') else r2_prefix + '/'
            raw_images = get_r2_images(prefix)
            image_urls = _normalize_image_urls(raw_images)
        except Exception:
            pass

        # Default category by product type
        if product_type == 'boxes' or 'box' in r2_prefix:
            category_id = '261035'   # Sealed Trading Card Boxes
        elif product_type == 'sets' or 'sets' in r2_prefix:
            category_id = '183052'   # Trading Card Sets
        elif product_type == 'packs' or 'pack' in r2_prefix:
            category_id = '183053'   # Sealed Trading Card Packs
        elif product_type == 'singles' or 'single' in r2_prefix:
            category_id = '183050'   # Trading Card Singles
        elif product_type == 'wrappers' or 'wrapper' in r2_prefix:
            category_id = '183054'   # Wrappers & Empty Card Boxes
        elif product_type == 'binders' or 'binder' in r2_prefix:
            category_id = '183059'   # Card Albums, Binders & Pages

        # Look up product data (title, item specifics, dims) from gap report
        folder_slug = r2_prefix.rstrip('/').split('/')[-1]
        try:
            from .services.gap_report import PRODUCT_DATA
            product_info = PRODUCT_DATA.get(folder_slug, {})
            if product_info:
                if not title:
                    title = product_info.get('title', '')
                raw_specs = product_info.get('specs', {})
                item_specs = {k.replace(' ', '_'): v for k, v in raw_specs.items()}
                weight_lbs = product_info.get('weight_lbs', 0)
                weight_oz = product_info.get('weight_oz', 0)
        except Exception:
            pass

        # Try to find a matching pre-built HTML description
        try:
            from .services.description_files import find_matching_description, list_description_files
            match = find_matching_description(r2_prefix)
            if match:
                description_html = match['content']
            description_files = list_description_files()
        except Exception:
            pass

        # If no pre-built file found, auto-generate from product specs
        if not description_html and item_specs:
            try:
                from .services.description_generator import generate_description
                # Convert underscored keys back to eBay format for the generator
                raw_specs = {k.replace('_', ' '): v for k, v in item_specs.items()}
                description_html = generate_description(title, raw_specs, product_type)
            except Exception:
                pass

    # Estimate selling price (runs even outside r2_prefix block, uses title)
    if title:
        try:
            from .services.price_estimate import estimate_price
            price_data = estimate_price(title, category_id or '261035')
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
        'item_specs': item_specs,
        'weight_lbs': weight_lbs,
        'weight_oz': weight_oz,
        'package_length': package_length,
        'package_width': package_width,
        'package_height': package_height,
        'price_data': price_data,
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
def listing_preview(request, pk):
    """eBay listing preview — shows the listing as it would appear on eBay.

    Renders title, images, price, description HTML, condition, and
    shipping info in an eBay-like layout so Sam can visually inspect
    before publishing.
    """
    listing = get_object_or_404(EbayListing, pk=pk)
    image_urls = _normalize_image_urls(listing.image_urls) if listing.image_urls else []

    return render(request, 'ebay_manager/listing_preview.html', {
        'listing': listing,
        'image_urls': image_urls,
    })


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
def listing_delete(request, pk):
    """Delete a draft listing. Also cleans up eBay offer/inventory if created."""
    if request.method == 'POST':
        listing = get_object_or_404(EbayListing, pk=pk)
        title = listing.title

        # Clean up eBay side if we pushed an offer
        if listing.sku:
            try:
                import requests as req
                from .services.api_client import get_user_token
                token = get_user_token()
                if token:
                    headers = {'Authorization': f'Bearer {token}', 'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US'}
                    # Delete offer
                    resp = req.get(f'https://api.ebay.com/sell/inventory/v1/offer?sku={listing.sku}', headers=headers, timeout=10)
                    if resp.status_code == 200:
                        for o in resp.json().get('offers', []):
                            req.delete(f'https://api.ebay.com/sell/inventory/v1/offer/{o["offerId"]}', headers=headers, timeout=10)
                    # Delete inventory item
                    req.delete(f'https://api.ebay.com/sell/inventory/v1/inventory_item/{listing.sku}', headers=headers, timeout=10)
            except Exception:
                pass

        listing.delete()
        messages.success(request, f'Deleted draft: {title}')
        return redirect('ebay_manager:listings')
    return redirect('ebay_manager:listings')


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


def _parse_item_specifics(post_data):
    """Extract item specifics from form POST data into a dict for the JSONField.

    Maps form field names (spec_manufacturer, spec_franchise, etc.) to
    eBay aspect names (Manufacturer, Franchise, etc.).
    """
    field_map = {
        'spec_manufacturer': 'Manufacturer',
        'spec_franchise': 'Franchise',
        'spec_set': 'Set',
        'spec_year': 'Year Manufactured',
        'spec_configuration': 'Configuration',
        'spec_type': 'Type',
        'spec_genre': 'Genre',
        'spec_features': 'Features',
        'spec_movie': 'Movie',
        'spec_tv_show': 'TV Show',
        'card_condition': 'card_condition',
    }
    specs = {}
    for field, aspect_name in field_map.items():
        value = post_data.get(field, '').strip()
        if value:
            specs[aspect_name] = value
    return specs


@login_required
@user_passes_test(is_staff)
def multi_variant_create(request):
    """Create a multi-variant eBay listing from R2 subfolders.

    Each subfolder (box-1, box-2, etc.) becomes a variant with its own
    photos and price. Used for pre-1990 items where condition varies.

    GET: Show variants discovered from R2 with price fields per variant.
    POST: Create and publish the multi-variant listing on eBay.
    """
    import json
    r2_prefix = request.GET.get('r2_prefix', '') or request.POST.get('r2_prefix', '')
    title = request.GET.get('title', '') or request.POST.get('title', '')
    product_type = request.GET.get('product_type', '') or request.POST.get('product_type', '')

    if request.method == 'POST':
        try:
            from .services.multi_variant import create_multi_variant_listing, discover_variants
            from .services.description_generator import generate_description

            variants = discover_variants(r2_prefix)

            # Collect prices per variant from form
            prices = {}
            for v in variants:
                price_key = f"price_{v['name']}"
                prices[v['name']] = float(request.POST.get(price_key, 0))

            # Get specs
            specs = {}
            spec_map = {
                'spec_manufacturer': 'Manufacturer', 'spec_franchise': 'Franchise',
                'spec_set': 'Set', 'spec_year': 'Year Manufactured',
                'spec_genre': 'Genre', 'spec_movie': 'Movie',
                'spec_configuration': 'Configuration', 'spec_type': 'Type',
                'spec_features': 'Features',
            }
            for field, name in spec_map.items():
                val = request.POST.get(field, '').strip()
                if val:
                    specs[name] = val

            desc = request.POST.get('description_html', '')
            if not desc:
                desc = generate_description(title, specs, product_type)

            fulfillment_id = request.POST.get('fulfillment_policy_id', '119108501015')
            weight = int(request.POST.get('ship_weight_oz', 24) or 24)
            dims = None
            pl = int(request.POST.get('package_length', 0) or 0)
            pw = int(request.POST.get('package_width', 0) or 0)
            ph = int(request.POST.get('package_height', 0) or 0)
            if pl and pw and ph:
                dims = {'length': pl, 'width': pw, 'height': ph}

            action = request.POST.get('action', 'publish')

            if action == 'draft':
                # Save as drafts only — no eBay push
                from .services.multi_variant import save_variant_drafts
                result = save_variant_drafts(
                    title=title, variants=variants, specs=specs, prices=prices,
                    category_id=request.POST.get('category_id', '261035'),
                    description_html=desc, r2_prefix=r2_prefix,
                    ship_weight_oz=weight, package_dims=dims,
                    fulfillment_policy_id=fulfillment_id, user=request.user,
                )
                messages.success(request, f"Multi-variant draft saved! {result['variant_count']} variants. Group: {result['group_key']}")
                return redirect('ebay_manager:listings')
            else:
                # Publish to eBay
                result = create_multi_variant_listing(
                    title=title, variants=variants, specs=specs, prices=prices,
                    description_html=desc, fulfillment_policy_id=fulfillment_id,
                    ship_weight_oz=weight, package_dims=dims, r2_prefix=r2_prefix,
                )
                messages.success(request, f"Multi-variant listing published! {len(variants)} variants. Item #{result.get('listing_id', '?')}")
                return redirect('ebay_manager:dashboard')
        except Exception as e:
            messages.error(request, f'Multi-variant failed: {e}')
            return redirect('ebay_manager:gap_report')

    # GET — discover variants and show form
    variants = []
    item_specs = {}
    price_data = {}
    series_list = []
    series_filter = request.GET.get('series', '') or request.POST.get('series', '')

    if r2_prefix:
        try:
            from .services.multi_variant import discover_variants, discover_series
            series_list = discover_series(r2_prefix)
            variants = discover_variants(r2_prefix, series_filter=series_filter or None)
        except Exception:
            pass

        folder_slug = r2_prefix.rstrip('/').split('/')[-1]
        try:
            from .services.gap_report import PRODUCT_DATA
            product_info = PRODUCT_DATA.get(folder_slug, {})
            if product_info:
                if not title:
                    title = product_info.get('title', '')
                raw_specs = product_info.get('specs', {})
                item_specs = {k.replace(' ', '_'): v for k, v in raw_specs.items()}
        except Exception:
            pass

    if title:
        try:
            from .services.price_estimate import estimate_price
            price_data = estimate_price(title)
        except Exception:
            pass

    if not title and r2_prefix:
        title = r2_prefix.rstrip('/').split('/')[-1].replace('-', ' ').title()

    return render(request, 'ebay_manager/multi_variant_create.html', {
        'r2_prefix': r2_prefix,
        'title': title,
        'product_type': product_type,
        'variants': variants,
        'item_specs': item_specs,
        'price_data': price_data,
        'series_list': series_list,
        'series_filter': series_filter,
    })


@login_required
@user_passes_test(is_staff)
def variant_group_detail(request, group_key):
    """Detail page for a multi-variant group.

    Shows all variants in the group with their photos, prices, and statuses.
    Supports publishing draft groups to eBay and adding new variants.
    """
    variants = EbayListing.objects.filter(group_key=group_key).order_by('variant_name')
    if not variants.exists():
        messages.error(request, f'Variant group {group_key} not found.')
        return redirect('ebay_manager:listings')

    first = variants.first()

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'update_prices':
            updated = 0
            for v in variants:
                price_key = f"price_{v.pk}"
                new_price = request.POST.get(price_key)
                if new_price is not None:
                    try:
                        v.price = float(new_price)
                        v.save(update_fields=['price', 'updated_at'])
                        updated += 1
                    except (ValueError, TypeError):
                        pass
            messages.success(request, f'Updated prices for {updated} variants.')
            return redirect('ebay_manager:variant_group_detail', group_key=group_key)

        elif action == 'generate_description':
            try:
                from .services.description_generator import generate_description
                desc = generate_description(
                    first.title,
                    first.item_specifics or {},
                    'boxes',
                )
                variants.update(description_html=desc)
                messages.success(request, 'Description generated for all variants.')
            except Exception as e:
                messages.error(request, f'Description generation failed: {e}')
            return redirect('ebay_manager:variant_group_detail', group_key=group_key)

        elif action == 'add_variant':
            try:
                from .services.multi_variant import discover_variants
                r2_prefix = first.parent_r2_prefix
                discovered = discover_variants(r2_prefix)
                existing_names = set(v.variant_name for v in variants)
                new_variants = [d for d in discovered if d['display'] not in existing_names]
                if not new_variants:
                    messages.info(request, 'No new subfolders found in R2 to add.')
                else:
                    from .services.multi_variant import save_variant_drafts
                    # Save only the new variants as additional drafts
                    prices = {nv['name']: float(first.price) for nv in new_variants}
                    for nv in new_variants:
                        slug = first.group_key.replace('GRP-', '')
                        sku = f"{slug}-{nv['name'].upper()}"
                        EbayListing.objects.create(
                            title=first.title,
                            price=first.price,
                            sku=sku,
                            status='draft',
                            is_variant=True,
                            group_key=group_key,
                            variant_name=nv['display'],
                            parent_r2_prefix=r2_prefix,
                            category_id=first.category_id,
                            condition_id=first.condition_id,
                            description_html=first.description_html,
                            image_urls=nv['images'],
                            item_specifics=first.item_specifics,
                        )
                    messages.success(request, f'Added {len(new_variants)} new variant(s): {", ".join(v["display"] for v in new_variants)}')
            except Exception as e:
                messages.error(request, f'Add variant failed: {e}')
            return redirect('ebay_manager:variant_group_detail', group_key=group_key)

        elif action == 'publish_group':
            try:
                from .services.multi_variant import create_multi_variant_listing, discover_variants
                r2_prefix = first.parent_r2_prefix
                discovered = discover_variants(r2_prefix)

                # Match R2 subfolder names (box-1, box-2, ...) back to the
                # DB variants so we can (a) reuse existing prices and
                # (b) preserve custom variant_name labels like
                # "Box #0728 of 4000" instead of defaulting to "Box 1".
                price_map = {}
                display_overrides = {}
                variants_by_sku = {v.sku: v for v in variants if v.sku}
                for d in discovered:
                    sku_guess = f"{group_key.replace('GRP-', '')}-{d['name'].upper()}"
                    match = variants_by_sku.get(sku_guess)
                    if not match:
                        # Fallback: match by current display name
                        for v in variants:
                            if d['display'] == v.variant_name:
                                match = v
                                break
                    if match:
                        price_map[d['name']] = float(match.price)
                        if match.variant_name and match.variant_name != d['display']:
                            display_overrides[d['name']] = match.variant_name
                    else:
                        price_map[d['name']] = float(first.price)

                result = create_multi_variant_listing(
                    title=first.title,
                    variants=discovered,
                    specs=first.item_specifics or {},
                    prices=price_map,
                    category_id=first.category_id or '261035',
                    condition_id=first.condition_id or '7000',
                    description_html=first.description_html or '',
                    fulfillment_policy_id='119108501015',
                    ship_weight_oz=(first.weight_lbs or 0) * 16 + (first.weight_oz or 0) or 24,
                    r2_prefix=r2_prefix,
                    display_overrides=display_overrides,
                )

                # Set ebay_item_id on only the first variant — the UNIQUE
                # constraint on ebay_item_id forbids sharing it across
                # multiple rows, and a multi-variant group has one listing id.
                listing_id = result.get('listing_id', '')
                now = timezone.now()
                first_variant = variants.order_by('pk').first()
                if first_variant:
                    first_variant.status = 'active'
                    first_variant.ebay_item_id = listing_id or None
                    first_variant.ebay_listing_url = (
                        f'https://www.ebay.com/itm/{listing_id}' if listing_id else None
                    )
                    first_variant.listed_at = now
                    first_variant.last_synced = now
                    first_variant.save()
                variants.exclude(pk=first_variant.pk if first_variant else None).update(
                    status='active',
                    ebay_item_id=None,
                    ebay_listing_url=(
                        f'https://www.ebay.com/itm/{listing_id}' if listing_id else None
                    ),
                    listed_at=now,
                    last_synced=now,
                )
                messages.success(request, f"Published! eBay item #{listing_id or '?'} with {len(discovered)} variants.")
            except Exception as e:
                messages.error(request, f'Publish failed: {e}')
            return redirect('ebay_manager:variant_group_detail', group_key=group_key)

        elif action == 'delete_variant':
            try:
                variant_pk = int(request.POST.get('variant_pk', 0))
            except (TypeError, ValueError):
                variant_pk = 0
            v = variants.filter(pk=variant_pk).first()
            if not v:
                messages.error(request, f'Variant {variant_pk} not found in group.')
                return redirect('ebay_manager:variant_group_detail', group_key=group_key)
            label = v.variant_name or f'pk={v.pk}'
            try:
                # If the variant is live on eBay, remove it from the
                # inventory item group, delete its offer, then delete its
                # inventory item. Leaves the group listing intact for the
                # remaining variants.
                if v.status == 'active' and v.sku:
                    import requests as _requests
                    from .services.api_client import get_user_token
                    tok = get_user_token()
                    if tok:
                        headers = {
                            'Authorization': f'Bearer {tok}',
                            'Content-Type': 'application/json',
                            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
                            'Content-Language': 'en-US',
                        }
                        # 1) Delete offer(s) for this SKU
                        offer_resp = _requests.get(
                            f'https://api.ebay.com/sell/inventory/v1/offer?sku={v.sku}',
                            headers=headers, timeout=20,
                        )
                        if offer_resp.status_code == 200:
                            for o in offer_resp.json().get('offers', []):
                                oid = o.get('offerId')
                                if o.get('status') == 'PUBLISHED':
                                    _requests.post(
                                        f'https://api.ebay.com/sell/inventory/v1/offer/{oid}/withdraw',
                                        headers=headers, timeout=20,
                                    )
                                if oid:
                                    _requests.delete(
                                        f'https://api.ebay.com/sell/inventory/v1/offer/{oid}',
                                        headers=headers, timeout=20,
                                    )
                        # 2) Pull the SKU out of the inventory item group
                        group_url = f'https://api.ebay.com/sell/inventory/v1/inventory_item_group/{group_key}'
                        gresp = _requests.get(group_url, headers=headers, timeout=20)
                        if gresp.status_code == 200:
                            grp = gresp.json()
                            remaining = [s for s in grp.get('variantSKUs', []) if s != v.sku]
                            if remaining:
                                grp['variantSKUs'] = remaining
                                spec_list = grp.get('variesBy', {}).get('specifications', [])
                                for spec in spec_list:
                                    vals = [x for x in spec.get('values', []) if x != v.variant_name]
                                    spec['values'] = vals
                                _requests.put(group_url, headers=headers, json=grp, timeout=30)
                            else:
                                # Group would be empty — delete the whole group
                                _requests.delete(group_url, headers=headers, timeout=20)
                        # 3) Delete the inventory item itself
                        _requests.delete(
                            f'https://api.ebay.com/sell/inventory/v1/inventory_item/{v.sku}',
                            headers=headers, timeout=20,
                        )

                v.delete()
                messages.success(request, f'Deleted variant "{label}".')
                remaining = EbayListing.objects.filter(group_key=group_key).count()
                if remaining == 0:
                    return redirect('ebay_manager:listings')
            except Exception as e:
                messages.error(request, f'Delete variant failed: {e}')
            return redirect('ebay_manager:variant_group_detail', group_key=group_key)

        elif action == 'refresh_variant_images':
            try:
                variant_pk = int(request.POST.get('variant_pk', 0))
            except (TypeError, ValueError):
                variant_pk = 0
            v = variants.filter(pk=variant_pk).first()
            if not v:
                messages.error(request, f'Variant {variant_pk} not found in group.')
                return redirect('ebay_manager:variant_group_detail', group_key=group_key)
            try:
                from non_sports_cards.r2_utils import get_r2_images, _cache
                _cache.clear()
                # Re-scan the variant's R2 subfolder. For flat groups the
                # subfolder name is the last URL segment of the SKU
                # (e.g. box-1 for SKU GROUP-BOX-1). For nested groups we
                # already stored image_urls whose common prefix we reuse.
                if v.parent_r2_prefix and v.image_urls:
                    # Derive the leaf folder from the first existing image URL
                    sample = v.image_urls[0]
                    # Strip CDN base, keep the R2 key, drop the filename
                    from urllib.parse import urlparse
                    path = urlparse(sample).path.lstrip('/')
                    r2_folder = path.rsplit('/', 1)[0] + '/'
                else:
                    # Fallback: parent_prefix/<variant-name>
                    slug = (v.sku or '').split('-')[-1].lower() or 'box-1'
                    r2_folder = f"{v.parent_r2_prefix.rstrip('/')}/{slug}/"

                images = get_r2_images(r2_folder)
                image_urls = [i.get('url', '') for i in images if i.get('url')]
                if not image_urls:
                    messages.warning(request, f'No images found under {r2_folder}')
                    return redirect('ebay_manager:variant_group_detail', group_key=group_key)

                v.image_urls = image_urls
                v.last_synced = timezone.now()
                v.save(update_fields=['image_urls', 'last_synced', 'updated_at'])

                # If this variant is live on eBay, PUT the new imageUrls
                # to the eBay inventory item too.
                if v.status == 'active' and v.sku:
                    import requests as _requests
                    from .services.api_client import get_user_token
                    tok = get_user_token()
                    if tok:
                        headers = {
                            'Authorization': f'Bearer {tok}',
                            'Content-Type': 'application/json',
                            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
                            'Content-Language': 'en-US',
                        }
                        url = f'https://api.ebay.com/sell/inventory/v1/inventory_item/{v.sku}'
                        g = _requests.get(url, headers=headers, timeout=20)
                        if g.status_code == 200:
                            item = g.json()
                            item.setdefault('product', {})['imageUrls'] = image_urls[:24]
                            p = _requests.put(url, headers=headers, json=item, timeout=30)
                            if p.status_code not in (200, 201, 204):
                                messages.warning(request, f'Image update saved locally but eBay PUT failed: {p.status_code} {p.text[:200]}')
                            else:
                                messages.success(request, f'{v.variant_name}: refreshed {len(image_urls)} images (DB + eBay).')
                                return redirect('ebay_manager:variant_group_detail', group_key=group_key)
                messages.success(request, f'{v.variant_name}: refreshed {len(image_urls)} images in DB.')
            except Exception as e:
                messages.error(request, f'Refresh images failed: {e}')
            return redirect('ebay_manager:variant_group_detail', group_key=group_key)

        elif action == 'delete_group':
            count = variants.count()
            variants.delete()
            messages.success(request, f'Deleted {count} variant drafts.')
            return redirect('ebay_manager:listings')

    # Build per-variant image data
    variant_data = []
    total_images = 0
    for v in variants:
        images = v.image_urls or []
        # Handle both list-of-dicts and list-of-strings
        image_list = []
        for img in images:
            if isinstance(img, dict):
                image_list.append(img.get('url', ''))
            else:
                image_list.append(img)
        total_images += len(image_list)
        variant_data.append({
            'listing': v,
            'images': image_list,
            'image_count': len(image_list),
        })

    total_value = sum(float(v.price) for v in variants)

    return render(request, 'ebay_manager/variant_group_detail.html', {
        'group_key': group_key,
        'variants': variant_data,
        'first': first,
        'total_value': total_value,
        'total_images': total_images,
        'variant_count': variants.count(),
        'all_draft': all(v.status == 'draft' for v in variants),
        'all_active': all(v.status == 'active' for v in variants),
    })


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
        listing.quantity = int(request.POST.get('quantity', listing.quantity) or 1)
        listing.item_specifics = _parse_item_specifics(request.POST)
        listing.packaging_config = request.POST.get('packaging_config', listing.packaging_config)
        listing.package_length = int(request.POST.get('package_length', listing.package_length) or 0)
        listing.package_width = int(request.POST.get('package_width', listing.package_width) or 0)
        listing.package_height = int(request.POST.get('package_height', listing.package_height) or 0)
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
