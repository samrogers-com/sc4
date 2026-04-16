"""Create multi-variant DRAFT listing for 2001 Rittenhouse Farscape in Motion Premiere Edition.

Two numbered sealed boxes from a limited edition of 4,000:
  Box 1: #0728 of 4000  @  $299.95
  Box 2: #3590 of 4000  @  $199.95

Saved as drafts (no eBay push). Review and publish from the variant
group detail page in the admin UI.
"""
from pathlib import Path

from django.core.management.base import BaseCommand

from ebay_manager.services.multi_variant import discover_variants, save_variant_drafts
from non_sports_cards.r2_utils import _cache


TITLE = '2001 Rittenhouse Farscape in Motion Premiere Edition Sealed Box Numbered /4000'
R2_PREFIX = 'trading-cards/boxes/2001-rittenhouse-farscape-in-motion'
CATEGORY_ID = '261035'  # Sealed Boxes
CONDITION_ID = '1000'   # New / Factory Sealed
DESCRIPTION_PATH = (
    Path(__file__).resolve().parents[4]
    / 'ebay_descriptions/ns-cards/boxes/tv/2001-rittenhouse-farscape-in-motion-box.html'
)

# Ship weight: 1 lb 6 oz = 22 oz.  Box dimensions: 9 x 6 x 4
SHIP_WEIGHT_OZ = 22
PACKAGE_DIMS = {'length': 9, 'width': 6, 'height': 4}

ASPECTS = {
    'Franchise': ['Farscape'],
    'Manufacturer': ['Rittenhouse'],
    'Set': ['Farscape in Motion Premiere Edition'],
    'Year Manufactured': ['2001'],
    'Genre': ['Sci-Fi'],
    'TV Show': ['Farscape'],
    'Configuration': ['Box'],
    'Type': ['Non-Sport Trading Card'],
    'Card Size': ['Standard'],
    'Number of Packs': ['24'],
    'Features': ['Factory Sealed', 'Lenticular', 'Hand-Numbered', 'Limited Edition'],
    'Country/Region of Manufacture': ['United States'],
    'Theme': ['Science Fiction', 'TV Shows', 'Space'],
    'Character': [
        'John Crichton', 'Aeryn Sun', 'Rygel', "Ka D'Argo",
        'Pa\u2019u Zotoh Zhaan', 'Chiana',
    ],
    'Vintage': ['Yes'],
}

# Per-variant display names shown as the "Box" aspect value on eBay
VARIANT_DISPLAY = {
    'box-1': 'Box #0728 of 4000',
    'box-2': 'Box #3590 of 4000',
}

PRICES = {
    'box-1': 299.95,
    'box-2': 199.95,
}


class Command(BaseCommand):
    help = 'Create DRAFT multi-variant listing for 2001 Rittenhouse Farscape in Motion.'

    def handle(self, *args, **options):
        _cache.clear()

        self.stdout.write(f'Discovering variants under {R2_PREFIX}/ ...')
        variants = discover_variants(R2_PREFIX)
        if not variants:
            self.stderr.write('No variants found. Did the R2 upload finish?')
            return

        # Apply our custom display names (box numbers)
        for v in variants:
            if v['name'] in VARIANT_DISPLAY:
                v['display'] = VARIANT_DISPLAY[v['name']]
            self.stdout.write(
                f"  {v['name']}: {len(v['images'])} images  "
                f"display={v['display']}  price=${PRICES.get(v['name'], 0):.2f}"
            )

        # Read the shared HTML description
        if DESCRIPTION_PATH.exists():
            description_html = DESCRIPTION_PATH.read_text()
            self.stdout.write(f'Loaded description ({len(description_html)} bytes) from {DESCRIPTION_PATH}')
        else:
            description_html = TITLE
            self.stdout.write(self.style.WARNING(f'Description not found at {DESCRIPTION_PATH}; using title as fallback'))

        result = save_variant_drafts(
            title=TITLE,
            variants=variants,
            specs=ASPECTS,
            prices=PRICES,
            category_id=CATEGORY_ID,
            condition_id=CONDITION_ID,
            description_html=description_html,
            r2_prefix=R2_PREFIX,
            ship_weight_oz=SHIP_WEIGHT_OZ,
            package_dims=PACKAGE_DIMS,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Saved {result['variant_count']} drafts under group {result['group_key']}."
        ))
        self.stdout.write(
            'Review and publish at: /ebay/variants/ (variant group detail page).'
        )
