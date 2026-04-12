# src/non_sports_cards/r2_utils.py
"""
R2 storage utilities for Sam's Collectibles gallery pages.

Provides cached access to Cloudflare R2 bucket listings so gallery
pages can render product images without hitting the API on every request.
"""

import os
import re
import time
import logging
from collections import defaultdict

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# R2 Configuration
# ---------------------------------------------------------------------------
R2_ACCESS_KEY = os.environ.get(
    'R2_ACCESS_KEY_ID', '1906b346fcf1a6779ee4cdd19a27fc0b')
R2_SECRET_KEY = os.environ.get(
    'R2_SECRET_ACCESS_KEY',
    'a71f3baccd32346f41d70494bdb9eab9f7ade7873f62794affc88e2f62c8c103')
R2_ENDPOINT = os.environ.get(
    'R2_ENDPOINT_URL',
    'https://c2fa931a6f5d02d3c12552d68c2c379b.r2.cloudflarestorage.com')
BUCKET = 'samscollectibles'
CDN_BASE = 'https://media.samscollectibles.net'

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

# ---------------------------------------------------------------------------
# In-memory cache with TTL
# ---------------------------------------------------------------------------
_cache = {}
CACHE_TTL = 300  # 5 minutes


def _get_cached(key):
    """Return cached value if still valid, else None."""
    entry = _cache.get(key)
    if entry and (time.time() - entry['ts']) < CACHE_TTL:
        return entry['data']
    return None


def _set_cached(key, data):
    """Store data in cache with current timestamp."""
    _cache[key] = {'data': data, 'ts': time.time()}


def invalidate_cache(prefix=None):
    """Clear cache entries. If prefix given, only matching keys."""
    if prefix is None:
        _cache.clear()
    else:
        keys_to_remove = [k for k in _cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del _cache[k]


# ---------------------------------------------------------------------------
# S3/R2 client
# ---------------------------------------------------------------------------
_client = None


def _get_client():
    """Lazy-init the boto3 S3 client for R2."""
    global _client
    if _client is None:
        _client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            config=BotoConfig(
                signature_version='s3v4',
                retries={'max_attempts': 2, 'mode': 'standard'},
            ),
            region_name='auto',
        )
    return _client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_r2_objects(prefix):
    """
    List all objects in R2 under a prefix.

    Returns a list of dicts: [{'key': '...', 'size': ..., 'last_modified': ...}]
    """
    cache_key = f'objects:{prefix}'
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    client = _get_client()
    objects = []
    continuation_token = None

    try:
        while True:
            kwargs = {
                'Bucket': BUCKET,
                'Prefix': prefix,
                'MaxKeys': 1000,
            }
            if continuation_token:
                kwargs['ContinuationToken'] = continuation_token

            response = client.list_objects_v2(**kwargs)

            for obj in response.get('Contents', []):
                objects.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                })

            if response.get('IsTruncated'):
                continuation_token = response.get('NextContinuationToken')
            else:
                break
    except Exception:
        logger.exception('Error listing R2 objects with prefix=%s', prefix)
        return []

    _set_cached(cache_key, objects)
    return objects


def get_r2_folders(prefix):
    """
    Get unique immediate subfolder names under a prefix (like ls).

    For prefix='trading-cards/boxes/', returns ['star-wars', 'star-trek', ...]
    """
    cache_key = f'folders:{prefix}'
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    client = _get_client()
    folders = set()

    try:
        kwargs = {
            'Bucket': BUCKET,
            'Prefix': prefix,
            'Delimiter': '/',
        }
        paginator = client.get_paginator('list_objects_v2')
        for page in paginator.paginate(**kwargs):
            for cp in page.get('CommonPrefixes', []):
                folder_path = cp['Prefix']
                # Extract just the folder name (strip prefix and trailing slash)
                name = folder_path[len(prefix):].rstrip('/')
                if name:
                    folders.add(name)
    except Exception:
        logger.exception('Error listing R2 folders with prefix=%s', prefix)
        return []

    result = sorted(folders)
    _set_cached(cache_key, result)
    return result


def get_r2_images(prefix):
    """
    Get all image URLs under a prefix.

    Returns list of dicts: [{'key': '...', 'url': '...', 'filename': '...'}]
    """
    objects = list_r2_objects(prefix)
    images = []
    for obj in objects:
        ext = os.path.splitext(obj['key'])[1].lower()
        if ext in IMAGE_EXTENSIONS:
            filename = os.path.basename(obj['key'])
            images.append({
                'key': obj['key'],
                'url': f"{CDN_BASE}/{obj['key']}",
                'filename': filename,
            })
    return images


