"""Add mixed/103 variant to the ANH Series 1 eBay listing."""
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from ebay_manager.models import EbayListing
from ebay_manager.services.api_client import get_user_token
from non_sports_cards.r2_utils import get_r2_images


INVENTORY_ITEM_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item'
ITEM_GROUP_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item_group'
OFFER_URL = 'https://api.ebay.com/sell/inventory/v1/offer'

DEFAULT_POLICIES = {
    'payment_policy_id': '238949740015',
    'return_policy_id': '195880479015',
}


class Command(BaseCommand):
    help = 'Add mixed/103 variant to ANH Series 1 listing (326957340844)'

    def handle(self, *args, **options):
        token = get_user_token()
        if not token:
            self.stderr.write('No eBay user token available.')
            return

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
            'Content-Language': 'en-US',
        }

        # Get the existing Series 1 listing
        existing = EbayListing.objects.get(pk=19)
        group_key = existing.group_key  # GRP-SW-ANH-S1-1STAR
        self.stdout.write(f'Existing: {existing.title} / {existing.variant_name}')
        self.stdout.write(f'Group key: {group_key}')
        self.stdout.write(f'eBay item: {existing.ebay_item_id}')

        # Get images for mixed/103
        images = get_r2_images('trading-cards/sets/star-wars/anh/series-1/mixed/103/')
        image_urls = [img.get('url', '') for img in images if img.get('url')]
        self.stdout.write(f'Mixed #103 images: {len(image_urls)}')

        if not image_urls:
            self.stderr.write('No images found for mixed/103!')
            return

        # Step 1: Check existing inventory item SKU for the 1star/102
        existing_sku = existing.sku
        if not existing_sku:
            # Try to find the SKU from eBay
            self.stdout.write('No SKU in DB, checking eBay for existing SKUs...')
            r = requests.get(
                f'{INVENTORY_ITEM_URL}?limit=50',
                headers=headers, timeout=20,
            )
            if r.status_code == 200:
                for item in r.json().get('inventoryItems', []):
                    sku = item.get('sku', '')
                    title = item.get('product', {}).get('title', '')
                    if 'series 1' in title.lower() and 'star wars' in title.lower():
                        self.stdout.write(f'  Found SKU: {sku} -> {title[:60]}')
                        existing_sku = sku
                        break

        new_sku = 'SW-ANH-S1-MIXED-103'
        self.stdout.write(f'Existing SKU: {existing_sku}')
        self.stdout.write(f'New SKU: {new_sku}')

        # Step 2: Create inventory item for mixed/103
        aspects = dict(existing.item_specifics or {})
        # Convert string values to lists for eBay API
        for key, val in aspects.items():
            if isinstance(val, str):
                aspects[key] = [val]
        aspects['Set Condition'] = ['Mixed']

        payload = {
            'availability': {
                'shipToLocationAvailability': {'quantity': 1},
            },
            'condition': 'USED_EXCELLENT',
            'product': {
                'title': existing.title,
                'description': existing.description_html or existing.title,
                'imageUrls': image_urls[:24],
                'aspects': aspects,
            },
        }

        self.stdout.write(f'Creating inventory item {new_sku}...')
        r = requests.put(
            f'{INVENTORY_ITEM_URL}/{new_sku}',
            headers=headers, json=payload, timeout=20,
        )
        self.stdout.write(f'  Status: {r.status_code}')
        if r.status_code not in (200, 201, 204):
            self.stderr.write(f'  Error: {r.text[:500]}')
            return

        # Step 3: Create offer for mixed/103
        offer_payload = {
            'sku': new_sku,
            'marketplaceId': 'EBAY_US',
            'format': 'FIXED_PRICE',
            'listingDescription': existing.description_html or existing.title,
            'availableQuantity': 1,
            'categoryId': existing.category_id or '183052',
            'pricingSummary': {
                'price': {'value': str(existing.price), 'currency': 'USD'},
            },
            'listingPolicies': {
                'fulfillmentPolicyId': '119108501015',
                'paymentPolicyId': DEFAULT_POLICIES['payment_policy_id'],
                'returnPolicyId': DEFAULT_POLICIES['return_policy_id'],
            },
            'merchantLocationKey': 'SC-DEFAULT',
        }

        # Check for existing offer first
        existing_offer = requests.get(
            f'{OFFER_URL}?sku={new_sku}', headers=headers, timeout=20
        )
        if existing_offer.status_code == 200 and existing_offer.json().get('offers'):
            offer_id = existing_offer.json()['offers'][0]['offerId']
            self.stdout.write(f'Offer already exists: {offer_id}')
        else:
            self.stdout.write('Creating offer...')
            r2 = requests.post(OFFER_URL, headers=headers, json=offer_payload, timeout=20)
            self.stdout.write(f'  Status: {r2.status_code}')
            if r2.status_code in (200, 201):
                offer_id = r2.json().get('offerId', '')
                self.stdout.write(f'  Offer ID: {offer_id}')
            else:
                self.stderr.write(f'  Error: {r2.text[:500]}')
                offer_id = None

        # Step 4: Update the item group to include new variant
        self.stdout.write(f'Updating item group {group_key}...')
        group_r = requests.get(
            f'{ITEM_GROUP_URL}/{group_key}',
            headers=headers, timeout=20,
        )
        if group_r.status_code == 200:
            group_data = group_r.json()
            skus = group_data.get('variantSKUs', [])
            if new_sku not in skus:
                skus.append(new_sku)
                group_data['variantSKUs'] = skus
                specs = group_data.get('variesBy', {}).get('specifications', [])
                if specs:
                    values = specs[0].get('values', [])
                    if 'Mixed #103' not in values:
                        values.append('Mixed #103')
                        specs[0]['values'] = values
                r3 = requests.put(
                    f'{ITEM_GROUP_URL}/{group_key}',
                    headers=headers, json=group_data, timeout=20,
                )
                self.stdout.write(f'  Group update status: {r3.status_code}')
                if r3.status_code not in (200, 201, 204):
                    self.stdout.write(f'  Response: {r3.text[:300]}')
            else:
                self.stdout.write(f'  SKU already in group')
        else:
            self.stdout.write(f'  Group not found on eBay ({group_r.status_code}), may need manual setup')

        # Step 5: Save DB record
        variant, created = EbayListing.objects.get_or_create(
            group_key=group_key,
            variant_name='Mixed #103',
            defaults={
                'title': existing.title,
                'price': existing.price,
                'sku': new_sku,
                'status': 'active',
                'is_variant': True,
                'parent_r2_prefix': 'trading-cards/sets/star-wars/anh',
                'category_id': existing.category_id,
                'condition_id': existing.condition_id,
                'description_html': existing.description_html,
                'image_urls': image_urls,
                'item_specifics': existing.item_specifics,
                'ebay_item_id': existing.ebay_item_id,
                'listed_at': timezone.now(),
                'last_synced': timezone.now(),
            }
        )
        status = 'Created' if created else 'Already exists'
        self.stdout.write(f'DB record: {status} pk={variant.pk}')

        self.stdout.write(self.style.SUCCESS('Done. Mixed #103 variant added to Series 1.'))
