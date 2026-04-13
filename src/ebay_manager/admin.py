from django.contrib import admin
from .models import EbayListing, EbayOrder, EbayOrderItem


class EbayOrderItemInline(admin.TabularInline):
    model = EbayOrderItem
    extra = 0
    readonly_fields = ('ebay_item_id', 'title', 'sku', 'quantity', 'price')


@admin.register(EbayListing)
class EbayListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'price', 'sku', 'ebay_item_id', 'view_count', 'watch_count', 'created_at')
    list_filter = ('status', 'category_id')
    search_fields = ('title', 'sku', 'ebay_item_id')
    readonly_fields = ('created_at', 'updated_at', 'last_synced')


@admin.register(EbayOrder)
class EbayOrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'buyer_username', 'order_total', 'order_status', 'tracking_number', 'creation_date')
    list_filter = ('order_status', 'shipping_carrier')
    search_fields = ('order_id', 'buyer_username', 'buyer_name', 'tracking_number')
    readonly_fields = ('created_at', 'last_synced')
    inlines = [EbayOrderItemInline]
