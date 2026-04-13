"""Analytics service — uses local DB data."""
from django.db.models import Sum, Count, Avg
from ebay_manager.models import EbayListing, EbayOrder, EbayOrderItem


def get_revenue_summary(days=30):
    """Revenue summary for the last N days."""
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=days)

    orders = EbayOrder.objects.filter(creation_date__gte=cutoff)
    return {
        'total_orders': orders.count(),
        'total_revenue': orders.aggregate(t=Sum('order_total'))['t'] or 0,
        'total_profit': orders.aggregate(t=Sum('net_profit'))['t'] or 0,
        'total_fees': orders.aggregate(t=Sum('ebay_fees'))['t'] or 0,
        'avg_order_value': orders.aggregate(a=Avg('order_total'))['a'] or 0,
    }


def get_top_sellers(limit=20):
    """Top selling items by revenue."""
    return (
        EbayOrderItem.objects
        .values('title')
        .annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum('price'),
        )
        .order_by('-total_revenue')[:limit]
    )


def get_listing_stats():
    """Listing status breakdown."""
    return (
        EbayListing.objects
        .values('status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
