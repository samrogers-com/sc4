# Generated for the auction-listing-support feature.
#
# Adds five fields to ebay_manager.EbayListing supporting auction-format
# listings via eBay's Inventory API:
#   - listing_format (FIXED_PRICE / AUCTION; default FIXED_PRICE)
#   - listing_duration (DAYS_1..DAYS_10 / GTC; default GTC)
#   - auction_start_price (nullable Decimal)
#   - auction_reserve_price (nullable Decimal)
#   - scheduled_start_time (nullable DateTime)
#
# Defaults are chosen so existing rows remain semantically identical to
# their pre-migration behaviour: every existing listing was implicitly a
# fixed-price GTC offer, which is exactly what the defaults encode.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ebay_manager', '0009_card_asterisk_scan_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='ebaylisting',
            name='listing_format',
            field=models.CharField(
                choices=[('FIXED_PRICE', 'Fixed Price'), ('AUCTION', 'Auction')],
                default='FIXED_PRICE',
                help_text='Fixed-price (Buy It Now) or auction listing',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='ebaylisting',
            name='listing_duration',
            field=models.CharField(
                choices=[
                    ('DAYS_1', '1 Day'),
                    ('DAYS_3', '3 Days'),
                    ('DAYS_5', '5 Days'),
                    ('DAYS_7', '7 Days'),
                    ('DAYS_10', '10 Days'),
                    ('GTC', 'Good Til Cancelled'),
                ],
                default='GTC',
                help_text='Listing duration. GTC for fixed-price; DAYS_N for auctions.',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='ebaylisting',
            name='auction_start_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Starting bid for auctions. Falls back to price if not set.',
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='ebaylisting',
            name='auction_reserve_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Reserve price for auctions. Optional.',
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='ebaylisting',
            name='scheduled_start_time',
            field=models.DateTimeField(
                blank=True,
                help_text='Scheduled start time (UTC). When set, eBay holds publish until this time. $0.10 fee.',
                null=True,
            ),
        ),
    ]
