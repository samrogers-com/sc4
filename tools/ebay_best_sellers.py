#!/usr/bin/env python3
"""
Sam's Collectibles -- eBay Best-Seller Recommender

Reads inventory from the annotated CSV (non-sports cards) or inventory
status JSON, then queries the Browse API for each item to estimate
market demand and competition. Ranks items by a "sell score" to
recommend what to list next.

Sell score factors:
    - Number of active listings (fewer = less competition = higher score)
    - Average listing price (higher = more profitable)
    - Price-to-competition ratio
    - Product type multiplier (sealed boxes score higher than singles)

Data sources:
    - Non-sports cards: src/non_sports_cards/static/nstc-core-10-29-22-annotated.csv
    - Inventory status: ebay_automation/data/inventory_status.json
    - eBay Browse API: active listing counts and prices

Uses the same Browse API (Client Credentials) as sold_price_lookup.py,
so no User OAuth token is needed.

Usage:
    # Analyze all inventory items and rank by sell score
    python tools/ebay_best_sellers.py

    # Top N items (default 20)
    python tools/ebay_best_sellers.py --top 10

    # Only analyze sealed boxes
    python tools/ebay_best_sellers.py --type boxes

    # Only analyze items ready to list
    python tools/ebay_best_sellers.py --ready-only

    # Force refresh (skip cache)
    python tools/ebay_best_sellers.py --refresh

    # Save report to file
    python tools/ebay_best_sellers.py --output report.txt

    -h, --help    Show full help
"""

import argparse
import base64
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
TOOLS_DIR = Path(__file__).parent
DATA_DIR = TOOLS_DIR / "data"

# Inventory sources
ANNOTATED_CSV = PROJECT_ROOT / "src" / "non_sports_cards" / "static" / "nstc-core-10-29-22-annotated.csv"
INVENTORY_STATUS = PROJECT_ROOT / "ebay_automation" / "data" / "inventory_status.json"

# Cache for Browse API results
MARKET_CACHE_FILE = DATA_DIR / "market_cache.json"
MARKET_CACHE_DAYS = 3  # Re-query after this many days

# eBay API credentials
EBAY_APP_ID = os.environ.get("EBAY_APP_ID", "")
EBAY_CERT_ID = os.environ.get("EBAY_CERT_ID", "")

# ---------------------------------------------------------------------------
# OAuth2 (Client Credentials -- same as sold_price_lookup.py)
# ---------------------------------------------------------------------------

_token_cache = {"access_token": None, "expires_at": 0}

OAUTH_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


def get_browse_token():
    """Get an OAuth2 app access token for the Browse API."""
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    if not EBAY_APP_ID or not EBAY_CERT_ID:
        return None

    credentials = base64.b64encode(
        f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()
    ).decode()

    resp = requests.post(
        OAUTH_TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 7200)
    return _token_cache["access_token"]


# ---------------------------------------------------------------------------
# Market Data (Browse API)
# ---------------------------------------------------------------------------

