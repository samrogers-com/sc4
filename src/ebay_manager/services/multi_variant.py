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


def discover_variants(r2_prefix, series_filter=None):
    """Discover variant subfolders and their images from R2.

    Supports three folder depths:
        Flat:   space-1999/box-1/            (images here)
        Nested: a-new-hope-77/series-1/1star/102/      (images here)
                a-new-hope-77/series-5/photos/         (images here)

    The scanner walks down until it finds leaf folders containing images.
    For the nested case (sets), structure is:
        {prefix}/{series}/{condition}/{set_number}/{images}

    Args:
        r2_prefix: Parent folder (e.g. 'trading-cards/boxes/space-1999'
                   or 'trading-cards/sets/star-wars/a-new-hope-77')
        series_filter: Optional series subfolder to limit to
                       (e.g. 'series-1'). Only variants under this
                       subfolder are returned.

    Returns:
        List of dicts with keys: name, display, series, condition,
        set_number, folder_path, images, image_count
    """
    from non_sports_cards.r2_utils import get_r2_folders, get_r2_images

    prefix = r2_prefix if r2_prefix.endswith('/') else r2_prefix + '/'
    top_folders = get_r2_folders(prefix)

    if series_filter:
        top_folders = [f for f in top_folders if f == series_filter]

    variants = []
    for folder in sorted(top_folders):
        _scan_folder(prefix, folder, None, None, variants, r2_prefix,
                     get_r2_folders, get_r2_images)

    return variants


def _scan_folder(prefix, folder, series, condition, variants,
                 r2_prefix, get_r2_folders, get_r2_images):
    """Recursively scan R2 folders to find leaf image folders.

    Walks down until a folder has images but no subfolders, then adds
    it as a variant. Tracks series and condition context from parent folders.

    Folder structure examples:
        boxes:  prefix/box-1/           -> series=None, condition=None
        sets:   prefix/series-1/1star/102/  -> series=series-1, condition=1star
    """
    folder_prefix = f"{prefix}{folder}/"
    sub_folders = get_r2_folders(folder_prefix)
    images = get_r2_images(folder_prefix)
    image_urls = [img.get('url', '') for img in images if img.get('url')]

    if sub_folders:
        # Not a leaf — go deeper
        for sub in sorted(sub_folders):
            # Determine context: is this a series, condition, or set number folder?
            new_series = series
            new_condition = condition
            if series is None and folder.startswith('series'):
                new_series = folder
            elif series and condition is None:
                new_condition = folder
            _scan_folder(folder_prefix, sub, new_series, new_condition,
                         variants, r2_prefix, get_r2_folders, get_r2_images)
    elif image_urls:
        # Leaf folder with images — this is a variant
        if series and condition:
            # Nested set: series-1/1star/102
            set_number = folder
            condition_display = _format_condition(condition)
            display = f"{condition_display} #{set_number}"
            name = f"{series}/{condition}/{folder}"
            folder_path = f"{prefix}{folder}".replace('//', '/')
        elif series:
            # Series subfolder with images directly (e.g. series-5/photos)
            display = folder.replace('-', ' ').title()
            name = f"{series}/{folder}"
            set_number = None
            folder_path = f"{prefix}{folder}".replace('//', '/')
        else:
            # Flat: box-1, box-2
            display = folder.replace('-', ' ').title()
            name = folder
            set_number = None
            condition = None
            folder_path = f"{prefix}{folder}".replace('//', '/')

        variants.append({
            'name': name,
            'display': display,
            'series': series,
            'condition': condition,
            'set_number': set_number if (series and condition) else None,
            'folder_path': folder_path,
            'images': image_urls,
            'image_count': len(image_urls),
        })


def _format_condition(condition):
    """Format a condition folder name for display.

    '1star' -> '1-Star', '2star' -> '2-Star', 'mixed' -> 'Mixed'
    """
    if condition == 'mixed':
        return 'Mixed'
    m = re.match(r'^(\d+)star$', condition)
    if m:
        return f"{m.group(1)}-Star"
    return condition.replace('-', ' ').title()


def discover_series(r2_prefix):
    """Discover top-level series subfolders that contain nested variants.

    Returns a list of series names if the R2 prefix has nested structure,
    or an empty list if variants are flat (no series grouping).

    Args:
        r2_prefix: Parent folder (e.g. 'trading-cards/sets/star-wars/a-new-hope-77')

    Returns:
        List of strings: ['series-1', 'series-2', 'series-5'] or []
    """
    from non_sports_cards.r2_utils import get_r2_folders

    prefix = r2_prefix if r2_prefix.endswith('/') else r2_prefix + '/'
    subfolders = get_r2_folders(prefix)

    series = []
    for folder in sorted(subfolders):
        # Check if this folder has sub-subfolders (making it a series grouping)
        sub_subfolders = get_r2_folders(f"{prefix}{folder}/")
        if sub_subfolders:
            series.append(folder)

    return series


