from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class EbayListing(models.Model):
    """Tracks an eBay listing linked to any inventory item."""

    # Link to any inventory item via GenericForeignKey (optional until matched)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    inventory_item = GenericForeignKey('content_type', 'object_id')

    # eBay data
    ebay_item_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    ebay_listing_url = models.URLField(max_length=500, null=True, blank=True)

    # Listing details
    title = models.CharField(max_length=80)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    market_mean_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Top quartile mean of active eBay listings for similar items'
    )
    suggested_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Market mean minus $1.05 (target selling price)'
    )
    quantity = models.IntegerField(default=1)
    category_id = models.CharField(max_length=10, null=True, blank=True)
    condition_id = models.CharField(max_length=5, null=True, blank=True)
    sku = models.CharField(max_length=50, null=True, blank=True)

    # Status
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Submission'),
        ('active', 'Active on eBay'),
        ('sold', 'Sold'),
        ('ended', 'Ended'),
        ('error', 'Error'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Multi-variant support — groups multiple listings (Box 1, Box 2, etc.)
    group_key = models.CharField(
        max_length=50, null=True, blank=True, db_index=True,
        help_text='eBay inventory item group key — ties variants together'
    )
    is_variant = models.BooleanField(
        default=False,
        help_text='True if this listing is part of a multi-variant group'
    )
    variant_name = models.CharField(
        max_length=50, null=True, blank=True,
        help_text='Variant display name (e.g. "Box 1", "Box 2")'
    )
    parent_r2_prefix = models.CharField(
        max_length=200, null=True, blank=True,
        help_text='Parent R2 folder for variant groups (e.g. trading-cards/boxes/space-1999)'
    )

    # Description
    description_html = models.TextField(null=True, blank=True)

    # Images (R2 URLs)
    image_urls = models.JSONField(default=list, blank=True)

    # Item specifics
    item_specifics = models.JSONField(default=dict, blank=True)

    # Packaging configuration — determines box size, weight overhead, and shipping policy
    PACKAGING_CONFIGS = [
        ('sealed_box', 'Cardboard Box'),
        ('raw_stacked', 'Raw Stacked Cards (6x4x2)'),
        ('9_pocket_single', '9-Pocket Sheets Single Set (13x10x2)'),
        ('9_pocket_multi', '9-Pocket Sheets Multiple Sets (13x10x3)'),
        ('custom', 'Custom / Other'),
    ]
    packaging_config = models.CharField(
        max_length=20, choices=PACKAGING_CONFIGS, default='sealed_box',
        help_text='Determines box size, packaging weight, and shipping policy'
    )

    # Packaging specs per config (class-level, not DB fields)
    # {config: (box_length, box_width, box_height, box_weight_oz, bubble_wrap_oz, fulfillment_policy_id)}
    PACKAGING_SPECS = {
        'sealed_box':       (None, None, None, 4, 1, '119108501015'),   # NS Boxes Calculated
        'raw_stacked':      (6, 4, 2, 2, 0, '282295444015'),           # Calculated Trading Cards Boxes
        '9_pocket_single':  (13, 10, 2, 5, 2, '282295444015'),         # Calculated Trading Cards Boxes
        '9_pocket_multi':   (13, 10, 3, 6, 2, '282295444015'),         # Calculated Trading Cards Boxes
        'custom':           (None, None, None, 4, 1, '282295444015'),   # Calculated Trading Cards Boxes
    }

    # Custom package dimensions (for sealed_box/custom where size varies)
    package_length = models.IntegerField(default=0, help_text='Package length in inches')
    package_width = models.IntegerField(default=0, help_text='Package width in inches')
    package_height = models.IntegerField(default=0, help_text='Package height in inches')

    # Weight (product only, packaging added automatically from config)
    weight_lbs = models.IntegerField(default=0, help_text='Product weight - pounds')
    weight_oz = models.IntegerField(default=0, help_text='Product weight - ounces')

    # Shipping & returns
    shipping_service = models.CharField(max_length=50, default='USPSGroundAdvantage')
    shipping_cost = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    returns_accepted = models.BooleanField(default=True)

    # Dates
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    listed_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Performance
    view_count = models.IntegerField(default=0)
    watch_count = models.IntegerField(default=0)

    # User
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'ebay_listings'
        ordering = ['-created_at']

    @property
    def packaging_spec(self):
        """Get the packaging spec tuple for the current config."""
        return self.PACKAGING_SPECS.get(self.packaging_config, self.PACKAGING_SPECS['sealed_box'])

    @property
    def packaging_overhead_oz(self):
        """Total packaging overhead (box + bubble wrap) in ounces."""
        spec = self.packaging_spec
        return spec[3] + spec[4]  # box_weight + bubble_wrap

    @property
    def box_dimensions(self):
        """Box dimensions as dict or None. Custom dims override config defaults."""
        if self.package_length and self.package_width and self.package_height:
            return {'length': self.package_length, 'width': self.package_width, 'height': self.package_height}
        spec = self.packaging_spec
        if spec[0]:
            return {'length': spec[0], 'width': spec[1], 'height': spec[2]}
        return None

    @property
    def fulfillment_policy_id(self):
        """eBay fulfillment (shipping) policy ID for this packaging config."""
        return self.packaging_spec[5]

    @property
    def product_weight_oz(self):
        """Total product weight in ounces."""
        return (self.weight_lbs * 16) + self.weight_oz

    @property
    def ship_weight_oz(self):
        """Total shipping weight in ounces (product + packaging)."""
        return self.product_weight_oz + self.packaging_overhead_oz

    @property
    def ship_weight_display(self):
        """Shipping weight formatted as 'X lb Y oz'."""
        total_oz = self.ship_weight_oz
        lbs = total_oz // 16
        oz = total_oz % 16
        if lbs and oz:
            return f"{lbs} lb {oz} oz"
        elif lbs:
            return f"{lbs} lb"
        elif oz:
            return f"{oz} oz"
        return "—"

    @property
    def packaging_summary(self):
        """Human-readable packaging summary."""
        spec = self.packaging_spec
        dims = f"{spec[0]}x{spec[1]}x{spec[2]}" if spec[0] else "varies"
        overhead = spec[3] + spec[4]
        return f"{dims} box, {overhead}oz packaging"

    def get_variant_group(self):
        """Get all listings in this variant group, ordered by variant name."""
        if not self.group_key:
            return EbayListing.objects.none()
        return EbayListing.objects.filter(group_key=self.group_key).order_by('variant_name')

    @property
    def variant_count(self):
        """Number of variants in this group."""
        if not self.group_key:
            return 0
        return EbayListing.objects.filter(group_key=self.group_key).count()

    def __str__(self):
        if self.is_variant and self.variant_name:
            return f"[{self.status}] {self.title} — {self.variant_name} (${self.price})"
        return f"[{self.status}] {self.title} (${self.price})"


class EbayOrder(models.Model):
    """Tracks a sold eBay order with full lifecycle."""

    order_id = models.CharField(max_length=50, unique=True)
    buyer_username = models.CharField(max_length=100)
    buyer_name = models.CharField(max_length=200, null=True, blank=True)

    # Financials
    order_total = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    ebay_fees = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    shipping_cost_actual = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_basis = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    net_profit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Lifecycle status
    ORDER_STATUSES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('shipped', 'Shipped'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('return_requested', 'Return Requested'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    order_status = models.CharField(max_length=30, choices=ORDER_STATUSES, default='pending')
    payment_status = models.CharField(max_length=30, null=True, blank=True)

    # Dates
    creation_date = models.DateTimeField()
    paid_date = models.DateTimeField(null=True, blank=True)
    shipped_date = models.DateTimeField(null=True, blank=True)
    estimated_delivery_date = models.DateTimeField(null=True, blank=True)
    delivered_date = models.DateTimeField(null=True, blank=True)

    # Shipping & tracking
    tracking_number = models.CharField(max_length=100, null=True, blank=True)
    shipping_carrier = models.CharField(max_length=50, null=True, blank=True)
    shipping_service = models.CharField(max_length=100, null=True, blank=True)
    ship_to_address = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ebay_orders'
        ordering = ['-creation_date']

    @property
    def net_to_seller(self):
        """Order total minus eBay fees."""
        if self.ebay_fees is not None:
            return self.order_total - self.ebay_fees
        return None

    def __str__(self):
        return f"Order {self.order_id} - {self.buyer_username} (${self.order_total})"


class EbayOrderItem(models.Model):
    """Line item within an eBay order."""

    order = models.ForeignKey(EbayOrder, on_delete=models.CASCADE, related_name='items')
    listing = models.ForeignKey(EbayListing, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')

    ebay_item_id = models.CharField(max_length=20)
    title = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'ebay_order_items'

    def __str__(self):
        return f"{self.title} x{self.quantity} @ ${self.price}"


class SetScanStatus(models.Model):
    """Tracks which card sets have been scanned for asterisk variants.

    Each record represents one set (e.g. mixed/103) and its scan progress.
    Used to avoid re-scanning sets and to show scan status in the UI.
    """
    SCAN_STATUSES = [
        ('pending', 'Pending'),
        ('scanning', 'Scanning'),
        ('complete', 'Complete'),
        ('error', 'Error'),
    ]

    r2_prefix = models.CharField(
        max_length=300, unique=True,
        help_text='Full R2 path e.g. trading-cards/sets/star-wars/a-new-hope-77/series-1/mixed/103'
    )
    group_key = models.CharField(
        max_length=50, null=True, blank=True,
        help_text='EbayListing variant group key if linked'
    )
    series = models.CharField(
        max_length=50, null=True, blank=True,
        help_text='Series name e.g. series-1'
    )
    set_number = models.CharField(
        max_length=10, null=True, blank=True,
        help_text='Set number e.g. 103'
    )
    status = models.CharField(max_length=20, choices=SCAN_STATUSES, default='pending')
    total_cards = models.IntegerField(default=66, help_text='Expected card count for this series')
    scanned_cards = models.IntegerField(default=0)
    single_star_count = models.IntegerField(default=0, help_text='Cards with ★')
    double_star_count = models.IntegerField(default=0, help_text='Cards with ★★')
    unknown_count = models.IntegerField(default=0, help_text='Cards that could not be read')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'card_set_scan_status'
        ordering = ['r2_prefix']

    def __str__(self):
        return f"[{self.status}] {self.r2_prefix} — ★{self.single_star_count} ★★{self.double_star_count}"


class CardAsteriskScan(models.Model):
    """Per-card asterisk detection result from Claude Vision API.

    Each record is one card in one set, with the detected ★ or ★★ count,
    card number, title, and confidence score.
    """
    scan_set = models.ForeignKey(
        SetScanStatus, on_delete=models.CASCADE, related_name='cards'
    )
    card_number = models.IntegerField(help_text='Card number (1-66 for Series 1)')
    asterisk_count = models.IntegerField(
        default=0,
        help_text='1 for ★, 2 for ★★, 0 for unknown/unreadable'
    )
    confidence = models.FloatField(
        default=0.0,
        help_text='Confidence score 0.0-1.0 from Claude analysis'
    )
    page_number = models.IntegerField(help_text='Photo page number (1-16)')
    position = models.IntegerField(help_text='Position in 9-pocket page (1-9)')
    card_title = models.CharField(
        max_length=200, null=True, blank=True,
        help_text='Card title text e.g. "Rebels defend their starship!"'
    )
    image_crop_url = models.CharField(
        max_length=500, null=True, blank=True,
        help_text='R2 URL of the cropped card image'
    )
    raw_response = models.TextField(
        null=True, blank=True,
        help_text='Raw Claude API response for debugging'
    )
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'card_asterisk_scans'
        ordering = ['scan_set', 'card_number']
        unique_together = [('scan_set', 'card_number')]

    def __str__(self):
        stars = '★' * self.asterisk_count if self.asterisk_count else '?'
        return f"#{self.card_number} {stars} — {self.card_title or 'Unknown'}"
