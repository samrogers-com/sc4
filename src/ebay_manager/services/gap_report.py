"""
Gap report service: compares R2 photo inventory with active eBay listings.

Identifies:
- R2 product folders that have photos but no active/draft eBay listing
- Active eBay listings that have no corresponding R2 photos

Used by:
- /ebay/gap-report/ web page (staff-only)
- manage.py ebay_sync --report (nightly CLI)
"""
import re
from django.conf import settings

# R2 CDN base URL for building image URLs
R2_CDN_BASE = getattr(settings, 'R2_CUSTOM_DOMAIN', 'media.samscollectibles.net')

# Product type prefixes to scan in R2
PRODUCT_TYPES = {
    'boxes': 'trading-cards/boxes',
    'sets': 'trading-cards/sets',
    'packs': 'trading-cards/packs',
    'singles': 'trading-cards/singles',
    'binders': 'trading-cards/binders',
}

# Map R2 folder slugs to proper eBay listing titles
# Used when creating listings from the gap report
LISTING_TITLES = {
    '007-goldeneye': '1995 Graffiti James Bond 007 GoldenEye Trading Cards Factory Sealed Box',
    '007-tomorrowneverdies': '1997 Inkworks James Bond 007 Tomorrow Never Dies Factory Sealed Box',
    '007-moonraker': '1979 James Bond 007 Moonraker Cards Box Complete With 36 Unopened Packs',
    'cosmiccardsinauguralimpel': '1991 Impel DC Comics Cosmic Cards Inaugural Edition Factory Sealed Box',
    'disneycollectorcardsimpel91': '1991 Impel Disney Collector Cards Factory Sealed Box',
    'disneycollectorcards2skybox92': '1992 SkyBox Disney Collector Cards Series 2 Factory Sealed Box',
    'the-outer-limits': '1997 DuoCards The Outer Limits Collector Cards Factory Sealed Box',
    'valiant': '1993 Upper Deck The Valiant Era Trading Cards Factory Sealed Box',
    'dune': 'Fleer Dune Trading Cards Wax Box 36 Packs',
    'godzilla-green-1998': '1998 JPP/Amada Godzilla Trading Cards Factory Sealed Box',
    'the-creators-universe': 'Creators of the Universe Trading Card Box Sealed',
    'x-file-s3': '1996 X-Files Season 3 Trading Card Box by Topps New Sealed',
    'x-files-contact': '1996 Intrepid The X Files Contact Trading Card Box Sealed',
    'x-files-s1': '1991 Topps The X Files Volume 1 Trading Card Box',
    'x-files-s2': 'Factory Sealed X-Files Season 2 Premium Trading Card Box TOPPS 1996',
    'x-files-showcase': '1991 Topps The X Files Showcase Volume 1 Trading Card Box',
    'space-1999': '1976 SPACE 1999 WAX BOX (24 MINT PACKS) DONRUSS',
    'wizardofoz-duocards': 'Wizard of Oz Factory Sealed Box Collector 1996 Duo Cards 30 packs',
    'wizardofoz-pacific': 'Wizard of OZ Trading Card Factory Sealed Box 1990 Pacific',
    'casper': 'Casper Trading Cards Fleer 1995 Lot of 5 Packs Unopened',
}


def get_gap_report():
    """Compare R2 photo folders with active eBay listings.

    Returns:
        dict with keys:
            'r2_without_listing': list of dicts with R2 product info
            'listings_without_photos': list of EbayListing objects
            'stats': summary counts
    """
    from ebay_manager.models import EbayListing

    try:
        from non_sports_cards.r2_utils import get_r2_folders, get_r2_folder_thumbnails
    except ImportError:
        return {'r2_without_listing': [], 'listings_without_photos': [], 'stats': {}}

    # Get all active + draft listings
    listings = EbayListing.objects.filter(status__in=['active', 'draft'])
    listing_titles = {l.title.lower(): l for l in listings}

    # Scan R2 for all product folders
    # Note: get_r2_folders returns list of strings, requires trailing slash on prefix
    r2_products = []
    for product_type, prefix in PRODUCT_TYPES.items():
        try:
            folders = get_r2_folders(prefix + '/')
        except Exception:
            continue

        for folder_name in folders:
            if not folder_name:
                continue

            full_prefix = f"{prefix}/{folder_name}"

            # Check for sub-subfolders (e.g. trading-cards/boxes/star-wars/ has sub-products)
            try:
                subfolders = get_r2_folders(full_prefix + '/')
            except Exception:
                subfolders = []

            if subfolders:
                # This is a category folder (e.g. star-wars/), scan its children
                for sub_name in subfolders:
                    sub_prefix = f"{full_prefix}/{sub_name}"
                    r2_products.append({
                        'r2_prefix': sub_prefix,
                        'folder_name': sub_name,
                        'display_name': LISTING_TITLES.get(sub_name, sub_name.replace('-', ' ').title()),
                        'product_type': product_type,
                        'parent': folder_name,
                    })
            else:
                # This is a leaf product folder
                r2_products.append({
                    'r2_prefix': full_prefix,
                    'folder_name': folder_name,
                    'display_name': LISTING_TITLES.get(folder_name, folder_name.replace('-', ' ').title()),
                    'product_type': product_type,
                    'parent': None,
                })

    # Match R2 products against listings using word overlap
    r2_without_listing = []
    matched_r2 = set()

    for product in r2_products:
        folder_words = set(re.split(r'[-_/]', product['folder_name'].lower()))
        folder_words -= {'the', 'a', 'an', 'of', 'and', 'img'}

        matched = False
        for title_lower, listing in listing_titles.items():
            title_words = set(re.split(r'[\s\-]+', title_lower))
            overlap = folder_words & title_words
            if len(overlap) >= 2:
                matched = True
                matched_r2.add(product['r2_prefix'])
                break

        if not matched:
            # Get thumbnail by fetching first image in the folder
            try:
                from non_sports_cards.r2_utils import get_r2_images
                images = get_r2_images(product['r2_prefix'] + '/')
                if images:
                    product['thumbnail_url'] = images[0].get('url', '')
                    product['image_count'] = len(images)
                else:
                    product['thumbnail_url'] = ''
                    product['image_count'] = 0
            except Exception:
                product['thumbnail_url'] = ''
                product['image_count'] = 0

            r2_without_listing.append(product)

    # Find listings without R2 photos
    listings_without_photos = []
    for listing in listings:
        title_words = set(re.split(r'[\s\-]+', listing.title.lower()))
        matched = False
        for product in r2_products:
            folder_words = set(re.split(r'[-_/]', product['folder_name'].lower()))
            folder_words -= {'the', 'a', 'an', 'of', 'and', 'img'}
            overlap = title_words & folder_words
            if len(overlap) >= 2:
                matched = True
                break
        if not matched:
            listings_without_photos.append(listing)

    return {
        'r2_without_listing': r2_without_listing,
        'listings_without_photos': listings_without_photos,
        'stats': {
            'r2_total': len(r2_products),
            'listings_total': listings.count(),
            'r2_unmatched': len(r2_without_listing),
            'listings_unmatched': len(listings_without_photos),
        },
    }
