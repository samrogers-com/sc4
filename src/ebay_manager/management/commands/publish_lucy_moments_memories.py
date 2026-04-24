"""Create + publish multi-quantity eBay listing for 1995 KRC Lucy: Moments & Memories.

8 identical sealed wax boxes — fixed-price listing with quantity=8. Description
at ebay_uploads/ns_cards/box/1995-krc-lucy-moments-memories-box.html is used
verbatim.
"""
from django.core.management.base import BaseCommand

from ebay_manager.models import EbayListing
from ebay_manager.services.description_files import EBAY_UPLOADS_ROOT
from ebay_manager.services.publish import publish_to_ebay
from non_sports_cards.r2_utils import get_r2_images, _cache


TITLE = '1995 KRC Lucy Moments & Memories Sealed Wax Box 36 Packs Lucille Ball I Love Lucy'
SKU = '1995-KRC-LUCY-MOMENTS-MEMORIES-BOX'
PRICE = 56.95
QUANTITY = 8
CATEGORY_ID = '261035'
CONDITION_ID = '1000'
R2_PREFIX = 'trading-cards/boxes/1995-krc-lucy-moments-memories'
DESCRIPTION_PATH = (
    EBAY_UPLOADS_ROOT / 'ns_cards' / 'box' / '1995-krc-lucy-moments-memories-box.html'
)

# 1 lb 10 oz = 26 oz. Box dims: 9 x 6 x 4
SHIP_WEIGHT_OZ = 26
PACKAGE_DIMS = {'length': 9, 'width': 6, 'height': 4}

ASPECTS = {
    'Franchise': ['I Love Lucy'],
    'Manufacturer': ['KRC International'],
    'Set': ['Lucy: Moments & Memories'],
    'Year Manufactured': ['1995'],
    'Genre': ['Comedy'],
    'TV Show': ['I Love Lucy'],
    'Configuration': ['Box'],
    'Type': ['Non-Sport Trading Card'],
    'Card Size': ['Standard'],
    'Number of Packs': ['36'],
    'Features': ['Factory Sealed', 'Autograph', 'Foil', 'Vintage'],
    'Country/Region of Manufacture': ['United States'],
    'Theme': ['TV Shows', 'Comedy', 'Classic TV', 'Hollywood'],
    'Character': ['Lucy Ricardo', 'Lucille Ball', 'Desi Arnaz', 'Ricky Ricardo'],
    'Vintage': ['Yes'],
}


class Command(BaseCommand):
    help = 'Create + publish multi-qty listing for 1995 KRC Lucy: Moments & Memories.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--draft', action='store_true',
            help='Save as draft (DB only) instead of publishing to eBay.',
        )
        parser.add_argument(
            '--quantity', type=int, default=QUANTITY,
            help=f'Override quantity (default: {QUANTITY}).',
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

        qty = options['quantity']
        listing, created = EbayListing.objects.update_or_create(
            sku=SKU,
            defaults={
                'title': TITLE,
                'price': PRICE,
                'quantity': qty,
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
        self.stdout.write(f'{verb} EbayListing pk={listing.pk} sku={SKU} qty={qty}')

        if options['draft']:
            self.stdout.write(self.style.SUCCESS('Draft saved. Not pushed to eBay.'))
            return

        self.stdout.write('Publishing to eBay...')
        result = publish_to_ebay(listing)
        self.stdout.write(self.style.SUCCESS(
            f"Published! eBay #{result['listing_id']}  {result['ebay_url']}"
        ))