def load_market_cache():
    if MARKET_CACHE_FILE.exists():
        with open(MARKET_CACHE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_market_cache(cache):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MARKET_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def is_cache_fresh(entry):
    cached_date = datetime.fromisoformat(entry.get("queried_at", "2000-01-01"))
    return (datetime.now() - cached_date).days < MARKET_CACHE_DAYS


def query_market_data(keywords, token):
    """
    Query Browse API for active listings matching keywords.

    Returns:
        dict with active_count, avg_price, min_price, max_price, prices
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }
    params = {
        "q": keywords,
        "filter": "buyingOptions:{FIXED_PRICE},conditions:{NEW|LIKE_NEW|VERY_GOOD}",
        "sort": "price",
        "limit": "50",
    }

    try:
        resp = requests.get(
            BROWSE_SEARCH_URL, headers=headers, params=params, timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "active_count": 0, "avg_price": 0}

    items = data.get("itemSummaries", [])
    total = data.get("total", 0)

    prices = []
    for item in items:
        price_info = item.get("price", {})
        val = float(price_info.get("value", 0))
        currency = price_info.get("currency", "USD")
        if currency == "USD" and val > 0:
            prices.append(val)

    if not prices:
        return {
            "active_count": total,
            "avg_price": 0,
            "min_price": 0,
            "max_price": 0,
            "prices": [],
            "queried_at": datetime.now().isoformat(),
        }

    return {
        "active_count": total,
        "avg_price": round(sum(prices) / len(prices), 2),
        "min_price": min(prices),
        "max_price": max(prices),
        "prices": prices,
        "queried_at": datetime.now().isoformat(),
    }


def get_market_data(keywords, token, cache, force_refresh=False):
    """Get market data with caching."""
    cache_key = keywords.strip().lower()

    if not force_refresh and cache_key in cache and is_cache_fresh(cache[cache_key]):
        return cache[cache_key]

    data = query_market_data(keywords, token)
    cache[cache_key] = data
    return data


# ---------------------------------------------------------------------------
# Inventory Loading
# ---------------------------------------------------------------------------

def load_inventory_from_csv():
    """Load inventory items from the annotated CSV."""
    items = []
    if not ANNOTATED_CSV.exists():
        return items

    with open(ANNOTATED_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("title", "").strip()
            maker = row.get("maker", "").strip()
            year = row.get("year_made", "").strip()
            item_type = row.get("type", "base").strip()
            quantity = int(row.get("quantity", "0") or "0")

            if not title or quantity <= 0:
                continue

            # Build search keywords
            parts = []
            if year:
                parts.append(year)
            if maker:
                parts.append(maker)
            parts.append(title)

            # Add product type qualifier
            if item_type == "box":
                parts.append("sealed box")
                product_type = "boxes"
            elif item_type == "base":
                parts.append("complete set trading cards")
                product_type = "sets"
            elif item_type in ("chase", "insert", "sticker"):
                parts.append(f"{item_type} set trading cards")
                product_type = "sets"
            else:
                parts.append("trading cards")
                product_type = "singles"

            items.append({
                "name": title,
                "keywords": " ".join(parts),
                "product_type": product_type,
                "maker": maker,
                "year": year,
                "quantity": quantity,
                "source": "csv",
            })

    return items


def load_inventory_from_status():
    """Load ready-to-list items from inventory_status.json."""
    items = []
    if not INVENTORY_STATUS.exists():
        return items

    with open(INVENTORY_STATUS, "r") as f:
        data = json.load(f)

    for item in data.get("ready_to_list", []):
        name = item.get("name", "")
        product_type = item.get("product_type", "boxes")
        keywords = name.replace("/", " ").replace("-", " ").replace("_", " ")

        if product_type == "boxes":
            keywords += " sealed box"
        elif product_type == "packs":
            keywords += " sealed pack"
        elif product_type == "sets":
            keywords += " complete set"

        items.append({
            "name": name,
            "keywords": keywords,
            "product_type": product_type,
            "maker": "",
            "year": "",
            "quantity": 1,
            "source": "inventory_status",
        })

    return items


# ---------------------------------------------------------------------------
# Sell Score Calculation
# ---------------------------------------------------------------------------

# Product type multipliers (sealed products sell better)
TYPE_MULTIPLIER = {
    "boxes": 1.5,
    "packs": 1.2,
    "sets": 1.0,
    "singles": 0.7,
    "binders": 0.9,
    "posters": 1.3,
    "comic_books": 1.1,
}


def calculate_sell_score(market_data, product_type):
    """
    Calculate a sell score (0-100) for an item.

    Higher score = should list sooner.

    Factors:
        - Competition (fewer active listings = better)
        - Price (higher avg price = more profitable)
        - Product type (sealed boxes > singles)
        - Price spread (big spread = pricing power)
    """
    active = market_data.get("active_count", 0)
    avg_price = market_data.get("avg_price", 0)
    max_price = market_data.get("max_price", 0)
    min_price = market_data.get("min_price", 0)

    if avg_price == 0:
        # No market data -- unknown, give a neutral score
        return 50.0

    # Competition score (0-30 pts): fewer listings = higher score
    if active == 0:
        comp_score = 30  # No competition
    elif active <= 5:
        comp_score = 25
    elif active <= 15:
        comp_score = 20
    elif active <= 30:
        comp_score = 15
    elif active <= 50:
        comp_score = 10
    else:
        comp_score = 5

    # Price score (0-30 pts): higher average = more profit
    if avg_price >= 100:
        price_score = 30
    elif avg_price >= 50:
        price_score = 25
    elif avg_price >= 25:
        price_score = 20
    elif avg_price >= 15:
        price_score = 15
    elif avg_price >= 8:
        price_score = 10
    else:
        price_score = 5

    # Price spread score (0-20 pts): big spread means pricing power
    spread = max_price - min_price if max_price > min_price else 0
    spread_pct = spread / avg_price if avg_price > 0 else 0
    if spread_pct >= 1.0:
        spread_score = 20
    elif spread_pct >= 0.5:
        spread_score = 15
    elif spread_pct >= 0.25:
        spread_score = 10
    else:
        spread_score = 5

    # Product type multiplier (0.7x - 1.5x)
    multiplier = TYPE_MULTIPLIER.get(product_type, 1.0)

    raw_score = (comp_score + price_score + spread_score) * multiplier

    # Normalize to 0-100
    return min(100.0, round(raw_score, 1))


# ---------------------------------------------------------------------------
# Report Output
# ---------------------------------------------------------------------------

def format_report(scored_items, top_n=20):
    """Format the best-seller report as a string."""
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("Sam's Collectibles -- Best-Seller Recommendations")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)
    lines.append("")

    if not scored_items:
        lines.append("No items to analyze.")
        return "\n".join(lines)

    lines.append(f"Top {min(top_n, len(scored_items))} items to list on eBay:")
    lines.append("")
    lines.append(
        f"  {'Rank':>4s}  {'Score':>5s}  {'Avg$':>7s}  {'Active':>6s}  "
        f"{'Type':>8s}  {'Item'}"
    )
    lines.append(
        f"  {'----':>4s}  {'-----':>5s}  {'----':>7s}  {'------':>6s}  "
        f"{'----':>8s}  {'----'}"
    )

    for i, item in enumerate(scored_items[:top_n], 1):
        name = item["name"]
        if len(name) > 45:
            name = name[:42] + "..."
        lines.append(
            f"  {i:4d}  {item['score']:5.1f}  "
            f"${item['avg_price']:>6.2f}  "
            f"{item['active_count']:6d}  "
            f"{item['product_type']:>8s}  "
            f"{name}"
        )

    # Summary stats
    lines.append("")
    lines.append("-" * 70)
    avg_score = sum(i["score"] for i in scored_items) / len(scored_items)
    high_value = [i for i in scored_items if i["avg_price"] >= 50]
    low_comp = [i for i in scored_items if i["active_count"] <= 10]

    lines.append(f"  Total items analyzed:     {len(scored_items)}")
    lines.append(f"  Average sell score:       {avg_score:.1f}")
    lines.append(f"  High-value items (>$50):  {len(high_value)}")
    lines.append(f"  Low-competition (<=10):   {len(low_comp)}")
    lines.append("")

    # Score interpretation
    lines.append("  Score interpretation:")
    lines.append("    80+  = High priority -- list these first")
    lines.append("    60-79 = Good candidates -- solid demand")
    lines.append("    40-59 = Average -- list when time permits")
    lines.append("    <40  = Low priority -- competitive or low value")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sam's Collectibles -- eBay Best-Seller Recommender",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Reads your inventory and queries eBay to rank items by sell potential.
Uses the Browse API (Client Credentials) -- no User OAuth needed.

Sell score factors:
    - Competition (fewer active listings = higher score)
    - Average price (higher = more profitable)
    - Price spread (more spread = pricing power)
    - Product type (sealed boxes > singles)

Examples:
    %(prog)s                    Analyze all inventory
    %(prog)s --top 10           Show top 10 recommendations
    %(prog)s --type boxes       Only analyze sealed boxes
    %(prog)s --ready-only       Only items ready to list
    %(prog)s --refresh          Ignore cache, re-query eBay
        """,
    )
    parser.add_argument(
        "--top", type=int, default=20,
        help="Number of top items to show (default: 20)",
    )
    parser.add_argument(
        "--type",
        choices=["boxes", "packs", "sets", "singles", "binders", "posters", "comic_books"],
        help="Filter by product type",
    )
    parser.add_argument(
        "--ready-only", action="store_true",
        help="Only analyze items from inventory_status.json (ready to list)",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Force refresh market data (ignore cache)",
    )
    parser.add_argument(
        "--output", type=str,
        help="Save report to a file",
    )
    args = parser.parse_args()

    # Check API credentials
    if not EBAY_APP_ID or not EBAY_CERT_ID:
        print("ERROR: EBAY_APP_ID and EBAY_CERT_ID must be set.")
        print("These are used for the Browse API (Client Credentials).")
        print("Add to ~/.zshrc:")
        print('  export EBAY_APP_ID="your-app-id"')
        print('  export EBAY_CERT_ID="your-cert-id"')
        sys.exit(1)

    # Get Browse API token
    try:
        token = get_browse_token()
    except Exception as e:
        print(f"ERROR: Could not get Browse API token: {e}")
        sys.exit(1)

    # Load inventory
    if args.ready_only:
        items = load_inventory_from_status()
        print(f"Loaded {len(items)} ready-to-list items from inventory_status.json")
    else:
        items = load_inventory_from_csv()
        # Also add ready-to-list items not in the CSV
        status_items = load_inventory_from_status()
        csv_names = {i["name"].lower() for i in items}
        for si in status_items:
            if si["name"].lower() not in csv_names:
                items.append(si)
        print(f"Loaded {len(items)} inventory items")

    if not items:
        print("No inventory items found.")
        print(f"  CSV:    {ANNOTATED_CSV}")
        print(f"  Status: {INVENTORY_STATUS}")
        sys.exit(1)

    # Filter by type if requested
    if args.type:
        items = [i for i in items if i["product_type"] == args.type]
        print(f"Filtered to {len(items)} {args.type} items")

    if not items:
        print("No items match the filter.")
        sys.exit(0)

    # Load market cache
    cache = load_market_cache()

    # Query market data for each item
    print(f"\nQuerying eBay Browse API for {len(items)} items...")
    scored_items = []

    for i, item in enumerate(items, 1):
        keywords = item["keywords"]
        sys.stdout.write(f"\r  [{i}/{len(items)}] {item['name'][:50]:<50s}")
        sys.stdout.flush()

        market = get_market_data(keywords, token, cache, force_refresh=args.refresh)

        if "error" in market:
            continue

        score = calculate_sell_score(market, item["product_type"])

        scored_items.append({
            "name": item["name"],
            "keywords": keywords,
            "product_type": item["product_type"],
            "score": score,
            "avg_price": market.get("avg_price", 0),
            "max_price": market.get("max_price", 0),
            "min_price": market.get("min_price", 0),
            "active_count": market.get("active_count", 0),
            "quantity": item.get("quantity", 1),
            "source": item.get("source", ""),
        })

        # Rate limit: ~2 requests/second
        time.sleep(0.5)

    print()  # Clear progress line

    # Save cache
    save_market_cache(cache)

    # Sort by score (highest first)
    scored_items.sort(key=lambda x: x["score"], reverse=True)

    # Generate report
    report = format_report(scored_items, top_n=args.top)
    print(report)

    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            f.write(report)
        print(f"  Report saved to: {output_path}")


if __name__ == "__main__":
    main()
