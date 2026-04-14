"""Sync active eBay listings into the local database."""
import requests
from django.utils import timezone
from .api_client import get_user_token


SELL_ITEMS_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item'
OFFER_URL = 'https://api.ebay.com/sell/inventory/v1/offer'
# Use the Trading API via REST for active listings
ACTIVE_LISTINGS_URL = 'https://api.ebay.com/sell/marketing/v1/ad_campaign'


def fetch_active_listings():
    """Fetch all active listings using the Sell Fulfillment completed sales
    and the Browse API for active items by seller."""
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured.")

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
    }

    # Use the sell/inventory offer endpoint to get active offers
    offers = []
    offset = 0
    limit = 100

    while True:
        resp = requests.get(
            f'{OFFER_URL}?limit={limit}&offset={offset}',
            headers=headers, timeout=20
        )
        if resp.status_code == 200:
            data = resp.json()
            offers.extend(data.get('offers', []))
            total = data.get('total', 0)
            offset += limit
            if offset >= total:
                break
        elif resp.status_code == 404:
            # No offers found
            break
        else:
            resp.raise_for_status()

    # Also try to get inventory items for any that don't have offers
    items = []
    offset = 0
    while True:
        resp = requests.get(
            f'{SELL_ITEMS_URL}?limit={limit}&offset={offset}',
            headers=headers, timeout=20
        )
        if resp.status_code == 200:
            data = resp.json()
            items.extend(data.get('inventoryItems', []))
            total = data.get('total', 0)
            offset += limit
            if offset >= total:
                break
        elif resp.status_code == 404:
            break
        else:
            resp.raise_for_status()

    return {'offers': offers, 'items': items}


def fetch_seller_list():
    """Fetch active listings using Browse API search by seller."""
    from .api_client import get_app_token

    token = get_app_token()
    if not token:
        raise PermissionError("Browse API not configured.")

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
    }

    listings = []
    offset = 0
    limit = 50

    while True:
        resp = requests.get(
            'https://api.ebay.com/buy/browse/v1/item_summary/search',
            headers=headers,
            params={
                'q': 'sams.collectibles',
                'filter': 'sellers:{sams.collectibles}',
                'limit': str(limit),
                'offset': str(offset),
            },
            timeout=20
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('itemSummaries', [])
            listings.extend(items)
            total = data.get('total', 0)
            offset += limit
            if offset >= total or not items:
                break
        elif resp.status_code == 404:
            break
        else:
            resp.raise_for_status()

    return listings


def sync_active_listings():
    """Pull active listings from eBay and sync to local DB."""
    from ebay_manager.models import EbayListing

    # Try Browse API seller search first (doesn't need user oauth for reading)
    browse_listings = fetch_seller_list()

    created = 0
    updated = 0

    for item in browse_listings:
        item_id = item.get('itemId', '')
        if not item_id:
            continue

        # Extract the legacy item ID (numeric) from the full item ID
        # eBay Browse API returns IDs like "v1|123456789|0"
        legacy_id = item_id.split('|')[1] if '|' in item_id else item_id

        price_val = item.get('price', {}).get('value', '0')
        image_url = item.get('image', {}).get('imageUrl', '')
        thumbnails = item.get('thumbnailImages', [])
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

    # Also sync from Inventory API if user oauth is available
    try:
        inv_data = fetch_active_listings()
        for offer in inv_data.get('offers', []):
            offer_id = offer.get('offerId', '')
            listing_id = offer.get('listing', {}).get('listingId', '')
            sku = offer.get('sku', '')
            price_val = offer.get('pricingSummary', {}).get('price', {}).get('value', '0')
            status = offer.get('status', '')

            if not listing_id:
                continue

            status_map = {
                'ACTIVE': 'active',
                'ENDED': 'ended',
            }

            listing, was_created = EbayListing.objects.update_or_create(
                ebay_item_id=listing_id,
                defaults={
                    'title': offer.get('listing', {}).get('title', '')[:80] or f'SKU: {sku}',
                    'price': float(price_val),
                    'sku': sku,
                    'status': status_map.get(status, 'active'),
                    'last_synced': timezone.now(),
                }
            )
            if was_created:
                created += 1
            else:
                updated += 1
    except Exception:
        pass  # Inventory API may not have data if seller uses listing tool

    return {'created': created, 'updated': updated, 'total': len(browse_listings)}
