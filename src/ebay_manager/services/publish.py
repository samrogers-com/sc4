"""
Publish listings to eBay via the Inventory API.

Flow for creating a listing on eBay:
1. Create/update inventory item (product info, images, weight)
2. Create an offer (price, policies, category, listing details)
3. Either publish the offer (goes live) or leave it as draft

eBay Inventory API docs:
https://developer.ebay.com/api-docs/sell/inventory/overview.html

Sam's default policies (from sell.account API):
- Shipping: "NS Boxes Calculated: USPS Ground Adv" (119108501015)
  or "Calculated – Trading Cards Boxes" (282295444015)
- Payment: "Combine shipping Payments Policy" (238949740015)
- Return: "30 days money back" (195880479015)
"""
import json
import requests
from django.utils import timezone
from .api_client import get_user_token

INVENTORY_ITEM_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item'
OFFER_URL = 'https://api.ebay.com/sell/inventory/v1/offer'
PUBLISH_URL = 'https://api.ebay.com/sell/inventory/v1/offer/{offerId}/publish'

# Sam's default policy IDs — fulfillment selected by packaging_config
DEFAULT_POLICIES = {
    'payment_policy_id': '238949740015',       # Combine shipping
    'return_policy_id': '195880479015',        # 30 days money back
}


def _get_headers():
    """Get authenticated headers for eBay API calls."""
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured or token expired.")
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
        'Content-Language': 'en-US',
    }


def _generate_sku(listing):
    """Generate a unique SKU for the inventory item."""
    if listing.sku:
        return listing.sku
    # Use the listing PK as a fallback SKU
    return f"SC-{listing.pk}"


def create_inventory_item(listing):
    """Create or update an inventory item on eBay.

    This sets the product info, images, and package weight.
    The SKU is the unique key for inventory items.

    Returns: SKU string
    """
    headers = _get_headers()
    sku = _generate_sku(listing)

    # Build image URLs list (eBay needs full URLs)
    image_urls = []
    for url in (listing.image_urls or []):
        if isinstance(url, dict):
            image_urls.append(url.get('url', ''))
        elif isinstance(url, str):
            image_urls.append(url)
    image_urls = [u for u in image_urls if u]

    # Build the inventory item payload
    package_info = {
        'weight': {
            'value': listing.ship_weight_oz,
            'unit': 'OUNCE',
        }
    }

    # Add box dimensions if known from packaging config
    dims = listing.box_dimensions
    if dims:
        package_info['dimensions'] = {
            'length': dims['length'],
            'width': dims['width'],
            'height': dims['height'],
            'unit': 'INCH',
        }

    # Build item specifics as eBay aspects (name/value pairs)
    aspects = {}
    for key, value in (listing.item_specifics or {}).items():
        if value:
            aspects[key] = [value] if isinstance(value, str) else value

    # Add grading and card condition fields (eBay requires these for card sets)
    if 'Graded' not in aspects:
        aspects['Graded'] = ['No']
    if 'Professional Grader' not in aspects:
        aspects['Professional Grader'] = ['N/A']
    if 'Card Condition' not in aspects:
        aspects['Card Condition'] = ['Near Mint or Better']

    product = {
        'title': listing.title,
        'description': listing.description_html or listing.title,
        'imageUrls': image_urls[:24],  # eBay max 24 images
    }
    if aspects:
        product['aspects'] = aspects

    payload = {
        'availability': {
            'shipToLocationAvailability': {
                'quantity': listing.quantity,
            }
        },
        'condition': _get_condition_enum(listing.condition_id, listing.category_id),
        'conditionDescriptors': _get_condition_descriptors(listing.condition_id, listing.category_id, listing.item_specifics),
        'product': product,
        'packageWeightAndSize': package_info,
    }

    # Create or replace inventory item (PUT with SKU in URL)
    resp = requests.put(
        f'{INVENTORY_ITEM_URL}/{sku}',
        headers=headers,
        json=payload,
        timeout=20,
    )

    if resp.status_code in (200, 201, 204):
        # Update listing with SKU
        if not listing.sku:
            listing.sku = sku
            listing.save(update_fields=['sku'])
        return sku
    else:
        error_msg = resp.text[:500]
        raise Exception(f"Failed to create inventory item: {resp.status_code} {error_msg}")


