"""
Sam's Collectibles - Sold Price Lookup (Phase 2)
Queries eBay's Browse API for listings to determine competitive Buy It Now pricing.

Uses OAuth2 Client Credentials flow with the Browse API's item_summary/search
endpoint. The deprecated Finding API (findCompletedItems) has been replaced.

Setup:
    1. Create a free eBay Developer account at https://developer.ebay.com
    2. Get your App ID (Client ID) and Cert ID (Client Secret)
    3. Set them as environment variables:
         export EBAY_APP_ID="your-client-id"
         export EBAY_CERT_ID="your-client-secret"

Usage:
    python sold_price_lookup.py "1993 SkyBox Star Trek Deep Space Nine sealed box"
    python sold_price_lookup.py --all
    python sold_price_lookup.py --all --strategy highest
    python sold_price_lookup.py --clear-cache
"""

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import (
    EBAY_APP_ID,
    EBAY_CERT_ID,
    EBAY_API_ENVIRONMENT,
    DATA_DIR,
    MAX_SOLD_RESULTS,
    PRICE_CACHE_DAYS,
)


# =============================================================================
# OAUTH2 TOKEN MANAGEMENT
# =============================================================================

_token_cache = {
    "access_token": None,
    "expires_at": 0,
}

OAUTH_ENDPOINTS = {
    "production": "https://api.ebay.com/identity/v1/oauth2/token",
    "sandbox": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
}

BROWSE_ENDPOINTS = {
    "production": "https://api.ebay.com/buy/browse/v1/item_summary/search",
    "sandbox": "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search",
}


def get_oauth_token() -> str:
    """
    Get an OAuth2 application access token using Client Credentials grant.
    Caches the token and refreshes when expired.
    """
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    if not EBAY_APP_ID or not EBAY_CERT_ID:
        raise ValueError(
            "EBAY_APP_ID and EBAY_CERT_ID must be set. "
            "Get credentials at https://developer.ebay.com"
        )

    credentials = base64.b64encode(
        f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()
    ).decode()

    env = EBAY_API_ENVIRONMENT or "production"
    token_url = OAUTH_ENDPOINTS.get(env, OAUTH_ENDPOINTS["production"])

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {credentials}",
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }

    resp = requests.post(token_url, headers=headers, data=data, timeout=15)
    resp.raise_for_status()
    token_data = resp.json()

    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"] = now + token_data.get("expires_in", 7200)

    return _token_cache["access_token"]


# =============================================================================
# PRICE CACHE
# =============================================================================

PRICE_CACHE_FILE = DATA_DIR / "price_cache.json"


