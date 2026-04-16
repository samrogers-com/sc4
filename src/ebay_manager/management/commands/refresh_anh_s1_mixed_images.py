"""Refresh eBay inventory-item imageUrls for the Star Wars ANH Series 1 Mixed variants.

Commit 19a9faf renamed the R2 prefix from `anh/` to `a-new-hope-77/` but the
already-published eBay inventory items still reference the old path, so the
live listing shows broken images.

This command:
  1. Reads the current inventory item from eBay for each SKU
  2. Replaces its imageUrls with the current R2 URLs at the new nested path
  3. PUTs the inventory item back (preserves everything else eBay already has)
  4. Updates the local DB image_urls for the matching EbayListing rows

It does NOT re-publish, touch offers, or change the item group. Side effects
are limited to fixing image URLs.
"""
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from ebay_manager.models import EbayListing
from ebay_manager.services.api_client import get_user_token
from non_sports_cards.r2_utils import _cache, get_r2_images


INVENTORY_ITEM_URL = 'https://api.ebay.com/sell/inventory/v1/inventory_item'

# Map each SKU to its new R2 folder
VARIANTS = [
    {'sku': 'SW-ANH-S1-MIXED-103', 'r2_path': 'trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/103/'},
    {'sku': 'SW-ANH-S1-MIXED-104', 'r2_path': 'trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/104/'},
    {'sku': 'SW-ANH-S1-MIXED-105', 'r2_path': 'trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/105/'},
    {'sku': 'SW-ANH-S1-MIXED-106', 'r2_path': 'trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/106/'},
]


class Command(BaseCommand):
    help = 'Refresh eBay inventory-item imageUrls for ANH Series 1 Mixed variants after R2 rename.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print plan, do not push to eBay.')

    def handle(self, *args, **options):
        _cache.clear()
        dry_run = options['dry_run']

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

        for v in VARIANTS:
            sku = v['sku']
            r2_path = v['r2_path']

            images = get_r2_images(r2_path)
            image_urls = [img.get('url', '') for img in images if img.get('url')]
            if not image_urls:
                self.stderr.write(f'{sku}: no images at {r2_path} — skipping.')
                continue

            # GET current inventory item so we preserve title/aspects/etc
            r = requests.get(f'{INVENTORY_ITEM_URL}/{sku}', headers=headers, timeout=20)
            if r.status_code != 200:
                self.stderr.write(f'{sku}: GET returned {r.status_code}: {r.text[:300]}')
                continue

            item = r.json()
            old_urls = item.get('product', {}).get('imageUrls', [])
            self.stdout.write(f'{sku}: {len(old_urls)} old -> {len(image_urls[:24])} new')
            if old_urls[:1]:
                self.stdout.write(f'   was: {old_urls[0]}')
            self.stdout.write(f'   now: {image_urls[0]}')

            if dry_run:
                continue

            # Replace imageUrls and PUT back. eBay PUT is "create or replace",
            # so we must pass the full object back, not just the changed field.
            item.setdefault('product', {})['imageUrls'] = image_urls[:24]

            put = requests.put(
                f'{INVENTORY_ITEM_URL}/{sku}',
                headers=headers, json=item, timeout=30,
            )
            if put.status_code not in (200, 201, 204):
                self.stderr.write(f'{sku}: PUT failed {put.status_code}: {put.text[:400]}')
                continue
            self.stdout.write(self.style.SUCCESS(f'{sku}: inventory item updated ({put.status_code})'))

            # Update any EbayListing rows for this SKU with the new URLs
            updated = EbayListing.objects.filter(sku=sku).update(
                image_urls=image_urls,
                last_synced=timezone.now(),
            )
            self.stdout.write(f'{sku}: {updated} DB rows refreshed')

        self.stdout.write(self.style.SUCCESS('Done.'))
