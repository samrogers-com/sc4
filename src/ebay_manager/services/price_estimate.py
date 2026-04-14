"""
eBay price estimation service.

Queries active eBay listings for similar items and calculates a
recommended selling price based on the top quartile mean minus $1.05.

Formula:
    1. Search eBay for similar items (same category, sealed condition)
    2. Collect prices from active Buy It Now listings
    3. Calculate high mean = average of top 25% of prices
    4. Suggested price = high_mean - $1.05 (rounds to .95 ending)

Example:
    Listings found: $87, $75, $50, $45, $45, $30, $25, $20
    Top quartile (top 2): $87, $75 → mean = $81.00
    Suggested: $81.00 - $1.05 = $79.95

Usage:
    from ebay_manager.services.price_estimate import estimate_price
    result = estimate_price("1998 JPP/Amada Godzilla trading cards sealed box")
    print(result['suggested_price'])  # 79.95
"""
import requests
from decimal import Decimal, ROUND_DOWN
from .api_client import get_app_token


def estimate_price(search_query, category_id='261035'):
    """Estimate selling price from active eBay listings.

    Args:
        search_query: Keywords to search (product title or key terms)
        category_id: eBay category to filter (default: Non-Sport Sealed Boxes)

    Returns:
        dict with:
            'suggested_price': Decimal — recommended price (high mean - $1.05)
            'high_mean': Decimal — average of top quartile prices
            'avg_price': Decimal — average of all prices found
            'low_price': Decimal — lowest price found
            'high_price': Decimal — highest price found
            'num_listings': int — number of comparable listings found
            'listings': list — top 5 comparable listings with title/price/seller
    """
    token = get_app_token()
    if not token:
        return _empty_result()

    headers = {
        'Authorization': f'Bearer {token}',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
    }

    # Search for similar items — Buy It Now, New condition
    params = {
        'q': search_query,
        'filter': 'buyingOptions:{FIXED_PRICE},conditionIds:{1000}',
        'sort': 'price',
        'limit': '30',
    }
    if category_id:
        params['category_ids'] = category_id

    try:
        resp = requests.get(
            'https://api.ebay.com/buy/browse/v1/item_summary/search',
            headers=headers, params=params, timeout=15
        )
        if resp.status_code != 200:
            return _empty_result()

        items = resp.json().get('itemSummaries', [])
    except Exception:
        return _empty_result()

    if not items:
        return _empty_result()

    # Extract prices and listing info
    prices = []
    listings = []
    for item in items:
        price = float(item.get('price', {}).get('value', 0))
        if price > 0:
            prices.append(price)
            listings.append({
                'title': item.get('title', '')[:60],
                'price': price,
                'seller': item.get('seller', {}).get('username', ''),
            })

    if not prices:
        return _empty_result()

    # Sort descending for top quartile
    sorted_prices = sorted(prices, reverse=True)
    quartile_size = max(1, len(sorted_prices) // 4)
    top_quartile = sorted_prices[:quartile_size]
    high_mean = sum(top_quartile) / len(top_quartile)

    # Suggested price: high mean - $1.05 (gives .95 ending)
    suggested = Decimal(str(high_mean)) - Decimal('1.05')
    # Round down to nearest .95
    dollars = int(suggested)
    suggested_price = Decimal(f'{dollars}.95')
    # If the subtraction already gives .95, use it directly
    if suggested >= Decimal(f'{dollars}.95'):
        suggested_price = Decimal(f'{dollars}.95')
    else:
        suggested_price = Decimal(f'{dollars - 1}.95')

    avg_price = sum(prices) / len(prices)

    return {
        'suggested_price': suggested_price,
        'high_mean': Decimal(str(round(high_mean, 2))),
        'avg_price': Decimal(str(round(avg_price, 2))),
        'low_price': Decimal(str(min(prices))),
        'high_price': Decimal(str(max(prices))),
        'num_listings': len(prices),
        'listings': sorted(listings, key=lambda x: -x['price'])[:5],
    }


def _empty_result():
    """Return empty price estimate result."""
    return {
        'suggested_price': None,
        'high_mean': None,
        'avg_price': None,
        'low_price': None,
        'high_price': None,
        'num_listings': 0,
        'listings': [],
    }