def load_price_cache() -> dict:
    """Load cached prices from disk."""
    if PRICE_CACHE_FILE.exists():
        with open(PRICE_CACHE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_price_cache(cache: dict):
    """Save price cache to disk."""
    PRICE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PRICE_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def is_cache_fresh(cache_entry: dict) -> bool:
    """Check if a cache entry is still within PRICE_CACHE_DAYS."""
    cached_date = datetime.fromisoformat(cache_entry.get("queried_at", "2000-01-01"))
    return (datetime.now() - cached_date).days < PRICE_CACHE_DAYS


# =============================================================================
# EBAY BROWSE API
# =============================================================================

def search_sold_items(keywords: str, category_id: str = None) -> list[dict]:
    """
    Query eBay Browse API for listings matching keywords.

    The Browse API with Client Credentials grant returns active listings
    (not completed/sold items). These active listing prices serve as
    market reference for competitive pricing.

    Returns a list of items with prices.
    """
    if not EBAY_APP_ID or not EBAY_CERT_ID:
        print("ERROR: EBAY_APP_ID and EBAY_CERT_ID not configured.")
        print("       1. Get credentials at https://developer.ebay.com")
        print("       2. Set them:")
        print("            export EBAY_APP_ID='your-client-id'")
        print("            export EBAY_CERT_ID='your-client-secret'")
        return []

    try:
        token = get_oauth_token()
    except Exception as e:
        print(f"  OAuth Error: {e}")
        return []

    env = EBAY_API_ENVIRONMENT or "production"
    search_url = BROWSE_ENDPOINTS.get(env, BROWSE_ENDPOINTS["production"])

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }

    # Build filter string for the Browse API
    filters = ["buyingOptions:{FIXED_PRICE}"]
    filters.append("conditions:{NEW|LIKE_NEW|VERY_GOOD}")

    if category_id:
        filters.append(f"categoryIds:{{{category_id}}}")

    params = {
        "q": keywords,
        "filter": ",".join(filters),
        "sort": "newlyListed",
        "limit": str(min(MAX_SOLD_RESULTS, 200)),
    }

    try:
        resp = requests.get(search_url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"  API HTTP Error: {e}")
        if resp.status_code == 403:
            print("  (Browse API access may require additional marketplace approval)")
        return []
    except Exception as e:
        print(f"  API Error: {e}")
        return []

    items = []
    for item_summary in data.get("itemSummaries", []):
        price_info = item_summary.get("price", {})
        price_val = float(price_info.get("value", 0))
        currency = price_info.get("currency", "USD")

        # Only include USD items with a positive price
        if currency != "USD" or price_val <= 0:
            continue

        condition = item_summary.get("condition", "")
        item_url = item_summary.get("itemWebUrl", "")
        item_id = item_summary.get("itemId", "")
        title = item_summary.get("title", "")

        # Use itemEndDate if available (for completed items), otherwise itemCreationDate
        sold_date = (
            item_summary.get("itemEndDate")
            or item_summary.get("itemCreationDate", "")
        )

        items.append({
            "title": title,
            "price": price_val,
            "currency": currency,
            "item_id": item_id,
            "sold_date": sold_date,
            "url": item_url,
            "condition": condition,
        })

    return items


# =============================================================================
# PRICING STRATEGIES
# =============================================================================

def calculate_price(sold_items: list[dict], strategy: str = "highest") -> dict:
    """
    Calculate recommended price from sold items.

    Strategies:
        highest  - Use the highest sold price (Sam's default)
        average  - Use the average sold price
        median   - Use the median sold price
        p75      - Use the 75th percentile
    """
    if not sold_items:
        return {
            "recommended_price": None,
            "strategy": strategy,
            "num_sold": 0,
            "prices": [],
        }

    prices = sorted([item["price"] for item in sold_items if item["price"] > 0])

    if not prices:
        return {
            "recommended_price": None,
            "strategy": strategy,
            "num_sold": 0,
            "prices": [],
        }

    if strategy == "highest":
        recommended = max(prices)
    elif strategy == "average":
        recommended = sum(prices) / len(prices)
    elif strategy == "median":
        mid = len(prices) // 2
        if len(prices) % 2 == 0:
            recommended = (prices[mid - 1] + prices[mid]) / 2
        else:
            recommended = prices[mid]
    elif strategy == "p75":
        idx = int(len(prices) * 0.75)
        recommended = prices[min(idx, len(prices) - 1)]
    else:
        recommended = max(prices)

    return {
        "recommended_price": round(recommended, 2),
        "strategy": strategy,
        "num_sold": len(prices),
        "highest": max(prices),
        "lowest": min(prices),
        "average": round(sum(prices) / len(prices), 2),
        "prices": prices,
    }


# =============================================================================
# LOOKUP WITH CACHING
# =============================================================================

