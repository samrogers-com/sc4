"""eBay Fulfillment API service — requires User OAuth."""
from .api_client import get_user_token, make_api_request

ORDERS_URL = 'https://api.ebay.com/sell/fulfillment/v1/order'


def fetch_orders(days=30):
    """Fetch recent orders from eBay."""
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured. Run tools/ebay_oauth_setup.py first.")

    from datetime import datetime, timedelta
    date_from = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%dT00:00:00.000Z')

    orders = []
    offset = 0
    limit = 50

    while True:
        try:
            data = make_api_request('GET', ORDERS_URL, token=token, params={
                'filter': f'creationdate:[{date_from}..]',
                'limit': str(limit),
                'offset': str(offset),
            })
        except Exception as e:
            print(f"Fulfillment API error: {e}")
            break

        page_orders = data.get('orders', [])
        orders.extend(page_orders)

        total = data.get('total', 0)
        offset += limit
        if offset >= total:
            break

    return orders


def sync_orders_to_db(days=30):
    """Fetch orders and save to Django DB."""
    from ebay_manager.models import EbayOrder, EbayOrderItem, EbayListing

    raw_orders = fetch_orders(days=days)
    created = 0
    updated = 0

    for raw in raw_orders:
        order_id = raw.get('orderId', '')
        if not order_id:
            continue

        pricing = raw.get('pricingSummary', {})
        total = float(pricing.get('total', {}).get('value', 0))

        order, was_created = EbayOrder.objects.update_or_create(
            order_id=order_id,
            defaults={
                'buyer_username': raw.get('buyer', {}).get('username', ''),
                'order_total': total,
                'order_status': _map_order_status(raw.get('orderFulfillmentStatus', '')),
                'payment_status': raw.get('orderPaymentStatus', ''),
                'creation_date': raw.get('creationDate', ''),
            }
        )

        if was_created:
            created += 1
        else:
            updated += 1

        # Line items
        for line in raw.get('lineItems', []):
            item_id = line.get('legacyItemId', '')
            EbayOrderItem.objects.update_or_create(
                order=order,
                ebay_item_id=item_id,
                defaults={
                    'title': line.get('title', ''),
                    'sku': line.get('sku', ''),
                    'quantity': line.get('quantity', 1),
                    'price': float(line.get('lineItemCost', {}).get('value', 0)),
                    'listing': EbayListing.objects.filter(ebay_item_id=item_id).first(),
                }
            )

    return {'created': created, 'updated': updated, 'total': len(raw_orders)}


def _map_order_status(ebay_status):
    """Map eBay fulfillment status to our status choices."""
    mapping = {
        'NOT_STARTED': 'paid',
        'IN_PROGRESS': 'shipped',
        'FULFILLED': 'delivered',
    }
    return mapping.get(ebay_status, 'pending')
