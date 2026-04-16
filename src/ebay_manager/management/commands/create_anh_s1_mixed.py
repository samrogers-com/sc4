"""Create multi-variant listing for ANH Series 1 Mixed sets (103-106)."""
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from ebay_manager.models import EbayListing
from ebay_manager.services.api_client import get_user_token
from non_sports_cards.r2_utils import get_r2_images, _cache


INVENTORY_ITEM_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item'
ITEM_GROUP_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item_group'
OFFER_URL = 'https://api.ebay.com/sell/inventory/v1/offer'

POLICIES = {
    'fulfillment_policy_id': '119108501015',
    'payment_policy_id': '238949740015',
    'return_policy_id': '195880479015',
}

TITLE = '1977 Topps Star Wars Series 1 Complete Base Set 1-66'
GROUP_KEY = 'GRP-SW-ANH-S1-MIXED'
CATEGORY_ID = '183052'
R2_PREFIX = 'trading-cards/sets/star-wars/a-new-hope-77'

ASPECTS = {
    'Franchise': ['Star Wars'],
    'Manufacturer': ['Topps'],
    'Set': ['Star Wars Series 1'],
    'Year Manufactured': ['1977'],
    'Genre': ['Sci-Fi'],
    'Movie': ['Star Wars: A New Hope'],
    'Configuration': ['Set'],
    'Type': ['Non-Sport Trading Card'],
    'Card Size': ['Standard'],
}

VARIANTS = [
    {'num': '103', 'price': '998.95', 'sku': 'SW-ANH-S1-MIXED-103'},
    {'num': '104', 'price': '978.95', 'sku': 'SW-ANH-S1-MIXED-104'},
    {'num': '105', 'price': '958.95', 'sku': 'SW-ANH-S1-MIXED-105'},
    {'num': '106', 'price': '938.95', 'sku': 'SW-ANH-S1-MIXED-106'},
]


