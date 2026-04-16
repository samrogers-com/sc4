"""
Card asterisk scanner — detects ★ or ★★ on 1977 Topps Star Wars cards.

Uses Claude Vision API to analyze card photos stored on R2 in 9-pocket
sleeve page format. Each page has up to 9 cards in a 3x3 grid.

The asterisk(s) appear before the © copyright text at the bottom of
each card front: ★ © 1977 20TH CENTURY-FOX FILM CORP. All Rights Reserved.
Single ★ and double ★★ indicate different puzzle back print runs.

Flow:
    1. find_unscanned_sets() — discover mixed/ folders on R2 not yet scanned
    2. scan_set(r2_prefix) — process all pages in one set
    3. crop_cards_from_page(image_bytes) — split 9-pocket page into 9 cards
    4. analyze_card(image_bytes) — send to Claude Vision API
"""
import base64
import io
import json
import logging
import re
import time

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Claude Vision prompt for asterisk detection
CARD_ANALYSIS_PROMPT = """This is a 1977 Topps Star Wars trading card photographed in a 9-pocket sleeve page. The card may be rotated.

Look at the copyright line at the bottom of the card front. It reads either:
  ★ © 1977 20TH CENTURY-FOX FILM CORP. All Rights Reserved.
or:
  ★★ © 1977 20TH CENTURY-FOX FILM CORP. All Rights Reserved.

Count how many star (★) symbols appear BEFORE the © symbol.
Also read the card number (small number near the Star Wars starburst logo).
Also read the card title text (below the photo on the card).

Reply ONLY with this JSON format, nothing else:
{"card_number": 9, "asterisk_count": 1, "card_title": "Rebels defend their starship!", "confidence": 0.95}

If you cannot read the card clearly, use confidence 0.0 and asterisk_count 0."""

# Series card counts
SERIES_CARD_COUNTS = {
    'series-1': 66,
    'series-2': 66,
    'series-3': 66,
    'series-4': 66,
    'series-5': 66,
}


def find_unscanned_sets(product_prefix='trading-cards/sets/star-wars'):
    """Find mixed/ set folders on R2 that haven't been scanned yet.

    Scans all movie/series/mixed/ paths and checks against SetScanStatus.

    Returns:
        List of dicts: [{'r2_prefix': '...', 'series': 'series-1', 'set_number': '103'}]
    """
    from non_sports_cards.r2_utils import get_r2_folders, _cache
    from ebay_manager.models import SetScanStatus

    _cache.clear()

    scanned_prefixes = set(
        SetScanStatus.objects.filter(status='complete')
        .values_list('r2_prefix', flat=True)
    )

    unscanned = []
    prefix = product_prefix if product_prefix.endswith('/') else product_prefix + '/'

    # Walk: movie/ -> series/ -> condition/ -> set_number/
    movies = get_r2_folders(prefix)
    for movie in sorted(movies):
        series_list = get_r2_folders(f'{prefix}{movie}/')
        for series in sorted(series_list):
            conditions = get_r2_folders(f'{prefix}{movie}/{series}/')
            for condition in sorted(conditions):
                if condition != 'mixed':
                    continue  # Only scan mixed sets
                set_numbers = get_r2_folders(f'{prefix}{movie}/{series}/{condition}/')
                for set_num in sorted(set_numbers):
                    full_prefix = f'{product_prefix}/{movie}/{series}/{condition}/{set_num}'
                    if full_prefix not in scanned_prefixes:
                        unscanned.append({
                            'r2_prefix': full_prefix,
                            'series': series,
                            'set_number': set_num,
                            'movie': movie,
                        })

    return unscanned