def lookup_price(
    keywords: str,
    category_id: str = None,
    strategy: str = "highest",
    force_refresh: bool = False,
) -> dict:
    """
    Look up sold price for a product, using cache when available.
    Returns pricing data dict.
    """
    cache = load_price_cache()
    cache_key = keywords.strip().lower()

    # Check cache first
    if not force_refresh and cache_key in cache and is_cache_fresh(cache[cache_key]):
        cached = cache[cache_key]
        print(f"  [CACHE] {keywords}")
        print(f"          ${cached['recommended_price']} ({cached['strategy']}, "
              f"{cached['num_sold']} sold)")
        return cached

    # Query eBay API
    print(f"  [API] Searching: {keywords}")
    sold_items = search_sold_items(keywords, category_id)

    if not sold_items:
        print(f"        No sold items found.")
        result = {
            "keywords": keywords,
            "recommended_price": None,
            "strategy": strategy,
            "num_sold": 0,
            "queried_at": datetime.now().isoformat(),
        }
    else:
        pricing = calculate_price(sold_items, strategy)
        result = {
            "keywords": keywords,
            **pricing,
            "queried_at": datetime.now().isoformat(),
            "sample_listings": [
                {"title": i["title"], "price": i["price"], "url": i["url"]}
                for i in sold_items[:5]
            ],
        }
        print(f"        Found {pricing['num_sold']} sold items")
        print(f"        Highest: ${pricing.get('highest', 'N/A')}")
        print(f"        Lowest:  ${pricing.get('lowest', 'N/A')}")
        print(f"        Average: ${pricing.get('average', 'N/A')}")
        print(f"        >>> Recommended ({strategy}): ${pricing['recommended_price']}")

    # Update cache
    cache[cache_key] = result
    save_price_cache(cache)

    return result


def lookup_all_ready_items(strategy: str = "highest", force_refresh: bool = False):
    """
    Price all items in the inventory_status.json 'ready_to_list' section.
    """
    inventory_file = DATA_DIR / "inventory_status.json"
    if not inventory_file.exists():
        print("ERROR: No inventory_status.json found.")
        print("       Run inventory_tracker.py first.")
        return

    with open(inventory_file, "r") as f:
        inventory = json.load(f)

    ready_items = inventory.get("ready_to_list", [])
    if not ready_items:
        print("No items marked as ready to list.")
        return

    print(f"\nPricing {len(ready_items)} items...\n")

    for item in ready_items:
        # Build search keywords from the item name
        name = item.get("name", "")
        keywords = name.replace("/", " ").replace("-", " ").replace("_", " ")
        # Add "sealed box" or product type for better results
        product_type = item.get("product_type", "")
        if product_type == "boxes":
            keywords += " sealed box"
        elif product_type == "packs":
            keywords += " sealed pack"
        elif product_type == "sets":
            keywords += " complete set"

        lookup_price(keywords, strategy=strategy, force_refresh=force_refresh)
        print()


# =============================================================================
# MANUAL PRICE ENTRY
# =============================================================================

def set_manual_price(keywords: str, price: float, notes: str = ""):
    """
    Manually set a price for an item (bypasses API).
    Useful when you know what you want to charge.
    """
    cache = load_price_cache()
    cache_key = keywords.strip().lower()

    cache[cache_key] = {
        "keywords": keywords,
        "recommended_price": price,
        "strategy": "manual",
        "num_sold": 0,
        "queried_at": datetime.now().isoformat(),
        "notes": notes,
    }

    save_price_cache(cache)
    print(f"  Set manual price: {keywords} -> ${price}")
    if notes:
        print(f"  Notes: {notes}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Sam's Collectibles - eBay Sold Price Lookup"
    )
    parser.add_argument(
        "keywords",
        nargs="?",
        help="Product keywords to search (e.g., '1993 SkyBox Star Trek DS9 sealed box')",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Price all items in inventory_status.json",
    )
    parser.add_argument(
        "--strategy",
        choices=["highest", "average", "median", "p75"],
        default="highest",
        help="Pricing strategy (default: highest)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force refresh (ignore cache)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the entire price cache",
    )
    parser.add_argument(
        "--set-price",
        type=float,
        help="Manually set a price for the given keywords",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Notes for manual price entry",
    )
    args = parser.parse_args()

    if args.clear_cache:
        if PRICE_CACHE_FILE.exists():
            PRICE_CACHE_FILE.unlink()
            print("Price cache cleared.")
        else:
            print("No cache to clear.")
        return

    if args.set_price and args.keywords:
        set_manual_price(args.keywords, args.set_price, args.notes)
        return

    if args.all:
        lookup_all_ready_items(strategy=args.strategy, force_refresh=args.refresh)
        return

    if args.keywords:
        lookup_price(args.keywords, strategy=args.strategy, force_refresh=args.refresh)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
