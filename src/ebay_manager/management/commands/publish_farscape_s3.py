"""Create + publish single-box eBay listing for 2002 Rittenhouse Farscape Season Three.

1-off listing (hand-numbered 2658/8000). Factory-sealed hobby box with
full Rittenhouse chase lineup (autos, costume cards, sketches, animation
cels). Description at
ebay_uploads/ns_cards/box/2002-rittenhouse-farscape-season-three-box.html
is used verbatim.
"""
from django.core.management.base import BaseCommand

from ebay_manager.models import EbayListing
from ebay_manager.services.description_files import EBAY_UPLOADS_ROOT
from ebay_manager.services.publish import publish_to_ebay
from non_sports_cards.r2_utils import get_r2_images, _cache


TITLE = '2002 Rittenhouse Farscape Season Three Sealed Hobby Box 2658/8000 Autographs'
SKU = '2002-RITTENHOUSE-FARSCAPE-S3-BOX-2658'
PRICE = 137.95
CATEGORY_ID = '261035'
CONDITION_ID = '1000'
R2_PREFIX = 'trading-cards/boxes/2002-rittenhouse-farscape-season-three'
DESCRIPTION_PATH = (
    EBAY_UPLOADS_ROOT / 'ns_cards' / 'box' / '2002-rittenhouse-farscape-season-three-box.html'
)

# 1 lb 12 oz = 28 oz. Box dims: 9 x 6 x 4
SHIP_WEIGHT_OZ = 28
PACKAGE_DIMS = {'length': 9, 'width': 6, 'height': 4}

ASPECTS = {
    'Franchise': ['Farscape'],
    'Manufacturer': ['Rittenhouse Archives'],
    'Set': ['Farscape Season Three'],
    'Year Manufactured': ['2002'],
    'Genre': ['Sci-Fi & Fantasy'],
    'TV Show': ['Farscape'],
    'Configuration': ['Box'],
    'Type': ['Non-Sport Trading Card'],
    'Card Size': ['Standard'],
    'Number of Packs': ['40'],
    'Features': ['Factory Sealed', 'Limited Edition', 'Hand-Numbered', 'Autograph', 'Costume Card', 'Sketch Card'],
    'Country/Region of Manufacture': ['United States'],
    'Theme': ['TV Shows', 'Sci-Fi', 'Jim Henson'],
    'Character': [
        'John Crichton', 'Aeryn Sun', 'Chiana', "D'Argo", 'Zhaan', 'Rygel',
        'Stark', 'Scorpius', 'Crais', 'Jool', 'Talyn', 'Moya',
    ],
    'Season': ['Season Three'],
    'Vintage': ['Yes'],
}


class Command(BaseCommand):
    help = 'Create + publish single-box listing for 2002 Rittenhouse Farscape Season Three.'

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
                'quantity': 1,
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
