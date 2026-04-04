"""
Sam's Collectibles - Sold Price Lookup (Phase 2)
Queries eBay's Finding API for completed/sold listings to determine
competitive Buy It Now pricing.

Setup:
    1. Create a free eBay Developer account at https://developer.ebay.com
    2. Get your App ID (Client ID) from the developer dashboard
    3. Set it as an environment variable:
         export EBAY_APP_ID="your-app-id-here"
       Or update EBAY_APP_ID in config.py

Usage:
    python sold_price_lookup.py "1993 SkyBox Star Trek Deep Space Nine sealed box"
    python sold_price_lookup.py --all
    python sold_price_lookup.py --all --strategy highest
    python sold_price_lookup.py --clear-cache
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from ebaysdk.finding import Connection as FindingAPI
    HAS_EBAYSDK = True
except ImportError:
    HAS_EBAYSDK = False

from config import (
    EBAY_APP_ID,
    EBAY_API_ENVIRONMENT,
    DATA_DIR,
    MAX_SOLD_RESULTS,
    PRICE_CACHE_DAYS,
)


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
# EBAY FINDING API
# =============================================================================

def search_sold_items(keywords: str, category_id: str = None) -> list[dict]:
    """
    Query eBay Finding API findCompletedItems for sold listings.
    Returns a list of sold items with prices.
    """
    if not HAS_EBAYSDK:
        print("ERROR: ebaysdk not installed. Run: pip install ebaysdk")
        print("       Then set EBAY_APP_ID in config.py or as env variable.")
        return []

    if not EBAY_APP_ID:
        print("ERROR: EBAY_APP_ID not configured.")
        print("       1. Get a free key at https://developer.ebay.com")
        print("       2. Set it: export EBAY_APP_ID='your-key-here'")
        print("       Or update EBAY_APP_ID in config.py")
        return []

    try:
        api = FindingAPI(
            appid=EBAY_APP_ID,
            config_file=None,
            siteid="EBAY-US",
        )

        request_params = {
            "keywords": keywords,
            "itemFilter": [
                {"name": "SoldItemsOnly", "value": "true"},
                {"name": "ListingType", "value": "FixedPrice"},
            ],
            "sortOrder": "PricePlusShippingHighest",
            "paginationInput": {
                "entriesPerPage": str(MAX_SOLD_RESULTS),
                "pageNumber": "1",
            },
        }

        if category_id:
            request_params["categoryId"] = category_id

        response = api.execute("findCompletedItems", request_params)
        results = response.dict()

        items = []
        search_result = results.get("searchResult", {})
        result_items = search_result.get("item", [])

        if not isinstance(result_items, list):
            result_items = [result_items] if result_items else []

        for item in result_items:
            selling_status = item.get("sellingStatus", {})
            current_price = selling_status.get("currentPrice", {})

            price = float(current_price.get("value", 0))
            sold_date = item.get("listingInfo", {}).get("endTime", "")

            items.append({
                "title": item.get("title", ""),
                "price": price,
                "currency": current_price.get("_currencyId", "USD"),
                "item_id": item.get("itemId", ""),
                "sold_date": sold_date,
                "url": item.get("viewItemURL", ""),
                "condition": item.get("condition", {}).get("conditionDisplayName", ""),
            })

        return items

    except Exception as e:
        print(f"  API Error: {e}")
        return []


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
