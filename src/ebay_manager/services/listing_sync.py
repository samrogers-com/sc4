"""Sync active eBay listings into the local database."""
import requests
from django.utils import timezone
from .api_client import get_app_token, get_user_token

SELLER_NAME = 'sams.collectibles'

# Broad single-word searches that cover all active listings
# Tested: these 10 terms find 64 unique listings (58+ active)
SEARCH_QUERIES = [
    'star',
    'box',
    'comic',
    'pack',
    'cards',
    'set',
    'base',
    'sealed',
    'return',
    'wars',
]


def fetch_seller_listings():
    """Fetch all active listings using Browse API seller filter with broad searches."""
    token = get_app_token()
    if not token:
        raise PermissionError("Browse API not configured.")

    headers = {
        'Authorization': f'Bearer {token}',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
    }

    seen_ids = set()
    all_listings = []

    for query in SEARCH_QUERIES:
        offset = 0
        limit = 200

        while True:
            resp = requests.get(
                'https://api.ebay.com/buy/browse/v1/item_summary/search',
                headers=headers,
                params={
                    'q': query,
                    'filter': f'sellers:{{{SELLER_NAME}}}',
                    'limit': str(limit),
                    'offset': str(offset),
                },
                timeout=20
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            items = data.get('itemSummaries', [])
            for item in items:
                item_id = item.get('itemId', '')
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_listings.append(item)

            total = data.get('total', 0)
            offset += limit
            if offset >= total or not items:
                break

    return all_listings


def sync_active_listings():
    """Pull active listings from eBay and sync to local DB."""
    from ebay_manager.models import EbayListing

    browse_listings = fetch_seller_listings()

    created = 0
    updated = 0

    for item in browse_listings:
        item_id = item.get('itemId', '')
        if not item_id:
            continue

        # Extract the legacy item ID (numeric) from "v1|123456789|0"
        legacy_id = item_id.split('|')[1] if '|' in item_id else item_id

        price_val = item.get('price', {}).get('value', '0')
        image_url = item.get('image', {}).get('imageUrl', '')
        additional_images = item.get('additionalImages', [])

        image_urls = [image_url] if image_url else []
        for img in additional_images:
            url = img.get('imageUrl', '')
            if url:
                image_urls.append(url)

        listing, was_created = EbayListing.objects.update_or_create(
            ebay_item_id=legacy_id,
            defaults={
                'title': item.get('title', '')[:80],
                'price': float(price_val),
                'status': 'active',
                'ebay_listing_url': item.get('itemWebUrl', ''),
                'image_urls': image_urls,
                'category_id': item.get('categoryId', ''),
                'condition_id': item.get('conditionId', ''),
                'last_synced': timezone.now(),
            }
        )

        if was_created:
            created += 1
        else:
            updated += 1

    # Enrich with item details (views, watchers) via individual lookups
    enrich_listings_with_details()

    # Cross-reference orders to mark sold items and populate SKUs
    mark_sold_from_orders()

    return {'created': created, 'updated': updated, 'total': len(browse_listings)}


def enrich_listings_with_details():
    """Fetch individual item details for views/watchers on active listings."""
    from ebay_manager.models import EbayListing

    token = get_app_token()
    if not token:
        return

    headers = {
        'Authorization': f'Bearer {token}',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
    }

    active = EbayListing.objects.filter(status='active')
    for listing in active:
        if not listing.ebay_item_id:
            continue
        try:
            # Browse API getItem returns views and watchers
            resp = requests.get(
                f'https://api.ebay.com/buy/browse/v1/item/v1|{listing.ebay_item_id}|0',
                headers=headers, timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                listing.view_count = data.get('uniqueBidderCount', 0)
                # estimatedAvailabilities has watchCount
                for avail in data.get('estimatedAvailabilities', []):
                    listing.watch_count = avail.get('estimatedAvailableQuantity', listing.watch_count)
                # Try to get SKU from localizedAspects or seller info
                sku = data.get('sku', '')
                if sku:
                    listing.sku = sku
                listing.save(update_fields=['view_count', 'watch_count', 'sku'])
        except Exception:
            continue


def mark_sold_from_orders():
    """Cross-reference order line items with listings to mark sold and populate SKUs."""
    from ebay_manager.models import EbayListing, EbayOrder, EbayOrderItem

    # Get all order items with their item IDs
    order_items = EbayOrderItem.objects.select_related('order').all()
    sold_item_ids = set()

    for oi in order_items:
        if oi.ebay_item_id:
            sold_item_ids.add(oi.ebay_item_id)
            # Link order item to listing if not already linked
            if not oi.listing_id:
                listing = EbayListing.objects.filter(ebay_item_id=oi.ebay_item_id).first()
                if listing:
                    oi.listing = listing
                    oi.save(update_fields=['listing'])

            # Update SKU on listing from order data
            if oi.sku:
                EbayListing.objects.filter(
                    ebay_item_id=oi.ebay_item_id, sku__isnull=True
                ).update(sku=oi.sku)
                EbayListing.objects.filter(
                    ebay_item_id=oi.ebay_item_id, sku=''
                ).update(sku=oi.sku)

    # Items that appear in orders but NOT in active listings are sold/ended
    # Create listing records for sold items we don't have yet
    for oi in order_items:
        if not oi.ebay_item_id:
            continue
        if not EbayListing.objects.filter(ebay_item_id=oi.ebay_item_id).exists():
            EbayListing.objects.create(
                ebay_item_id=oi.ebay_item_id,
                title=oi.title[:80],
                price=oi.price,
                sku=oi.sku or '',
                status='sold',
                last_synced=timezone.now(),
            )