class Command(BaseCommand):
    help = 'Create multi-variant eBay listing for ANH Series 1 Mixed sets'

    def handle(self, *args, **options):
        _cache.clear()

        token = get_user_token()
        if not token:
            self.stderr.write('No eBay user token.')
            return

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
            'Content-Language': 'en-US',
        }

        all_image_urls = []
        variant_displays = []

        # Step 1: Create inventory items for each variant
        for v in VARIANTS:
            r2_path = f'trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/{v["num"]}/'
            images = get_r2_images(r2_path)
            image_urls = [img.get('url', '') for img in images if img.get('url')]
            self.stdout.write(f'Mixed #{v["num"]}: {len(image_urls)} images, ${v["price"]}')

            if not image_urls:
                self.stderr.write(f'  No images for {v["num"]}!')
                continue

            all_image_urls.extend(image_urls[:6])
            display = f'Mixed #{v["num"]}'
            variant_displays.append(display)

            aspects = dict(ASPECTS)
            aspects['Set Condition'] = ['Mixed']
            aspects['Set Number'] = [display]

            payload = {
                'availability': {'shipToLocationAvailability': {'quantity': 1}},
                'condition': 'USED_EXCELLENT',
                'product': {
                    'title': TITLE,
                    'description': TITLE,
                    'imageUrls': image_urls[:24],
                    'aspects': aspects,
                },
                'packageWeightAndSize': {
                    'weight': {'value': 8, 'unit': 'OUNCE'},
                    'dimensions': {'length': 9, 'width': 6, 'height': 2, 'unit': 'INCH'},
                },
            }

            r = requests.put(
                f'{INVENTORY_ITEM_URL}/{v["sku"]}',
                headers=headers, json=payload, timeout=20,
            )
            self.stdout.write(f'  Inventory item: {r.status_code}')
            if r.status_code not in (200, 201, 204):
                self.stderr.write(f'  Error: {r.text[:300]}')
                return

        # Step 2: Create inventory item group
        self.stdout.write('Creating item group...')
        group_aspects = dict(ASPECTS)
        group_aspects['Set Condition'] = ['Mixed']

        group_payload = {
            'title': TITLE,
            'description': TITLE,
            'imageUrls': all_image_urls[:24],
            'aspects': group_aspects,
            'variantSKUs': [v['sku'] for v in VARIANTS],
            'variesBy': {
                'aspectsImageVariesBy': ['Set Number'],
                'specifications': [
                    {
                        'name': 'Set Number',
                        'values': variant_displays,
                    }
                ],
            },
        }

        r = requests.put(
            f'{ITEM_GROUP_URL}/{GROUP_KEY}',
            headers=headers, json=group_payload, timeout=20,
        )
        self.stdout.write(f'  Group: {r.status_code}')
        if r.status_code not in (200, 201, 204):
            self.stderr.write(f'  Error: {r.text[:500]}')
            return

        # Step 3: Create offers for each variant
        offer_ids = []
        for v in VARIANTS:
            # Check existing offer
            existing = requests.get(
                f'{OFFER_URL}?sku={v["sku"]}', headers=headers, timeout=20
            )
            if existing.status_code == 200 and existing.json().get('offers'):
                offer_id = existing.json()['offers'][0]['offerId']
                self.stdout.write(f'  Offer exists for {v["sku"]}: {offer_id}')
                # Update price
                update = {
                    'pricingSummary': {'price': {'value': v['price'], 'currency': 'USD'}},
                }
                requests.put(
                    f'{OFFER_URL}/{offer_id}', headers=headers, json=update, timeout=20
                )
            else:
                offer_payload = {
                    'sku': v['sku'],
                    'marketplaceId': 'EBAY_US',
                    'format': 'FIXED_PRICE',
                    'listingDescription': TITLE,
                    'availableQuantity': 1,
                    'categoryId': CATEGORY_ID,
                    'pricingSummary': {
                        'price': {'value': v['price'], 'currency': 'USD'},
                    },
                    'listingPolicies': {
                        'fulfillmentPolicyId': POLICIES['fulfillment_policy_id'],
                        'paymentPolicyId': POLICIES['payment_policy_id'],
                        'returnPolicyId': POLICIES['return_policy_id'],
                    },
                    'merchantLocationKey': 'SC-DEFAULT',
                }
                r2 = requests.post(OFFER_URL, headers=headers, json=offer_payload, timeout=20)
                self.stdout.write(f'  Offer for {v["sku"]}: {r2.status_code}')
                if r2.status_code in (200, 201):
                    offer_id = r2.json().get('offerId', '')
                else:
                    self.stderr.write(f'  Error: {r2.text[:300]}')
                    continue
            offer_ids.append(offer_id)

        # Step 4: Publish
        self.stdout.write('Publishing group...')
        pub = requests.post(
            f'{ITEM_GROUP_URL}/{GROUP_KEY}/publish',
            headers=headers, timeout=20,
        )
        self.stdout.write(f'  Publish: {pub.status_code}')

        if pub.status_code in (200, 201):
            listing_id = pub.json().get('listingId', '')
            self.stdout.write(self.style.SUCCESS(f'  Listed! eBay #{listing_id}'))
        else:
            # Try publishing individual offers
            self.stdout.write(f'  Group publish failed: {pub.text[:300]}')
            self.stdout.write('  Trying individual offer publish...')
            listing_id = None
            for oid in offer_ids:
                r3 = requests.post(
                    f'{OFFER_URL}/{oid}/publish', headers=headers, timeout=20
                )
                self.stdout.write(f'    Offer {oid}: {r3.status_code} {r3.text[:200]}')
                if r3.status_code in (200, 201):
                    listing_id = r3.json().get('listingId', '')

        # Step 5: Save DB records
        r2_images_by_num = {}
        for v in VARIANTS:
            imgs = get_r2_images(f'trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/{v["num"]}/')
            r2_images_by_num[v['num']] = [i.get('url', '') for i in imgs if i.get('url')]

        for v in VARIANTS:
            obj, created = EbayListing.objects.update_or_create(
                group_key=GROUP_KEY,
                variant_name=f'Mixed #{v["num"]}',
                defaults={
                    'title': TITLE,
                    'price': float(v['price']),
                    'sku': v['sku'],
                    'status': 'active',
                    'is_variant': True,
                    'parent_r2_prefix': R2_PREFIX,
                    'category_id': CATEGORY_ID,
                    'image_urls': r2_images_by_num.get(v['num'], []),
                    'item_specifics': ASPECTS,
                    'ebay_listing_url': f'https://www.ebay.com/itm/{listing_id}' if listing_id else None,
                    'listed_at': timezone.now(),
                    'last_synced': timezone.now(),
                }
            )
            status = 'Created' if created else 'Updated'
            self.stdout.write(f'  DB: {status} Mixed #{v["num"]} pk={obj.pk}')

        self.stdout.write(self.style.SUCCESS('Done.'))