def crop_cards_from_page(image_bytes):
    """Split a 9-pocket sleeve page photo into individual card crops.

    The cards are photographed upside down (rotated 180°). This function
    rotates the image, then crops each of the 9 card positions.

    Some pages may have fewer than 9 cards (last page of a set).

    Args:
        image_bytes: Raw JPEG bytes of the page photo

    Returns:
        List of up to 9 dicts: [{'position': 1, 'image_bytes': bytes, 'has_card': bool}]
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img = img.rotate(180)  # Cards are stored upside down

    w, h = img.size
    card_w = w // 3
    card_h = h // 3

    cards = []
    for row in range(3):
        for col in range(3):
            position = row * 3 + col + 1
            x1 = col * card_w + 15  # Slight inset to avoid sleeve edges
            y1 = row * card_h + 15
            x2 = (col + 1) * card_w - 15
            y2 = (row + 1) * card_h - 15

            crop = img.crop((x1, y1, x2, y2))

            # Check if this pocket has a card (not mostly empty/wood background)
            # Simple heuristic: cards have more color variation than empty sleeves
            pixels = list(crop.getdata())
            if len(pixels) > 100:
                # Sample center pixels — cards have distinct colors, empty pockets are brown
                center_x = crop.width // 2
                center_y = crop.height // 2
                sample_region = crop.crop((
                    center_x - 50, center_y - 50,
                    center_x + 50, center_y + 50
                ))
                colors = sample_region.getcolors(maxcolors=1000)
                # If mostly one color (wood), it's empty
                has_card = len(colors or []) > 50
            else:
                has_card = False

            # Convert crop to JPEG bytes
            buf = io.BytesIO()
            crop.save(buf, format='JPEG', quality=85)
            card_bytes = buf.getvalue()

            cards.append({
                'position': position,
                'image_bytes': card_bytes,
                'has_card': has_card,
            })

    return cards


def analyze_card(image_bytes, api_key=None):
    """Send a card crop to Claude Vision API for asterisk detection.

    Args:
        image_bytes: JPEG bytes of a single card crop
        api_key: Anthropic API key (uses settings if not provided)

    Returns:
        Dict: {'card_number': int, 'asterisk_count': int, 'card_title': str, 'confidence': float}
        or None if analysis failed
    """
    import anthropic

    key = api_key or getattr(settings, 'ANTHROPIC_API_KEY', '')
    if not key:
        logger.error('No ANTHROPIC_API_KEY configured')
        return None

    client = anthropic.Anthropic(api_key=key)
    b64_image = base64.b64encode(image_bytes).decode('utf-8')

    try:
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=200,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': 'image/jpeg',
                            'data': b64_image,
                        },
                    },
                    {
                        'type': 'text',
                        'text': CARD_ANALYSIS_PROMPT,
                    },
                ],
            }],
        )

        raw_text = message.content[0].text.strip()

        # Parse JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[^}]+\}', raw_text)
        if json_match:
            result = json.loads(json_match.group())
            result['raw_response'] = raw_text
            return result
        else:
            logger.warning(f'Could not parse JSON from response: {raw_text[:200]}')
            return {'card_number': 0, 'asterisk_count': 0, 'card_title': '',
                    'confidence': 0.0, 'raw_response': raw_text}

    except Exception as e:
        logger.error(f'Claude API error: {e}')
        return None


def scan_set(r2_prefix, api_key=None, callback=None):
    """Scan all cards in one set and save results to the database.

    Args:
        r2_prefix: Full R2 path to the set folder
            e.g. 'trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/103'
        api_key: Anthropic API key (uses settings if not provided)
        callback: Optional function(message) called with progress updates

    Returns:
        SetScanStatus instance
    """
    from non_sports_cards.r2_utils import get_r2_images, _get_client, BUCKET, _cache
    from ebay_manager.models import SetScanStatus, CardAsteriskScan

    _cache.clear()

    def log(msg):
        logger.info(msg)
        if callback:
            callback(msg)

    # Parse series and set number from prefix
    parts = r2_prefix.rstrip('/').split('/')
    set_number = parts[-1] if parts else ''
    series = None
    for p in parts:
        if p.startswith('series-'):
            series = p
            break

    # Determine expected card count
    total_cards = SERIES_CARD_COUNTS.get(series, 66)

    # Get or create scan status
    scan_status, created = SetScanStatus.objects.get_or_create(
        r2_prefix=r2_prefix,
        defaults={
            'series': series,
            'set_number': set_number,
            'total_cards': total_cards,
            'status': 'pending',
        }
    )

    scan_status.status = 'scanning'
    scan_status.started_at = timezone.now()
    scan_status.error_message = None
    scan_status.save()

    log(f'Scanning {r2_prefix} (expecting {total_cards} cards)')

    try:
        # Get all page images
        images = get_r2_images(r2_prefix + '/')
        image_urls = sorted(
            [img for img in images if img.get('url')],
            key=lambda x: x.get('filename', '')
        )

        log(f'Found {len(image_urls)} page images')

        client = _get_client()
        scanned = 0
        single_stars = 0
        double_stars = 0
        unknowns = 0

        for page_idx, img_info in enumerate(image_urls, 1):
            key = img_info.get('key', '')
            log(f'  Page {page_idx}: {key}')

            # Download image from R2
            response = client.get_object(Bucket=BUCKET, Key=key)
            image_bytes = response['Body'].read()

            # Crop into individual cards
            cards = crop_cards_from_page(image_bytes)

            for card in cards:
                if not card['has_card']:
                    continue

                # Analyze with Claude Vision
                result = analyze_card(card['image_bytes'], api_key=api_key)

                if result and result.get('card_number', 0) > 0:
                    card_num = result['card_number']
                    asterisks = result.get('asterisk_count', 0)
                    confidence = result.get('confidence', 0.0)
                    title = result.get('card_title', '')

                    # Save result (update if card already scanned)
                    CardAsteriskScan.objects.update_or_create(
                        scan_set=scan_status,
                        card_number=card_num,
                        defaults={
                            'asterisk_count': asterisks,
                            'confidence': confidence,
                            'page_number': page_idx,
                            'position': card['position'],
                            'card_title': title,
                            'raw_response': result.get('raw_response', ''),
                        }
                    )

                    scanned += 1
                    if asterisks == 1:
                        single_stars += 1
                    elif asterisks == 2:
                        double_stars += 1
                    else:
                        unknowns += 1

                    stars = '★' * asterisks if asterisks else '?'
                    log(f'    #{card_num} {stars} "{title}" (conf={confidence})')
                else:
                    unknowns += 1
                    log(f'    Position {card["position"]}: could not read')

                # Rate limit — avoid hitting API too fast
                time.sleep(0.5)

        # Update scan status
        scan_status.status = 'complete'
        scan_status.completed_at = timezone.now()
        scan_status.scanned_cards = scanned
        scan_status.single_star_count = single_stars
        scan_status.double_star_count = double_stars
        scan_status.unknown_count = unknowns
        scan_status.save()

        log(f'Complete: {scanned} cards — ★{single_stars} ★★{double_stars} ?{unknowns}')

    except Exception as e:
        scan_status.status = 'error'
        scan_status.error_message = str(e)
        scan_status.save()
        logger.error(f'Scan failed for {r2_prefix}: {e}')
        raise

    return scan_status
