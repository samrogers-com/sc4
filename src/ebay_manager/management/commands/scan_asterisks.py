"""
Scan mixed-star card sets for ★ vs ★★ asterisk variants.

Uses Claude Vision API to analyze cards in 9-pocket sleeve page photos
stored on R2. Results are saved to the database for cross-set analysis.

Usage:
    # Dry run — show what would be scanned
    python manage.py scan_asterisks --dry-run

    # Scan all unscanned mixed sets
    python manage.py scan_asterisks --all

    # Scan a specific set
    python manage.py scan_asterisks --set trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/103

    # Re-scan a completed set
    python manage.py scan_asterisks --set <prefix> --rescan

    # Show summary of all scanned sets
    python manage.py scan_asterisks --report
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Scan mixed-star card sets for ★ vs ★★ asterisk variants using Claude Vision'

    def add_arguments(self, parser):
        parser.add_argument(
            '--set', type=str,
            help='R2 prefix for a specific set to scan'
        )
        parser.add_argument(
            '--all', action='store_true',
            help='Scan all unscanned mixed sets'
        )
        parser.add_argument(
            '--rescan', action='store_true',
            help='Re-scan already completed sets'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be scanned without doing it'
        )
        parser.add_argument(
            '--report', action='store_true',
            help='Show summary report of all scanned sets'
        )
        parser.add_argument(
            '--api-key', type=str,
            help='Override ANTHROPIC_API_KEY from settings'
        )

    def handle(self, *args, **options):
        from ebay_manager.services.asterisk_scanner import (
            find_unscanned_sets, scan_set,
        )
        from ebay_manager.models import SetScanStatus, CardAsteriskScan

        api_key = options.get('api_key') or getattr(settings, 'ANTHROPIC_API_KEY', '')

        if options['report']:
            self._show_report()
            return

        if options['set']:
            # Scan a specific set
            prefix = options['set']
            if options['dry_run']:
                self.stdout.write(f'Would scan: {prefix}')
                return

            existing = SetScanStatus.objects.filter(r2_prefix=prefix).first()
            if existing and existing.status == 'complete' and not options['rescan']:
                self.stdout.write(self.style.WARNING(
                    f'Already scanned: {prefix} (★{existing.single_star_count} '
                    f'★★{existing.double_star_count}). Use --rescan to re-scan.'
                ))
                return

            if options['rescan'] and existing:
                # Clear previous results
                CardAsteriskScan.objects.filter(scan_set=existing).delete()
                existing.status = 'pending'
                existing.scanned_cards = 0
                existing.single_star_count = 0
                existing.double_star_count = 0
                existing.unknown_count = 0
                existing.save()

            result = scan_set(
                prefix,
                api_key=api_key,
                callback=lambda msg: self.stdout.write(msg),
            )
            self.stdout.write(self.style.SUCCESS(
                f'Done: ★{result.single_star_count} ★★{result.double_star_count} '
                f'?{result.unknown_count}'
            ))
            return

        if options['all']:
            unscanned = find_unscanned_sets()
            if not unscanned:
                self.stdout.write(self.style.SUCCESS('All mixed sets already scanned.'))
                return

            if options['dry_run']:
                self.stdout.write(f'Would scan {len(unscanned)} sets:')
                for s in unscanned:
                    self.stdout.write(f'  {s["r2_prefix"]}')
                return

            self.stdout.write(f'Scanning {len(unscanned)} sets...')
            for i, s in enumerate(unscanned, 1):
                self.stdout.write(f'\n=== Set {i}/{len(unscanned)}: {s["r2_prefix"]} ===')
                try:
                    result = scan_set(
                        s['r2_prefix'],
                        api_key=api_key,
                        callback=lambda msg: self.stdout.write(msg),
                    )
                    self.stdout.write(self.style.SUCCESS(
                        f'  ★{result.single_star_count} ★★{result.double_star_count} '
                        f'?{result.unknown_count}'
                    ))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'  Failed: {e}'))

            self.stdout.write(self.style.SUCCESS(f'\nAll {len(unscanned)} sets processed.'))
            return

        # No flags — show help
        self.stdout.write('Use --all, --set <prefix>, --report, or --dry-run.')
        self.stdout.write('Run --dry-run first to see what would be scanned.')

    def _show_report(self):
        """Show summary of all scanned sets with cross-set analysis."""
        from ebay_manager.models import SetScanStatus, CardAsteriskScan

        scans = SetScanStatus.objects.all()
        if not scans.exists():
            self.stdout.write('No sets scanned yet.')
            return

        self.stdout.write('\n=== Scan Status ===')
        for s in scans:
            status_color = {
                'complete': self.style.SUCCESS,
                'scanning': self.style.WARNING,
                'error': self.style.ERROR,
                'pending': self.style.NOTICE,
            }.get(s.status, str)
            self.stdout.write(
                f'  {status_color(s.status.ljust(10))} {s.r2_prefix}'
                f'  ★{s.single_star_count} ★★{s.double_star_count} ?{s.unknown_count}'
            )

        # Cross-set analysis for complete scans
        complete = scans.filter(status='complete')
        if complete.count() >= 2:
            self.stdout.write('\n=== Cross-Set Analysis ===')

            # Collect all card data
            all_cards = {}  # card_number -> {set_number: asterisk_count}
            for scan in complete:
                for card in scan.cards.all():
                    if card.card_number not in all_cards:
                        all_cards[card.card_number] = {}
                    all_cards[card.card_number][scan.set_number] = card.asterisk_count

            # Find cards that could form complete ★ or ★★ sets
            single_star_available = set()
            double_star_available = set()
            for card_num, sets in sorted(all_cards.items()):
                for set_num, count in sets.items():
                    if count == 1:
                        single_star_available.add(card_num)
                    elif count == 2:
                        double_star_available.add(card_num)

            total_expected = complete.first().total_cards
            self.stdout.write(
                f'  ★ cards available: {len(single_star_available)}/{total_expected}'
            )
            self.stdout.write(
                f'  ★★ cards available: {len(double_star_available)}/{total_expected}'
            )

            missing_single = set(range(1, total_expected + 1)) - single_star_available
            missing_double = set(range(1, total_expected + 1)) - double_star_available
            if missing_single:
                self.stdout.write(
                    f'  Missing ★: {sorted(missing_single)}'
                )
            if missing_double:
                self.stdout.write(
                    f'  Missing ★★: {sorted(missing_double)}'
                )
