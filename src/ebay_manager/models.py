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

    # Description
    description_html = models.TextField(null=True, blank=True)

    # Images (R2 URLs)
    image_urls = models.JSONField(default=list, blank=True)

    # Item specifics
    item_specifics = models.JSONField(default=dict, blank=True)

    # Weight (product only, packaging added automatically)
    # Store as lbs + oz for easy entry. Ship weight auto-calculated.
    weight_lbs = models.IntegerField(default=0, help_text='Product weight - pounds')
    weight_oz = models.IntegerField(default=0, help_text='Product weight - ounces')

    # Shipping & returns
    shipping_service = models.CharField(max_length=50, default='USPSGroundAdvantage')
    shipping_cost = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    returns_accepted = models.BooleanField(default=True)

    # Packaging overhead: 4oz box + 1oz bubble wrap = 5oz
    PACKAGING_OZ = 5

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
    def product_weight_oz(self):
        """Total product weight in ounces."""
        return (self.weight_lbs * 16) + self.weight_oz

    @property
    def ship_weight_oz(self):
        """Total shipping weight in ounces (product + packaging)."""
        return self.product_weight_oz + self.PACKAGING_OZ

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

    def __str__(self):
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
