"""Create a PostDraft for a given eBay listing + platform via Claude Haiku.

Usage:
    python manage.py generate_draft --sku 1988-TOPPS-HOWARD-THE-DUCK-BOX --platform instagram
    python manage.py generate_draft --item-id 327106630765 --platform facebook
    python manage.py generate_draft --sku ... --platform instagram --model claude-sonnet-4-6
    python manage.py generate_draft --sku ... --platform instagram --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from ebay_manager.models import EbayListing
from social_manager.models import PostDraft
from social_manager.services.caption_generator import (
    CaptionGenerationError,
    generate_caption,
)


class Command(BaseCommand):
    help = 'Generate a draft social-media caption for an eBay listing via Claude.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--sku', type=str, help='EbayListing.sku')
        group.add_argument('--item-id', type=str, help='EbayListing.ebay_item_id')
        parser.add_argument(
            '--platform',
            required=True,
            choices=[
                'instagram', 'facebook', 'tiktok', 'youtube', 'reddit', 'pinterest',
            ],
        )
        parser.add_argument(
            '--model',
            default='claude-haiku-4-5',
            help='Anthropic model id (default: claude-haiku-4-5)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print the result but do not save a PostDraft',
        )

    def handle(self, *args, **options):
        if options['sku']:
            try:
                listing = EbayListing.objects.get(sku=options['sku'])
            except EbayListing.DoesNotExist as exc:
                raise CommandError(f'No EbayListing with sku={options["sku"]!r}') from exc
        else:
            try:
                listing = EbayListing.objects.get(ebay_item_id=options['item_id'])
            except EbayListing.DoesNotExist as exc:
                raise CommandError(
                    f'No EbayListing with ebay_item_id={options["item_id"]!r}'
                ) from exc

        self.stdout.write(f'Listing: {listing.title} (${listing.price})')
        self.stdout.write(f'Platform: {options["platform"]}  model: {options["model"]}')

        try:
            result = generate_caption(
                listing, platform=options['platform'], model=options['model'],
            )
        except CaptionGenerationError as exc:
            raise CommandError(f'Caption generation failed: {exc}') from exc

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Caption:'))
        self.stdout.write(f'  {result["caption"]}')
        self.stdout.write(self.style.SUCCESS('Hashtags:'))
        self.stdout.write(f'  {" ".join(result["hashtags"])}')
        self.stdout.write(self.style.NOTICE(f'Cost: ${result["cost_usd"]}'))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('--dry-run: not saved'))
            return

        draft = PostDraft.objects.create(
            listing=listing,
            caption=result['caption'],
            hashtags=' '.join(result['hashtags']),
            llm_model_used=options['model'],
            generation_cost_usd=result['cost_usd'],
            status='pending',
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSaved PostDraft id={draft.id} status={draft.status}'
            )
        )