# Folder slug -> full display name
# Folder names now use descriptive slugs with year suffix:
#   a-new-hope-77, empire-strikes-back-80, return-of-the-jedi-83
FOLDER_DISPLAY_NAMES = {
    'a-new-hope-77': 'A New Hope (1977)',
    'empire-strikes-back-80': 'The Empire Strikes Back (1980)',
    'return-of-the-jedi-83': 'Return of the Jedi (1983)',
    'tpm': 'The Phantom Menace',
    'aotc': 'Attack of the Clones',
    'rots': 'Revenge of the Sith',
    'tng': 'The Next Generation',
    'ds9': 'Deep Space Nine',
    'tos': 'The Original Series',
}


def expand_folder_name(slug):
    """Expand a folder slug to its full display name.

    Args:
        slug: Folder name like 'a-new-hope-77', 'empire-strikes-back-80'

    Returns:
        Full name like 'A New Hope (1977)' or the title-cased slug if unknown.
    """
    return FOLDER_DISPLAY_NAMES.get(slug.lower(), slug.replace('-', ' ').title())


def create_multi_variant_listing(title, variants, specs, prices,
                                  category_id='261035',
                                  condition_id='7000',
                                  description_html='',
                                  fulfillment_policy_id='119108501015',
                                  ship_weight_oz=24,
                                  package_dims=None,
                                  r2_prefix='',
                                  display_overrides=None):
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

    # eBay inventory-item product.description has a 4000-char limit and is
    # not shown to buyers (the offer's listingDescription is). When the HTML
    # exceeds the cap, fall back to the title here.
    inv_description = description_html or title
    if len(inv_description) > 4000:
        inv_description = title

    # Apply display-name overrides (keyed by variant name) so existing custom
    # labels like "Box #0728 of 4000" are preserved on eBay and the DB
    # instead of being replaced by default "Box 1" / "Box 2".
    if display_overrides:
        for v in variants:
            override = display_overrides.get(v['name'])
            if override:
                v['display'] = override

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
                'description': inv_description,
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
        'description': inv_description,
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

    # Step 5: Save DB records for each variant
    _save_variant_records(
        group_key=group_key,
        title=title,
        variants=variants,
        variant_skus=variant_skus,
        prices=prices,
        specs=specs,
        category_id=category_id,
        condition_id=condition_id,
        description_html=description_html,
        r2_prefix=r2_prefix,
        listing_id=listing_id,
        status='active',
        ship_weight_oz=ship_weight_oz,
        package_dims=package_dims,
        fulfillment_policy_id=fulfillment_policy_id,
    )

    return {
        'listing_id': listing_id,
        'group_key': group_key,
        'variant_skus': variant_skus,
        'offer_ids': offer_ids,
    }


def save_variant_drafts(title, variants, specs, prices, category_id='261035',
                        condition_id='7000', description_html='',
                        r2_prefix='', ship_weight_oz=24, package_dims=None,
                        fulfillment_policy_id='119108501015', user=None):
    """Save multi-variant listing as drafts in the database (no eBay push).

    Creates one EbayListing per variant with is_variant=True and a shared
    group_key. Can be published later from the variant group detail page.

    Returns: dict with group_key, variant_count
    """
    slug = re.sub(r'[^a-zA-Z0-9]', '', title[:20]).upper()
    group_key = f"GRP-{slug}"

    _save_variant_records(
        group_key=group_key,
        title=title,
        variants=variants,
        variant_skus={v['name']: f"{slug}-{v['name'].upper()}" for v in variants},
        prices=prices,
        specs=specs,
        category_id=category_id,
        condition_id=condition_id,
        description_html=description_html,
        r2_prefix=r2_prefix,
        listing_id=None,
        status='draft',
        ship_weight_oz=ship_weight_oz,
        package_dims=package_dims,
        fulfillment_policy_id=fulfillment_policy_id,
        user=user,
    )

    return {'group_key': group_key, 'variant_count': len(variants)}


def _save_variant_records(group_key, title, variants, variant_skus, prices,
                          specs, category_id, condition_id, description_html,
                          r2_prefix, listing_id, status, ship_weight_oz,
                          package_dims, fulfillment_policy_id, user=None):
    """Save EbayListing records for each variant in a group.

    Creates or updates one record per variant with shared group_key.
    """
    from ebay_manager.models import EbayListing

    # `ebay_item_id` has a UNIQUE constraint, but a multi-variant group shares
    # one listing id across all variants. Assign the id only to the first
    # variant; leave the rest null so update_or_create doesn't collide.
    for idx, variant in enumerate(variants):
        sku = variant_skus.get(variant['name'], '')
        price = prices.get(variant['name'], prices.get('default', 0))
        image_urls = variant.get('images', [])

        # Build item specifics
        item_specs = dict(specs) if specs else {}

        variant_item_id = listing_id if (idx == 0 and listing_id) else None
        listing_url = f'https://www.ebay.com/itm/{listing_id}' if listing_id else None

        EbayListing.objects.update_or_create(
            group_key=group_key,
            variant_name=variant['display'],
            defaults={
                'title': title,
                'price': price,
                'sku': sku,
                'status': status,
                'is_variant': True,
                'parent_r2_prefix': r2_prefix,
                'category_id': category_id,
                'condition_id': condition_id,
                'description_html': description_html,
                'image_urls': image_urls,
                'item_specifics': item_specs,
                'ebay_item_id': variant_item_id,
                'ebay_listing_url': listing_url,
                'listed_at': timezone.now() if status == 'active' else None,
                'last_synced': timezone.now() if status == 'active' else None,
                'weight_lbs': ship_weight_oz // 16,
                'weight_oz': ship_weight_oz % 16,
                'shipping_service': 'USPSGroundAdvantage',
                'created_by': user,
            }
        )


