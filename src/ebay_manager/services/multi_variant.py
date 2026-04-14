"""
Multi-variant eBay listing service.

Creates a single eBay listing with multiple variations (e.g. Box 1,
Box 2, Box 3) where each variant has its own photos, price, and SKU.

Used for pre-1990 items where condition varies between copies.

eBay Inventory API flow for multi-variant:
1. Create individual inventory items (one per variant/box)
2. Create an inventory item group (ties variants together)
3. Create an offer referencing the group
4. Publish the offer

R2 folder structure drives variants:
    trading-cards/boxes/space-1999/
        box-1/ → Variant 1 (SKU: SPACE1999-BOX1)
        box-2/ → Variant 2 (SKU: SPACE1999-BOX2)
        box-3/ → Variant 3
        box-4/ → Variant 4
"""
import re
import requests
from django.utils import timezone
from .api_client import get_user_token, get_app_token

INVENTORY_ITEM_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item'
ITEM_GROUP_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item_group'
OFFER_URL = 'https://api.ebay.com/sell/inventory/v1/offer'

# Default policies
DEFAULT_POLICIES = {
    'payment_policy_id': '238949740015',
    'return_policy_id': '195880479015',
}


def _get_headers():
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured or token expired.")
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
        'Content-Language': 'en-US',
    }


def discover_variants(r2_prefix):
    """Discover variant subfolders and their images from R2.

    Args:
        r2_prefix: Parent folder (e.g. 'trading-cards/boxes/space-1999')

    Returns:
        List of dicts: [{'name': 'box-1', 'display': 'Box 1', 'images': [...urls...]}]
    """
    from non_sports_cards.r2_utils import get_r2_folders, get_r2_images

    prefix = r2_prefix if r2_prefix.endswith('/') else r2_prefix + '/'
    subfolders = get_r2_folders(prefix)

    variants = []
    for folder in sorted(subfolders):
        images = get_r2_images(f"{prefix}{folder}/")
        image_urls = [img.get('url', '') for img in images if img.get('url')]
        if image_urls:
            display = folder.replace('-', ' ').title()
            variants.append({
                'name': folder,
                'display': display,
                'images': image_urls,
                'image_count': len(image_urls),
            })

    return variants


