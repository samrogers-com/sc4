"""Browse API service — works with Client Credentials (no User OAuth needed)."""
from .api_client import get_app_token, make_api_request

SEARCH_URL = 'https://api.ebay.com/buy/browse/v1/item_summary/search'


def search_listings(keywords, category_id=None, limit=50):
    """Search active eBay listings."""
    token = get_app_token()
    if not token:
        return []

    filters = ['buyingOptions:{FIXED_PRICE}', 'conditions:{NEW|LIKE_NEW|VERY_GOOD}']
    if category_id:
        filters.append(f'categoryIds:{{{category_id}}}')

    params = {
        'q': keywords,
        'filter': ','.join(filters),
        'sort': 'newlyListed',
        'limit': str(min(limit, 200)),
    }

    try:
        data = make_api_request('GET', SEARCH_URL, token=token, params=params)
        items = []
        for item in data.get('itemSummaries', []):
            price_info = item.get('price', {})
            items.append({
                'title': item.get('title', ''),
                'price': float(price_info.get('value', 0)),
                'item_id': item.get('itemId', ''),
                'url': item.get('itemWebUrl', ''),
                'condition': item.get('condition', ''),
            })
        return items
    except Exception as e:
        print(f"Browse API error: {e}")
        return []


def get_market_price(keywords, strategy='highest'):
    """Get market price for an item."""
    items = search_listings(keywords)
    if not items:
        return None

    prices = sorted([i['price'] for i in items if i['price'] > 0])
    if not prices:
        return None

    if strategy == 'highest':
        return max(prices)
    elif strategy == 'average':
        return round(sum(prices) / len(prices), 2)
    elif strategy == 'median':
        mid = len(prices) // 2
        return prices[mid] if len(prices) % 2 else (prices[mid-1] + prices[mid]) / 2
    return max(prices)
