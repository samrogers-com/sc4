from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.contrib import messages

from .models import EbayListing, EbayOrder, EbayOrderItem


def is_staff(user):
    return user.is_staff


@login_required
@user_passes_test(is_staff)
def dashboard(request):
    """Main eBay Manager dashboard."""
    total_listings = EbayListing.objects.count()
    active_listings = EbayListing.objects.filter(status='active').count()
    draft_listings = EbayListing.objects.filter(status='draft').count()
    sold_listings = EbayListing.objects.filter(status='sold').count()

    total_orders = EbayOrder.objects.count()
    revenue = EbayOrder.objects.aggregate(total=Sum('order_total'))['total'] or 0
    total_profit = EbayOrder.objects.aggregate(total=Sum('net_profit'))['total'] or 0

    recent_orders = EbayOrder.objects.order_by('-creation_date')[:10]
    recent_listings = EbayListing.objects.order_by('-created_at')[:10]

    # API status
    api_status = _get_api_status()

    return render(request, 'ebay_manager/dashboard.html', {
        'total_listings': total_listings,
        'active_listings': active_listings,
        'draft_listings': draft_listings,
        'sold_listings': sold_listings,
        'total_orders': total_orders,
        'revenue': revenue,
        'total_profit': total_profit,
        'recent_orders': recent_orders,
        'recent_listings': recent_listings,
        'api_status': api_status,
    })


@login_required
@user_passes_test(is_staff)
def listings(request):
    """All eBay listings with filters."""
    status_filter = request.GET.get('status', '')
    qs = EbayListing.objects.all()
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, 'ebay_manager/listings.html', {
        'listings': qs,
        'status_filter': status_filter,
        'status_choices': EbayListing.STATUS_CHOICES,
    })


@login_required
@user_passes_test(is_staff)
def listing_create(request):
    """Create a new eBay listing from inventory."""
    # For now, show a form to manually create
    if request.method == 'POST':
        listing = EbayListing(
            title=request.POST.get('title', ''),
            price=request.POST.get('price', 0),
            sku=request.POST.get('sku', ''),
            category_id=request.POST.get('category_id', ''),
            condition_id=request.POST.get('condition_id', '7000'),
            status='draft',
            created_by=request.user,
            content_type_id=request.POST.get('content_type_id'),
            object_id=request.POST.get('object_id'),
        )
        listing.save()
        messages.success(request, f'Draft listing created: {listing.title}')
        return redirect('ebay_manager:listing_detail', pk=listing.pk)

    return render(request, 'ebay_manager/listing_create.html')


@login_required
@user_passes_test(is_staff)
def listing_detail(request, pk):
    """Single listing detail."""
    listing = get_object_or_404(EbayListing, pk=pk)
    order_items = listing.order_items.select_related('order').all()

    return render(request, 'ebay_manager/listing_detail.html', {
        'listing': listing,
        'order_items': order_items,
    })


@login_required
@user_passes_test(is_staff)
def orders(request):
    """Order history."""
    status_filter = request.GET.get('status', '')
    qs = EbayOrder.objects.prefetch_related('items').all()
    if status_filter:
        qs = qs.filter(order_status=status_filter)

    return render(request, 'ebay_manager/orders.html', {
        'orders': qs,
        'status_filter': status_filter,
        'status_choices': EbayOrder.ORDER_STATUSES,
    })


@login_required
@user_passes_test(is_staff)
def order_detail(request, pk):
    """Single order detail."""
    order = get_object_or_404(EbayOrder.objects.prefetch_related('items'), pk=pk)

    return render(request, 'ebay_manager/order_detail.html', {
        'order': order,
    })


@login_required
@user_passes_test(is_staff)
def analytics(request):
    """Performance analytics."""
    total_revenue = EbayOrder.objects.aggregate(total=Sum('order_total'))['total'] or 0
    total_profit = EbayOrder.objects.aggregate(total=Sum('net_profit'))['total'] or 0
    total_fees = EbayOrder.objects.aggregate(total=Sum('ebay_fees'))['total'] or 0
    total_orders = EbayOrder.objects.count()

    top_items = (
        EbayOrderItem.objects
        .values('title')
        .annotate(total_sold=Sum('quantity'), total_revenue=Sum('price'))
        .order_by('-total_revenue')[:20]
    )

    status_breakdown = (
        EbayOrder.objects
        .values('order_status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return render(request, 'ebay_manager/analytics.html', {
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'total_fees': total_fees,
        'total_orders': total_orders,
        'top_items': top_items,
        'status_breakdown': status_breakdown,
    })


@login_required
@user_passes_test(is_staff)
def settings_view(request):
    """API connection status and setup."""
    api_status = _get_api_status()

    return render(request, 'ebay_manager/settings.html', {
        'api_status': api_status,
    })


@login_required
@user_passes_test(is_staff)
def sync_listings(request):
    """Import active listings from eBay."""
    if request.method == 'POST':
        # TODO: Implement after User OAuth setup
        messages.info(request, 'Listing sync requires User OAuth setup. See Settings page.')
        return redirect('ebay_manager:settings')
    return redirect('ebay_manager:dashboard')


@login_required
@user_passes_test(is_staff)
def sync_orders(request):
    """Import sold history from eBay."""
    if request.method == 'POST':
        # TODO: Implement after User OAuth setup
        messages.info(request, 'Order sync requires User OAuth setup. See Settings page.')
        return redirect('ebay_manager:settings')
    return redirect('ebay_manager:dashboard')


def _get_api_status():
    """Check eBay API connection status."""
    import os
    from pathlib import Path

    app_id = os.environ.get('EBAY_APP_ID', '')
    cert_id = os.environ.get('EBAY_CERT_ID', '')
    token_file = Path(__file__).parent.parent.parent / 'tools' / 'ebay_user_token.json'

    return {
        'browse_api': bool(app_id and cert_id),
        'app_id_set': bool(app_id),
        'cert_id_set': bool(cert_id),
        'user_oauth': token_file.exists(),
        'token_file': str(token_file),
    }