def create_multi_variant_listing(title, variants, specs, prices,
                                  category_id='261035',
                                  condition_id='7000',
                                  description_html='',
                                  fulfillment_policy_id='119108501015',
                                  ship_weight_oz=24,
                                  package_dims=None):
    """Create a multi-variant listing on eBay.

    Args:
        title: Listing title (e.g. "1976 Space 1999 Wax Box Donruss")
        variants: List from discover_variants()
        specs: Dict of item specifics (Manufacturer, Franchise, etc.)
        prices: Dict mapping variant name to price (e.g. {'box-1': 139.95})
        category_id: eBay category
        condition_id: Condition code
        description_html: HTML description
        fulfillment_policy_id: Shipping policy ID
        ship_weight_oz: Shipping weight per variant in ounces
        package_dims: Dict with length/width/height or None

    Returns:
        Dict with listing_id, offer_id, variant_skus
    """
    headers = _get_headers()

    # Generate group key and SKUs
    slug = re.sub(r'[^a-zA-Z0-9]', '', title[:20]).upper()
    group_key = f"GRP-{slug}"
    variant_skus = {}

    # Step 1: Create individual inventory items per variant
    for variant in variants:
        sku = f"{slug}-{variant['name'].upper()}"
        variant_skus[variant['name']] = sku
        price = prices.get(variant['name'], prices.get('default', 99.95))

        # Build aspects with variant-specific aspect
        aspects = {}
        for key, value in (specs or {}).items():
            if value:
                aspects[key] = [value] if isinstance(value, str) else value
        # Add the variation aspect
        aspects['Box'] = [variant['display']]

        package_info = {
            'weight': {'value': ship_weight_oz, 'unit': 'OUNCE'},
        }
        if package_dims:
            package_info['dimensions'] = {
                'length': package_dims['length'],
                'width': package_dims['width'],
                'height': package_dims['height'],
                'unit': 'INCH',
            }

        payload = {
            'availability': {
                'shipToLocationAvailability': {'quantity': 1},
            },
            'condition': 'NEW',
            'product': {
                'title': title,
                'description': description_html or title,
                'imageUrls': variant['images'][:24],
                'aspects': aspects,
            },
            'packageWeightAndSize': package_info,
        }

        resp = requests.put(
            f'{INVENTORY_ITEM_URL}/{sku}',
            headers=headers, json=payload, timeout=20,
        )
        if resp.status_code not in (200, 201, 204):
            raise Exception(f"Failed to create variant {sku}: {resp.status_code} {resp.text[:300]}")

    # Step 2: Create inventory item group
    # All variant images combined for the group listing
    all_images = []
    for v in variants:
        all_images.extend(v['images'][:6])

    group_aspects = {}
    for key, value in (specs or {}).items():
        if value:
            group_aspects[key] = [value] if isinstance(value, str) else value

    group_payload = {
        'title': title,
        'description': description_html or title,
        'imageUrls': all_images[:24],
        'aspects': group_aspects,
        'variantSKUs': list(variant_skus.values()),
        'variesBy': {
            'aspectsImageVariesBy': ['Box'],
            'specifications': [
                {
                    'name': 'Box',
                    'values': [v['display'] for v in variants],
                }
            ],
        },
    }

    resp = requests.put(
        f'{ITEM_GROUP_URL}/{group_key}',
        headers=headers, json=group_payload, timeout=20,
    )
    if resp.status_code not in (200, 201, 204):
        raise Exception(f"Failed to create item group: {resp.status_code} {resp.text[:300]}")

    # Step 3: Create offers for each variant
    offer_ids = []
    for variant in variants:
        sku = variant_skus[variant['name']]
        price = prices.get(variant['name'], prices.get('default', 99.95))

        offer_payload = {
            'sku': sku,
            'marketplaceId': 'EBAY_US',
            'format': 'FIXED_PRICE',
            'listingDescription': description_html or title,
            'availableQuantity': 1,
            'categoryId': category_id,
            'pricingSummary': {
                'price': {'value': str(price), 'currency': 'USD'},
            },
            'listingPolicies': {
                'fulfillmentPolicyId': fulfillment_policy_id,
                'paymentPolicyId': DEFAULT_POLICIES['payment_policy_id'],
                'returnPolicyId': DEFAULT_POLICIES['return_policy_id'],
            },
            'merchantLocationKey': 'SC-DEFAULT',
        }

        # Check for existing offer
        existing = requests.get(f'{OFFER_URL}?sku={sku}', headers=headers, timeout=20)
        if existing.status_code == 200 and existing.json().get('offers'):
            offer_id = existing.json()['offers'][0]['offerId']
            update = {k: v for k, v in offer_payload.items() if k not in ('sku', 'marketplaceId')}
            requests.put(f'{OFFER_URL}/{offer_id}', headers=headers, json=update, timeout=20)
        else:
            resp = requests.post(OFFER_URL, headers=headers, json=offer_payload, timeout=20)
            if resp.status_code in (200, 201):
                offer_id = resp.json().get('offerId', '')
            else:
                raise Exception(f"Failed to create offer for {sku}: {resp.status_code} {resp.text[:300]}")
        offer_ids.append(offer_id)

    # Step 4: Publish the group
    publish_resp = requests.post(
        f'{ITEM_GROUP_URL}/{group_key}/publish',
        headers=headers, timeout=20,
    )

    if publish_resp.status_code not in (200, 201):
        # Try publishing individual offers as fallback
        listing_id = None
        for oid in offer_ids:
            pub = requests.post(f'{OFFER_URL}/{oid}/publish', headers=headers, timeout=20)
            if pub.status_code in (200, 201):
                listing_id = pub.json().get('listingId', '')

        if not listing_id:
            raise Exception(f"Failed to publish: {publish_resp.status_code} {publish_resp.text[:300]}")
    else:
        listing_id = publish_resp.json().get('listingId', '')

    return {
        'listing_id': listing_id,
        'group_key': group_key,
        'variant_skus': variant_skus,
        'offer_ids': offer_ids,
    }