def add_variant_to_group(group_key, variant, price, r2_prefix=''):
    """Add a new variant to an existing multi-variant group.

    Creates the eBay inventory item and offer, updates the item group,
    and saves a new EbayListing record.

    Args:
        group_key: Existing group key
        variant: Dict with 'name', 'display', 'images'
        price: Price for the new variant
        r2_prefix: Parent R2 folder

    Returns: dict with sku, offer_id
    """
    from ebay_manager.models import EbayListing

    # Get an existing variant to copy settings from
    existing = EbayListing.objects.filter(group_key=group_key).first()
    if not existing:
        raise Exception(f"No existing variants found for group {group_key}")

    headers = _get_headers()
    slug = group_key.replace('GRP-', '')
    sku = f"{slug}-{variant['name'].upper()}"

    # Build aspects from existing variant
    aspects = {}
    for key, value in (existing.item_specifics or {}).items():
        if value:
            aspects[key] = [value] if isinstance(value, str) else value
    aspects['Box'] = [variant['display']]

    # Inventory item description has a 4000-char cap (see create_multi_variant_listing).
    inv_description = existing.description_html or existing.title
    if len(inv_description) > 4000:
        inv_description = existing.title

    # Create inventory item
    payload = {
        'availability': {'shipToLocationAvailability': {'quantity': 1}},
        'condition': 'NEW',
        'product': {
            'title': existing.title,
            'description': inv_description,
            'imageUrls': variant['images'][:24],
            'aspects': aspects,
        },
        'packageWeightAndSize': {
            'weight': {'value': existing.ship_weight_oz, 'unit': 'OUNCE'},
        },
    }

    resp = requests.put(f'{INVENTORY_ITEM_URL}/{sku}', headers=headers, json=payload, timeout=20)
    if resp.status_code not in (200, 201, 204):
        raise Exception(f"Failed to create variant {sku}: {resp.status_code} {resp.text[:300]}")

    # Create offer
    offer_payload = {
        'sku': sku,
        'marketplaceId': 'EBAY_US',
        'format': 'FIXED_PRICE',
        'listingDescription': existing.description_html or existing.title,
        'availableQuantity': 1,
        'categoryId': existing.category_id,
        'pricingSummary': {'price': {'value': str(price), 'currency': 'USD'}},
        'listingPolicies': {
            'fulfillmentPolicyId': existing.fulfillment_policy_id,
            'paymentPolicyId': DEFAULT_POLICIES['payment_policy_id'],
            'returnPolicyId': DEFAULT_POLICIES['return_policy_id'],
        },
        'merchantLocationKey': 'SC-DEFAULT',
    }

    resp2 = requests.post(OFFER_URL, headers=headers, json=offer_payload, timeout=20)
    if resp2.status_code not in (200, 201):
        raise Exception(f"Failed to create offer: {resp2.status_code} {resp2.text[:300]}")
    offer_id = resp2.json().get('offerId', '')

    # Update the item group to include new variant
    # First get existing group data
    group_resp = requests.get(f'{ITEM_GROUP_URL}/{group_key}', headers=headers, timeout=20)
    if group_resp.status_code == 200:
        group_data = group_resp.json()
        existing_skus = group_data.get('variantSKUs', [])
        existing_skus.append(sku)
        existing_values = group_data.get('variesBy', {}).get('specifications', [{}])[0].get('values', [])
        existing_values.append(variant['display'])

        group_data['variantSKUs'] = existing_skus
        group_data['variesBy']['specifications'][0]['values'] = existing_values

        requests.put(f'{ITEM_GROUP_URL}/{group_key}', headers=headers, json=group_data, timeout=20)

    # Save DB record
    EbayListing.objects.create(
        title=existing.title,
        price=price,
        sku=sku,
        status='active',
        is_variant=True,
        group_key=group_key,
        variant_name=variant['display'],
        parent_r2_prefix=r2_prefix or existing.parent_r2_prefix,
        category_id=existing.category_id,
        condition_id=existing.condition_id,
        description_html=existing.description_html,
        image_urls=variant['images'],
        item_specifics=existing.item_specifics,
        listed_at=timezone.now(),
        last_synced=timezone.now(),
    )

    return {'sku': sku, 'offer_id': offer_id}
