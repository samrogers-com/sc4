"""
Nightly eBay sync management command.

Syncs listings and orders from eBay, cross-references R2 photos,
and generates a gap report.

Usage:
    python manage.py ebay_sync              # Full sync + report
    python manage.py ebay_sync --report     # Gap report only (no API calls)
    python manage.py ebay_sync --sync-only  # Sync only (no report)
"""
import os
import re
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Sync eBay listings/orders and compare with R2 photo inventory'

    def add_arguments(self, parser):
        parser.add_argument('--report', action='store_true', help='Only run gap report')
        parser.add_argument('--sync-only', action='store_true', help='Only sync, skip report')
        parser.add_argument('--days', type=int, default=365, help='Order history days')

    def handle(self, *args, **options):
        report_only = options['report']
        sync_only = options['sync_only']
        days = options['days']

        if not report_only:
            self._sync_listings()
            self._sync_orders(days)

        if not sync_only:
            self._gap_report()

    def _sync_listings(self):
        self.stdout.write(self.style.NOTICE('Syncing listings from eBay...'))
        try:
            from ebay_manager.services.listing_sync import sync_active_listings
            result = sync_active_listings()
            self.stdout.write(self.style.SUCCESS(
                f"Listings: {result['created']} new, {result['updated']} updated "
                f"({result['total']} from eBay)"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Listing sync failed: {e}'))

    def _sync_orders(self, days):
        self.stdout.write(self.style.NOTICE('Syncing orders from eBay...'))
        try:
            from ebay_manager.services.fulfillment import sync_orders_to_db
            result = sync_orders_to_db(days=days)
            self.stdout.write(self.style.SUCCESS(
                f"Orders: {result['created']} new, {result['updated']} updated "
                f"({result['total']} from eBay)"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Order sync failed: {e}'))

    def _gap_report(self):
        """Compare R2 photos with eBay listings to find gaps."""
        self.stdout.write(self.style.NOTICE('\nGenerating gap report...'))

        from ebay_manager.models import EbayListing
        import boto3

        # Get R2 product folders
        r2_endpoint = os.environ.get('R2_ENDPOINT_URL', '')
        r2_key = os.environ.get('R2_ACCESS_KEY_ID', '')
        r2_secret = os.environ.get('R2_SECRET_ACCESS_KEY', '')

        if not all([r2_endpoint, r2_key, r2_secret]):
            self.stdout.write(self.style.WARNING('R2 credentials not set, skipping gap report'))
            return

        try:
            s3 = boto3.client('s3',
                endpoint_url=r2_endpoint,
                aws_access_key_id=r2_key,
                aws_secret_access_key=r2_secret,
                region_name='auto',
                config=boto3.session.Config(signature_version='s3v4'),
            )

            # List R2 product folders
            r2_folders = {}
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket='samscollectibles'):
                for obj in page.get('Contents', []):
                    parts = obj['Key'].split('/')
                    if len(parts) >= 3:
                        folder = '/'.join(parts[:3])
                        r2_folders.setdefault(folder, 0)
                        r2_folders[folder] += 1

            # Get active eBay listings
            active_listings = EbayListing.objects.filter(status='active')
            active_titles = {l.title.lower(): l for l in active_listings}

            self.stdout.write(f'\nR2 product folders: {len(r2_folders)}')
            self.stdout.write(f'Active eBay listings: {active_listings.count()}')

            # Find R2 folders with no matching listing
            self.stdout.write(self.style.WARNING('\n--- R2 PHOTOS WITH NO ACTIVE LISTING ---'))
            r2_no_listing = 0
            for folder, count in sorted(r2_folders.items()):
                # Skip ebay-imports (those came FROM eBay)
                if 'ebay-imports' in folder:
                    continue
                # Extract keywords from folder name
                folder_words = set(re.split(r'[-_/]', folder.lower()))
                matched = False
                for title in active_titles:
                    title_words = set(re.split(r'[\s-]+', title.lower()))
                    overlap = folder_words & title_words
                    if len(overlap) >= 3:
                        matched = True
                        break
                if not matched:
                    self.stdout.write(f'  {folder} ({count} files)')
                    r2_no_listing += 1

            self.stdout.write(f'  Total: {r2_no_listing} products with photos but no listing')

            # Find listings with no R2 photos
            self.stdout.write(self.style.WARNING('\n--- ACTIVE LISTINGS WITH NO R2 PHOTOS ---'))
            no_photos = 0
            for listing in active_listings:
                title_words = set(re.split(r'[\s-]+', listing.title.lower()))
                matched = False
                for folder in r2_folders:
                    if 'ebay-imports' in folder:
                        continue
                    folder_words = set(re.split(r'[-_/]', folder.lower()))
                    overlap = title_words & folder_words
                    if len(overlap) >= 3:
                        matched = True
                        break
                if not matched:
                    has_ebay_imgs = bool(listing.image_urls)
                    self.stdout.write(
                        f'  {listing.title[:60]} '
                        f'{"(has eBay imgs)" if has_ebay_imgs else "(NO IMAGES)"}'
                    )
                    no_photos += 1

            self.stdout.write(f'  Total: {no_photos} listings without R2 photos')

            # Summary
            self.stdout.write(self.style.SUCCESS(
                f'\n=== GAP REPORT COMPLETE ==='
                f'\n  R2 products without listings: {r2_no_listing}'
                f'\n  Listings without R2 photos: {no_photos}'
                f'\n  Report generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}'
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Gap report failed: {e}'))
