"""One-time command to set up ANH set variant groups in the database."""
from django.core.management.base import BaseCommand
from ebay_manager.models import EbayListing


class Command(BaseCommand):
    help = 'Set up ANH Star Wars set variant groups from existing eBay listings'

    def handle(self, *args, **options):
        r2_prefix = 'trading-cards/sets/star-wars/a-new-hope-77'

        # Series 2, 1-Star: pk=31, eBay#326464328238 — 4 variants (101-104)
        l2 = EbayListing.objects.get(pk=31)
        l2.group_key = 'GRP-SW-ANH-S2-1STAR'
        l2.is_variant = True
        l2.variant_name = '1-Star #101'
        l2.parent_r2_prefix = r2_prefix
        l2.save()
        self.stdout.write(f'Updated pk=31: {l2.group_key} / {l2.variant_name}')

        for num in ['102', '103', '104']:
            v, created = EbayListing.objects.get_or_create(
                group_key='GRP-SW-ANH-S2-1STAR',
                variant_name=f'1-Star #{num}',
                defaults={
                    'title': l2.title,
                    'price': l2.price,
                    'sku': f'SW-ANH-S2-1STAR-{num}',
                    'status': 'active',
                    'is_variant': True,
                    'parent_r2_prefix': r2_prefix,
                    'category_id': l2.category_id,
                    'condition_id': l2.condition_id,
                    'item_specifics': l2.item_specifics,
                }
            )
            status = 'Created' if created else 'Already exists'
            self.stdout.write(f'  {status}: 1-Star #{num} pk={v.pk}')

        # Series 2, 2-Star: pk=18, eBay#326951892686 — 1 variant (101)
        l3 = EbayListing.objects.get(pk=18)
        l3.group_key = 'GRP-SW-ANH-S2-2STAR'
        l3.is_variant = True
        l3.variant_name = '2-Star #101'
        l3.parent_r2_prefix = r2_prefix
        l3.save()
        self.stdout.write(f'Updated pk=18: {l3.group_key} / {l3.variant_name}')

        self.stdout.write(self.style.SUCCESS('Done. ANH variant groups configured.'))