def get_r2_folder_thumbnails(prefix):
    """
    For each immediate subfolder under prefix, return the first image as thumbnail.

    Returns list of dicts:
        [{'folder': 'star-wars', 'thumbnail_url': '...', 'image_count': 5}]
    """
    cache_key = f'thumbs:{prefix}'
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    folders = get_r2_folders(prefix)
    result = []

    for folder in folders:
        folder_prefix = f"{prefix}{folder}/"
        images = get_r2_images(folder_prefix)
        thumbnail_url = images[0]['url'] if images else None
        result.append({
            'folder': folder,
            'thumbnail_url': thumbnail_url,
            'image_count': len(images),
        })

    _set_cached(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Filename parsing for SW ANH set photos
# ---------------------------------------------------------------------------

# Pattern: sw-{movie}-s{series}{type}-{star}s{sku}-p{photo}.jpg
# Example: sw-anh-s2base-1s101-p01.jpg
#   movie=anh, series=2, type=base, star=1, sku=101, photo=01
SW_PHOTO_PATTERN = re.compile(
    r'^sw-(?P<movie>[a-z]+)-s(?P<series>\d+)(?P<card_type>\w+)-'
    r'(?P<stars>\d+)s(?P<sku>\d+)-p(?P<photo>\d+)\.\w+$'
)

MOVIE_NAMES = {
    'anh': 'A New Hope',
    'esb': 'Empire Strikes Back',
    'rotj': 'Return of the Jedi',
}

CARD_TYPE_NAMES = {
    'base': 'Base Card',
    'sticker': 'Sticker',
    'chase': 'Chase Card',
}


def parse_sw_filename(filename):
    """
    Parse a Star Wars set photo filename into structured data.

    Returns dict or None if filename doesn't match the pattern.
    """
    match = SW_PHOTO_PATTERN.match(filename)
    if not match:
        return None

    g = match.groupdict()
    return {
        'movie_code': g['movie'],
        'movie_name': MOVIE_NAMES.get(g['movie'], g['movie'].upper()),
        'series': int(g['series']),
        'card_type': CARD_TYPE_NAMES.get(g['card_type'], g['card_type']),
        'card_type_raw': g['card_type'],
        'stars': int(g['stars']),
        'star_label': f"{g['stars']} Star",
        'sku': g['sku'],
        'photo_num': int(g['photo']),
    }


def group_sw_images_by_sku(images):
    """
    Group a list of SW set images by SKU.

    Returns dict: {sku: {'info': parsed_info, 'images': [...]}}
    """
    groups = defaultdict(lambda: {'info': None, 'images': []})

    for img in images:
        parsed = parse_sw_filename(img['filename'])
        if parsed:
            sku = parsed['sku']
            if groups[sku]['info'] is None:
                groups[sku]['info'] = parsed
            groups[sku]['images'].append(img)
        else:
            # Non-SW-pattern images go into an 'other' group
            groups['other']['images'].append(img)

    # Sort images within each group by photo number
    for sku, data in groups.items():
        data['images'].sort(key=lambda x: x['filename'])

    return dict(groups)


# ---------------------------------------------------------------------------
# Display name helpers
# ---------------------------------------------------------------------------

def folder_display_name(folder_name):
    """
    Convert a folder slug to a display-friendly name.

    '007jamesbonder-redbinder' -> '007 James Bond ER - Red Binder'
    'star-wars' -> 'Star Wars'
    'sw-3d' -> 'SW 3D'
    """
    # Special mappings for known folders
    DISPLAY_NAMES = {
        # Binders
        '007jamesbonder-redbinder': 'James Bond Red Binder',
        # Boxes - Star Wars
        'sw-3d': 'SW 3D Widevision',
        'sw-first-anthology': 'First Anthology',
        'sw-mastervisions': 'Mastervisions',
        'sw-vehicles': 'SW Vehicles',
        'sw-shadows-empire': 'Shadows of the Empire',
        'sw-widevision': 'Widevision',
        # Boxes - Star Trek
        'ds9': 'Deep Space Nine',
        'master-series': 'Master Series',
        'tng': 'The Next Generation',
        'tos': 'The Original Series',
        # Boxes - Movies
        '007-goldeneye': '007 Goldeneye',
        '007-moonraker': '007 Moonraker',
        'dune': 'Dune',
        'godzilla': 'Godzilla',
        # Boxes - TV
        'outer-limits': 'Outer Limits',
        'space-1999': 'Space 1999',
        'x-files': 'X-Files',
        # Franchises
        'star-wars': 'Star Wars',
        'star-trek': 'Star Trek',
        'marvel': 'Marvel',
        'dc-comics': 'DC Comics',
        'disney': 'Disney',
        'valiant': 'Valiant',
        'movies': 'Movies',
        'tv-shows': 'TV Shows',
        'other': 'Other',
        # Sets
        'anh-series-1': 'ANH Series 1',
        'anh-series-2': 'ANH Series 2',
        'anh-series-3': 'ANH Series 3',
        'anh-series-4': 'ANH Series 4',
        'anh-series-5': 'ANH Series 5',
        'shadows-of-the-empire': 'Shadows of the Empire',
        'widevision': 'Widevision',
        'masterpieces': 'Masterpieces',
        'universe': 'Universe',
        'x-men': 'X-Men',
        # Packs
        'casper': 'Casper',
        # Singles
        'vehicles': 'Vehicles',
    }

    if folder_name in DISPLAY_NAMES:
        return DISPLAY_NAMES[folder_name]

    # Default: capitalize and replace hyphens with spaces
    return folder_name.replace('-', ' ').title()


PRODUCT_TYPE_NAMES = {
    'binders': 'Binders',
    'boxes': 'Boxes',
    'packs': 'Packs',
    'sets': 'Sets',
    'singles': 'Singles',
}