def create_or_update_offer(listing, sku):
    """Create or update an offer for the inventory item.

    An offer ties the inventory item to listing policies (shipping,
    payment, returns) and category. If an offer already exists for
    this SKU, it updates the existing one.

    Returns: offer_id string
    """
    headers = _get_headers()

    payload = {
        'sku': sku,
        'marketplaceId': 'EBAY_US',
        'format': 'FIXED_PRICE',
        'listingDescription': listing.description_html or listing.title,
        'availableQuantity': listing.quantity,
        'categoryId': listing.category_id or '261035',
        'pricingSummary': {
            'price': {
                'value': str(listing.price),
                'currency': 'USD',
            }
        },
        'listingPolicies': {
            'fulfillmentPolicyId': listing.fulfillment_policy_id,
            'paymentPolicyId': DEFAULT_POLICIES['payment_policy_id'],
            'returnPolicyId': DEFAULT_POLICIES['return_policy_id'],
        },
        'merchantLocationKey': 'SC-DEFAULT',
    }

    # Check if offer already exists for this SKU
    existing_resp = requests.get(
        f'{OFFER_URL}?sku={sku}',
        headers=headers, timeout=20,
    )
    if existing_resp.status_code == 200:
        offers = existing_resp.json().get('offers', [])
        if offers:
            # Update existing offer
            offer_id = offers[0]['offerId']
            # Remove sku and marketplaceId from update payload (can't change)
            update_payload = {k: v for k, v in payload.items() if k not in ('sku', 'marketplaceId')}
            resp = requests.put(
                f'{OFFER_URL}/{offer_id}',
                headers=headers, json=update_payload, timeout=20,
            )
            if resp.status_code in (200, 204):
                return offer_id
            else:
                raise Exception(f"Failed to update offer: {resp.status_code} {resp.text[:500]}")

    # Create new offer
    resp = requests.post(
        OFFER_URL, headers=headers, json=payload, timeout=20,
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        return data.get('offerId', '')
    else:
        raise Exception(f"Failed to create offer: {resp.status_code} {resp.text[:500]}")


def publish_offer(offer_id):
    """Publish an offer to make it a live eBay listing.

    Returns: listing_id (eBay item ID)
    """
    headers = _get_headers()

    resp = requests.post(
        PUBLISH_URL.format(offerId=offer_id),
        headers=headers,
        timeout=20,
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        return data.get('listingId', '')
    else:
        error_msg = resp.text[:500]
        raise Exception(f"Failed to publish offer: {resp.status_code} {error_msg}")


def send_to_ebay_drafts(listing):
    """Push a listing to eBay as a draft (not published).

    Creates the inventory item and offer but does NOT publish.
    The listing appears in Seller Hub > Drafts.

    Returns: dict with sku, offer_id
    """
    sku = create_inventory_item(listing)
    offer_id = create_or_update_offer(listing, sku)

    # Update local listing status
    listing.status = 'pending'
    listing.last_synced = timezone.now()
    listing.save(update_fields=['status', 'last_synced'])

    return {'sku': sku, 'offer_id': offer_id}


def publish_to_ebay(listing):
    """Push a listing to eBay as a live active listing.

    Creates inventory item, offer, and publishes immediately.

    Returns: dict with sku, offer_id, listing_id, ebay_url
    """
    sku = create_inventory_item(listing)
    offer_id = create_or_update_offer(listing, sku)
    listing_id = publish_offer(offer_id)

    # Update local listing
    listing.status = 'active'
    listing.ebay_item_id = listing_id
    listing.ebay_listing_url = f'https://www.ebay.com/itm/{listing_id}'
    listing.listed_at = timezone.now()
    listing.last_synced = timezone.now()
    listing.save(update_fields=[
        'status', 'ebay_item_id', 'ebay_listing_url', 'listed_at', 'last_synced'
    ])

    return {
        'sku': sku,
        'offer_id': offer_id,
        'listing_id': listing_id,
        'ebay_url': f'https://www.ebay.com/itm/{listing_id}',
    }


def _get_condition_descriptors(condition_id, category_id='', item_specifics=None):
    """Get condition descriptors required for certain categories.

    Category 183050 (Complete Sets) requires:
    - Condition 4000 (Ungraded): Card Condition descriptor (40001)
      Values: 400010=Near mint or better, 400011=Excellent, 400012=Very good, 400013=Poor
    - Condition 2750 (Graded): Professional Grader (27501) + Grade (27502)
    """
    cid = str(condition_id)
    cat = str(category_id)

    # Ungraded card sets — Card Condition required
    if cat in ('183050', '183052') and cid in ('4000', '7000', '1000'):
        card_cond = '400010'  # Default: Near mint or better
        if item_specifics:
            card_cond = item_specifics.get('card_condition', '400010')
        return [
            {
                'name': '40001',
                'values': [card_cond],
            }
        ]

    return []


def _get_condition_enum(condition_id, category_id=''):
    """Get eBay condition enum for the Inventory API.

    The Inventory API uses string enums like 'NEW', 'USED_EXCELLENT', etc.
    Some categories don't allow certain conditions.

    Valid enums: NEW, LIKE_NEW, NEW_OTHER, NEW_WITH_DEFECTS,
    MANUFACTURER_REFURBISHED, CERTIFIED_REFURBISHED, EXCELLENT_REFURBISHED,
    VERY_GOOD_REFURBISHED, GOOD_REFURBISHED, SELLER_REFURBISHED,
    USED_EXCELLENT, USED_VERY_GOOD, USED_GOOD, USED_ACCEPTABLE, FOR_PARTS_OR_NOT_WORKING
    """
    # Categories that don't allow NEW (Complete Sets, Singles)
    UNGRADED_CATEGORIES = {'183050', '183052'}
    cid = str(condition_id)

    if str(category_id) in UNGRADED_CATEGORIES:
        if cid in ('7000', '1000'):
            return 'USED_VERY_GOOD'  # Ungraded
        if cid == '4000':
            return 'USED_VERY_GOOD'  # Ungraded
        if cid == '3000':
            return 'USED_GOOD'       # Used
        if cid == '2750':
            return 'USED_EXCELLENT'  # Graded

    mapping = {
        '7000': 'NEW',
        '1000': 'NEW',
        '3000': 'USED_GOOD',
        '4000': 'USED_VERY_GOOD',
        '5000': 'USED_GOOD',
        '6000': 'USED_ACCEPTABLE',
    }
    return mapping.get(cid, 'NEW')
