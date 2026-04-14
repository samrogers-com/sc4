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

# Product data for gap report listings — title, item specifics, default dimensions
# Used to pre-populate the listing create form from the gap report
# Keys are R2 folder slugs
PRODUCT_DATA = {
    '007-goldeneye': {
        'title': '1995 Graffiti James Bond 007 GoldenEye Trading Cards Factory Sealed Box',
        'specs': {'Manufacturer': 'Graffiti', 'Franchise': 'James Bond', 'Set': 'GoldenEye', 'Year Manufactured': '1995', 'Genre': 'Action', 'Movie': 'GoldenEye', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    '007-tomorrowneverdies': {
        'title': '1997 Inkworks James Bond 007 Tomorrow Never Dies Factory Sealed Box',
        'specs': {'Manufacturer': 'Inkworks', 'Franchise': 'James Bond', 'Set': 'Tomorrow Never Dies', 'Year Manufactured': '1997', 'Genre': 'Action', 'Movie': 'Tomorrow Never Dies', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    '007-moonraker': {
        'title': '1979 James Bond 007 Moonraker Cards Box Complete With 36 Unopened Packs',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'James Bond', 'Set': 'Moonraker', 'Year Manufactured': '1979', 'Genre': 'Action', 'Movie': 'Moonraker', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'cosmiccardsinauguralimpel': {
        'title': '1991 Impel DC Comics Cosmic Cards Inaugural Edition Factory Sealed Box',
        'specs': {'Manufacturer': 'Impel', 'Franchise': 'DC Comics', 'Set': 'Cosmic Cards Inaugural Edition', 'Year Manufactured': '1991', 'Genre': 'Sci-Fi', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'disneycollectorcardsimpel91': {
        'title': '1991 Impel Disney Collector Cards Factory Sealed Box',
        'specs': {'Manufacturer': 'Impel', 'Franchise': 'Disney', 'Set': 'Disney Collector Cards', 'Year Manufactured': '1991', 'Genre': 'Fantasy', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'disneycollectorcards2skybox92': {
        'title': '1992 SkyBox Disney Collector Cards Series 2 Factory Sealed Box',
        'specs': {'Manufacturer': 'SkyBox', 'Franchise': 'Disney', 'Set': 'Disney Collector Cards Series 2', 'Year Manufactured': '1992', 'Genre': 'Fantasy', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'the-outer-limits': {
        'title': '1997 DuoCards The Outer Limits Collector Cards Factory Sealed Box',
        'specs': {'Manufacturer': 'DuoCards', 'Franchise': 'The Outer Limits', 'Set': 'The Outer Limits', 'Year Manufactured': '1997', 'Genre': 'Sci-Fi', 'TV Show': 'The Outer Limits', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'valiant': {
        'title': '1993 Upper Deck The Valiant Era Trading Cards Factory Sealed Box',
        'specs': {'Manufacturer': 'Upper Deck', 'Franchise': 'Valiant Comics', 'Set': 'The Valiant Era', 'Year Manufactured': '1993', 'Genre': 'Sci-Fi', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'godzilla-green-1998': {
        'title': '1998 JPP/Amada Godzilla Premium Trading Cards Factory Sealed Box',
        'specs': {'Manufacturer': 'JPP/Amada', 'Franchise': 'Godzilla', 'Set': 'Godzilla', 'Year Manufactured': '1998', 'Genre': 'Sci-Fi', 'Movie': 'Godzilla', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
        'weight_lbs': 1, 'weight_oz': 2,
    },
    'dune': {
        'title': 'Fleer Dune Trading Cards Wax Box 36 Packs',
        'specs': {'Manufacturer': 'Fleer', 'Franchise': 'Dune', 'Set': 'Dune', 'Year Manufactured': '1984', 'Genre': 'Sci-Fi', 'Movie': 'Dune', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'the-creators-universe': {
        'title': 'Creators of the Universe Trading Card Box Sealed',
        'specs': {'Manufacturer': 'Dynamic', 'Franchise': 'Creators of the Universe', 'Set': 'Creators of the Universe', 'Year Manufactured': '1993', 'Genre': 'Sci-Fi', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'x-file-s3': {
        'title': '1996 X-Files Season 3 Trading Card Box by Topps New Sealed',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'The X-Files', 'Set': 'X-Files Season 3', 'Year Manufactured': '1996', 'Genre': 'Sci-Fi', 'TV Show': 'The X-Files', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'x-files-contact': {
        'title': '1996 Intrepid The X Files Contact Trading Card Box Sealed',
        'specs': {'Manufacturer': 'Intrepid', 'Franchise': 'The X-Files', 'Set': 'X-Files Contact', 'Year Manufactured': '1996', 'Genre': 'Sci-Fi', 'TV Show': 'The X-Files', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'x-files-s1': {
        'title': '1991 Topps The X Files Volume 1 Trading Card Box',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'The X-Files', 'Set': 'X-Files Volume 1', 'Year Manufactured': '1995', 'Genre': 'Sci-Fi', 'TV Show': 'The X-Files', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'x-files-s2': {
        'title': 'Factory Sealed X-Files Season 2 Premium Trading Card Box TOPPS 1996',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'The X-Files', 'Set': 'X-Files Season 2', 'Year Manufactured': '1996', 'Genre': 'Sci-Fi', 'TV Show': 'The X-Files', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'x-files-showcase': {
        'title': '1991 Topps The X Files Showcase Volume 1 Trading Card Box',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'The X-Files', 'Set': 'X-Files Showcase', 'Year Manufactured': '1997', 'Genre': 'Sci-Fi', 'TV Show': 'The X-Files', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'space-1999': {
        'title': '1976 SPACE 1999 WAX BOX (24 MINT PACKS) DONRUSS',
        'specs': {'Manufacturer': 'Donruss', 'Franchise': 'Space: 1999', 'Set': 'Space 1999', 'Year Manufactured': '1976', 'Genre': 'Sci-Fi', 'TV Show': 'Space: 1999', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'wizardofoz-duocards': {
        'title': 'Wizard of Oz Factory Sealed Box Collector 1996 Duo Cards 30 packs',
        'specs': {'Manufacturer': 'DuoCards', 'Franchise': 'Wizard of Oz', 'Set': 'Wizard of Oz', 'Year Manufactured': '1996', 'Genre': 'Fantasy', 'Movie': 'The Wizard of Oz', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'wizardofoz-pacific': {
        'title': 'Wizard of OZ Trading Card Factory Sealed Box 1990 Pacific',
        'specs': {'Manufacturer': 'Pacific', 'Franchise': 'Wizard of Oz', 'Set': 'Wizard of Oz', 'Year Manufactured': '1990', 'Genre': 'Fantasy', 'Movie': 'The Wizard of Oz', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'casper': {
        'title': 'Casper Trading Cards Fleer 1995 Lot of 5 Packs Unopened',
        'specs': {'Manufacturer': 'Fleer', 'Franchise': 'Casper', 'Set': 'Casper', 'Year Manufactured': '1995', 'Genre': 'Fantasy', 'Movie': 'Casper', 'Configuration': 'Pack', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    # Star Wars boxes (sub-products under star-wars/)
    'sw-3d': {
        'title': 'Star Wars 3D Trading Cards Box Factory Sealed Topps 3Di Widevision',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Star Wars 3Di Widevision', 'Year Manufactured': '1996', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
        'weight_lbs': 2, 'weight_oz': 1,
    },
    'sw-first-anthology': {
        'title': 'Star Wars CCG Card Game First Anthology Sealed Box Decipher Cards',
        'specs': {'Manufacturer': 'Decipher', 'Franchise': 'Star Wars', 'Set': 'First Anthology', 'Year Manufactured': '1997', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'sw-mastervisions': {
        'title': 'STAR WARS Topps Master Visions Collector Art Cards Premiere Edition',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Master Visions', 'Year Manufactured': '1995', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'sw-rotj-stickers': {
        'title': '1983 Star Wars Return of the Jedi Album Sticker Box 60 Packs Sealed',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Return of the Jedi Stickers', 'Year Manufactured': '1983', 'Genre': 'Sci-Fi', 'Movie': 'Return of the Jedi', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'sw-shadows-of-the-empire': {
        'title': 'Sealed NEW Topps Star Wars Shadow of the Empire Premium Trading Card Box',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Shadows of the Empire', 'Year Manufactured': '1996', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'sw-topps-trilogy-regular': {
        'title': '1997 Topps STAR WARS VEHICLES Factory Sealed Wax Box 36 Packs',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Star Wars Vehicles', 'Year Manufactured': '1997', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'sw-trilogy-merlin': {
        'title': '1997 Merlin Star Wars Trilogy Cards Box',
        'specs': {'Manufacturer': 'Merlin', 'Franchise': 'Star Wars', 'Set': 'Star Wars Trilogy', 'Year Manufactured': '1997', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    # Star Trek boxes (sub-products under star-trek/)
    'deep-space-nine-s1': {
        'title': '1993 SkyBox Star Trek Deep Space Nine Series 1 Sealed Box',
        'specs': {'Manufacturer': 'SkyBox', 'Franchise': 'Star Trek', 'Set': 'Deep Space Nine Series 1', 'Year Manufactured': '1993', 'Genre': 'Sci-Fi', 'TV Show': 'Star Trek: Deep Space Nine', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'master-series': {
        'title': '1993 Skybox Star Trek Edition Master Series Sealed Box',
        'specs': {'Manufacturer': 'SkyBox', 'Franchise': 'Star Trek', 'Set': 'Master Series', 'Year Manufactured': '1993', 'Genre': 'Sci-Fi', 'TV Show': 'Star Trek', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'next-gerneration': {
        'title': '1994 SkyBox Star Trek The Next Generation Season 1 Sealed Box',
        'specs': {'Manufacturer': 'SkyBox', 'Franchise': 'Star Trek', 'Set': 'The Next Generation', 'Year Manufactured': '1994', 'Genre': 'Sci-Fi', 'TV Show': 'Star Trek: The Next Generation', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    'tos-25th-anniversary-series-2': {
        'title': '1991 Impel Star Trek 25th Anniversary Series 2 Trading Cards Sealed Box',
        'specs': {'Manufacturer': 'Impel', 'Franchise': 'Star Trek', 'Set': '25th Anniversary Series 2', 'Year Manufactured': '1991', 'Genre': 'Sci-Fi', 'TV Show': 'Star Trek', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    # Marvel boxes (sub-products under marvel/)
    '1993-masterpieces': {
        'title': '1993 SkyBox Marvel Masterpieces Trading Cards Sealed Box',
        'specs': {'Manufacturer': 'SkyBox', 'Franchise': 'Marvel', 'Set': 'Marvel Masterpieces', 'Year Manufactured': '1993', 'Genre': 'Sci-Fi', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
    # Star Wars sets (sub-products under star-wars/ in sets/)
    'galaxy-s1': {
        'title': '1993 Topps Star Wars Galaxy Series 1 Complete Base Set',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Galaxy Series 1', 'Year Manufactured': '1993', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Set', 'Type': 'Non-Sport Trading Card'},
    },
    'galaxy-s2': {
        'title': '1994 Topps Star Wars Galaxy Series 2 Complete Base Set',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Galaxy Series 2', 'Year Manufactured': '1994', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Set', 'Type': 'Non-Sport Trading Card'},
    },
    'anh': {
        'title': '1977 Topps Star Wars A New Hope Trading Card Sets',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Star Wars Series 1-5', 'Year Manufactured': '1977', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Set', 'Type': 'Non-Sport Trading Card'},
    },
    'esb': {
        'title': '1980 Topps Star Wars Empire Strikes Back Trading Card Sets',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Empire Strikes Back', 'Year Manufactured': '1980', 'Genre': 'Sci-Fi', 'Movie': 'The Empire Strikes Back', 'Configuration': 'Set', 'Type': 'Non-Sport Trading Card'},
    },
    'andy-griffith': {
        'title': '1990 Pacific Andy Griffith Show Complete Trading Card Set',
        'specs': {'Manufacturer': 'Pacific', 'Franchise': 'Andy Griffith Show', 'Set': 'Andy Griffith Show', 'Year Manufactured': '1990', 'Genre': 'Comedy', 'TV Show': 'The Andy Griffith Show', 'Configuration': 'Set', 'Type': 'Non-Sport Trading Card'},
    },
    'chrome-archives': {
        'title': '1999 Topps Star Wars Chrome Archives Complete Trading Card Set',
        'specs': {'Manufacturer': 'Topps', 'Franchise': 'Star Wars', 'Set': 'Chrome Archives', 'Year Manufactured': '1999', 'Genre': 'Sci-Fi', 'Movie': 'Star Wars', 'Configuration': 'Set', 'Type': 'Non-Sport Trading Card'},
    },
    'marveluniverse-91': {
        'title': '1991 Impel Marvel Universe Series II Trading Cards Sealed Box',
        'specs': {'Manufacturer': 'Impel', 'Franchise': 'Marvel', 'Set': 'Marvel Universe Series II', 'Year Manufactured': '1991', 'Genre': 'Sci-Fi', 'Configuration': 'Box', 'Type': 'Non-Sport Trading Card', 'Features': 'Factory Sealed'},
    },
}

# Default box dimensions for sealed boxes (9x6x4 is standard wax box size)
DEFAULT_BOX_DIMS = {'length': 9, 'width': 6, 'height': 4}

# Legacy helper for templates that reference LISTING_TITLES
LISTING_TITLES = {k: v['title'] for k, v in PRODUCT_DATA.items()}


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

    # Match against active + draft + pending listings only (not sold)
    # Sold items are excluded via SOLD_OUT_FOLDERS instead
    listings = EbayListing.objects.filter(status__in=['active', 'draft', 'pending'])
    listing_titles = {l.title.lower(): l for l in listings}

    # Products known to be sold out — checks both folder slug and parent folder
    SOLD_OUT_FOLDERS = {'dune', 'x-files-s1', 'x-files-showcase', 'galaxy-s3'}
    # Products with existing multi-variant or active listings (don't show sub-boxes)
    # Also includes R2 folders whose names don't match listing titles well
    ALREADY_LISTED_FOLDERS = {
        '007-moonraker', 'space-1999',
        'vechicles', 'vehicles',          # SW Vehicles set (typo in R2 folder)
        'wonder-bread',                   # SW Wonder Bread set
        '007jamesbonder-redbinder',       # 007 Red Binder listing
        'duos-lionel-legendarys-trains-pack',  # Lionel Trains Pack
        'sw-3d',                              # Star Wars 3D box
        'sw-rotj-stickers',                   # ROTJ Sticker box
        'sw-shadows-of-the-empire',           # Shadows of Empire box
        'sw-mastervisions',                   # Master Visions
        'sw-topps-trilogy-regular',            # Topps Trilogy box
        'sw-trilogy-merlin',                   # Merlin Trilogy box
        'sw-wide-anh-esb-rotj-sets',          # Widevision sets
        'widevision',                         # Widevision set
    }

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
    # Uses BOTH the folder slug AND the PRODUCT_DATA title for matching
    r2_without_listing = []
    matched_r2 = set()
    # Common words that appear in many listings — don't count for matching
    stop_words = {'the', 'a', 'an', 'of', 'and', 'img', 'in', 'on', 'for', 'with', 'new'}
    generic_words = {
        'star', 'wars', 'trek', 'topps', 'set', 'complete', 'base', 'series',
        'card', 'cards', 'trading', 'sealed', 'factory', 'box', 'edition',
        'collection', 'premium', 'marvel', 'disney', 'impel', 'skybox',
        'fleer', 'upper', 'deck',
        # Years are not distinctive — many products share the same year
        '1976', '1977', '1978', '1979', '1980', '1981', '1982', '1983',
        '1984', '1985', '1986', '1987', '1988', '1989', '1990', '1991',
        '1992', '1993', '1994', '1995', '1996', '1997', '1998', '1999',
        '2000', '2001',
    }

    for product in r2_products:
        # Build match words from folder name + display name (PRODUCT_DATA title)
        folder_words = set(re.split(r'[-_/]', product['folder_name'].lower()))
        display_words = set(re.split(r'[\s\-]+', product['display_name'].lower()))
        all_match_words = (folder_words | display_words) - stop_words
        all_match_words = {w for w in all_match_words if len(w) > 2}
        # Distinctive words = not generic
        distinctive_words = all_match_words - generic_words

        matched = False
        for title_lower, listing in listing_titles.items():
            title_words = set(re.split(r'[\s\-]+', title_lower))
            title_words = {w for w in title_words if len(w) > 2} - stop_words
            overlap = all_match_words & title_words
            distinctive_overlap = distinctive_words & title_words
            # Require 3+ total overlap AND at least 1 distinctive word match
            if len(overlap) >= 3 and len(distinctive_overlap) >= 1:
                matched = True
                matched_r2.add(product['r2_prefix'])
                break

        if not matched:
            slug = product['folder_name']
            parent = product.get('parent', '')

            # Skip sold-out products (check both slug and parent folder)
            if slug in SOLD_OUT_FOLDERS or parent in SOLD_OUT_FOLDERS:
                continue

            # Skip products already listed (check both slug and parent)
            if slug in ALREADY_LISTED_FOLDERS or parent in ALREADY_LISTED_FOLDERS:
                continue

            # Flag pre-1990 / multi-variant items
            # Check both the slug and parent for product data
            product_info = PRODUCT_DATA.get(slug, PRODUCT_DATA.get(parent, {}))
            year_str = product_info.get('specs', {}).get('Year Manufactured', '')
            try:
                year = int(year_str) if year_str else 0
            except ValueError:
                year = 0

            if year > 0 and year < 1990:
                product['needs_multi_variant'] = True
            else:
                product['needs_multi_variant'] = False

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
        title_words = {w for w in title_words if len(w) > 2} - stop_words
        title_distinctive = title_words - generic_words
        matched = False
        for product in r2_products:
            folder_words = set(re.split(r'[-_/]', product['folder_name'].lower()))
            display_words = set(re.split(r'[\s\-]+', product['display_name'].lower()))
            product_words = {w for w in (folder_words | display_words) if len(w) > 2} - stop_words
            product_distinctive = product_words - generic_words
            overlap = title_words & product_words
            distinctive_overlap = title_distinctive & product_distinctive
            if len(overlap) >= 3 and len(distinctive_overlap) >= 1:
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
