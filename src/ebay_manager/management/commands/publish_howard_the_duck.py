"""Create + publish single-box eBay listing for 1988 Topps Howard the Duck.

1-off listing (not multi-variant). Box exterior is not sealed but the
individual packs inside remain securely wrapped. The HTML description
at ebay_descriptions/ns-cards/boxes/movies/1988-topps-howard-the-duck-box.html
is used verbatim.
"""
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from ebay_manager.models import EbayListing
from ebay_manager.services.publish import publish_to_ebay
from non_sports_cards.r2_utils import get_r2_images, _cache


TITLE = '1988 Topps Howard the Duck Trading Cards Full Box 36 Wrapped Packs Marvel Lucasfilm'
SKU = '1988-TOPPS-HOWARD-THE-DUCK-BOX'
PRICE = 149.95
CATEGORY_ID = '261035'   # Sealed Boxes
CONDITION_ID = '3000'    # Used
R2_PREFIX = 'trading-cards/boxes/1988-topps-howard-the-duck'
DESCRIPTION_PATH = (
    Path(__file__).resolve().parents[4]
    / 'ebay_descriptions/ns-cards/boxes/movies/1988-topps-howard-the-duck-box.html'
)

# 2 lb 0 oz = 32 oz.  Box dims: 9 x 6 x 4
SHIP_WEIGHT_OZ = 32
PACKAGE_DIMS = {'length': 9, 'width': 6, 'height': 4}

ASPECTS = {
    'Franchise': ['Howard the Duck'],
    'Manufacturer': ['Topps'],
    'Set': ['Howard the Duck'],
    'Year Manufactured': ['1988'],
    'Genre': ['Sci-Fi & Fantasy', 'Comedy'],
    'Movie': ['Howard the Duck'],
    'Configuration': ['Box'],
    'Type': ['Non-Sport Trading Card'],
    'Card Size': ['Standard'],
    'Number of Packs': ['36'],
    'Features': ['Wrapped Packs'],
    'Country/Region of Manufacture': ['United States'],
    'Theme': ['Comic Books', 'Movies', 'Sci-Fi', 'Comedy'],
    'Character': ['Howard the Duck', 'Beverly Switzler', 'Phil Blumburtt', 'Dr. Jenning'],
    'Vintage': ['Yes'],
}


class Command(BaseCommand):
    help = 'Create + publish single-box listing for 1988 Topps Howard the Duck.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--draft', action='store_true',
            help='Save as draft (DB only) instead of publishing to eBay.',
        )

    def handle(self, *args, **options):
        _cache.clear()

        images = get_r2_images(R2_PREFIX + '/')
        image_urls = [img.get('url', '') for img in images if img.get('url')]
        self.stdout.write(f'Found {len(image_urls)} images under {R2_PREFIX}/')
        if not image_urls:
            self.stderr.write('No images found — aborting.')
            return

        if DESCRIPTION_PATH.exists():
            description_html = DESCRIPTION_PATH.read_text()
            self.stdout.write(f'Loaded description ({len(description_html)} bytes)')
        else:
            self.stderr.write(f'Description file missing at {DESCRIPTION_PATH}')
            return

        listing, created = EbayListing.objects.update_or_create(
            sku=SKU,
            defaults={
                'title': TITLE,
                'price': PRICE,
                'status': 'pending',
                'is_variant': False,
                'category_id': CATEGORY_ID,
                'condition_id': CONDITION_ID,
                'description_html': description_html,
                'image_urls': image_urls,
                'item_specifics': ASPECTS,
                'weight_lbs': SHIP_WEIGHT_OZ // 16,
                'weight_oz': SHIP_WEIGHT_OZ % 16,
                'package_length': PACKAGE_DIMS['length'],
                'package_width': PACKAGE_DIMS['width'],
                'package_height': PACKAGE_DIMS['height'],
                'shipping_service': 'USPSGroundAdvantage',
                'parent_r2_prefix': R2_PREFIX,
            }
        )
        verb = 'Created' if created else 'Updated'
        self.stdout.write(f'{verb} EbayListing pk={listing.pk} sku={SKU}')

        if options['draft']:
            self.stdout.write(self.style.SUCCESS('Draft saved. Not pushed to eBay.'))
            return

        self.stdout.write('Publishing to eBay...')
        result = publish_to_ebay(listing)
        self.stdout.write(self.style.SUCCESS(
            f"Published! eBay #{result['listing_id']}  {result['ebay_url']}"
        ))
