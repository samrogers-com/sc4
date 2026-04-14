"""Sync active eBay listings into the local database."""
import requests
from django.utils import timezone
from .api_client import get_app_token

SELLER_NAME = 'sams.collectibles'

# Broad search terms to cover all inventory categories
SEARCH_QUERIES = [
    'star wars',
    'star trek',
    'trading cards',
    'movie poster',
    'comic book',
    'wax box',
    'sticker',
    'topps',
    'fleer',
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

    return {'created': created, 'updated': updated, 'total': len(browse_listings)}
