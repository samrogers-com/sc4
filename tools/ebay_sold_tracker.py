#!/usr/bin/env python3
"""
Sam's Collectibles -- eBay Sold Listings Tracker

Pulls sold order history from eBay's Fulfillment API and stores it in
a local SQLite database for analysis, reporting, and trend tracking.

Requires User OAuth token (not the App/Client Credentials token).
Run tools/ebay_oauth_setup.py first to authorize your eBay account.

The Fulfillment API returns orders placed through your seller account,
including line items, buyer info, prices, and eBay fees.

Database: tools/data/sold_history.db
Token:    tools/ebay_user_token.json (gitignored)

Usage:
    # Pull last 30 days of orders (default)
    python tools/ebay_sold_tracker.py

    # Pull last N days
    python tools/ebay_sold_tracker.py --days 7

    # Pull all available history
    python tools/ebay_sold_tracker.py --all

    # Show sales summary
    python tools/ebay_sold_tracker.py --summary

    # Show top sellers
    python tools/ebay_sold_tracker.py --summary --top 10

    # Dry run (show what would be fetched without saving)
    python tools/ebay_sold_tracker.py --dry-run --days 7

    # Force refresh (re-fetch orders already in database)
    python tools/ebay_sold_tracker.py --refresh --days 7

    -h, --help    Show full help
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
DATA_DIR = TOOLS_DIR / "data"
DB_PATH = DATA_DIR / "sold_history.db"

# Import token helper from sibling module
sys.path.insert(0, str(TOOLS_DIR))
try:
    from ebay_oauth_setup import get_valid_access_token, TOKEN_FILE
except ImportError:
    # Fallback if import fails
    TOKEN_FILE = TOOLS_DIR / "ebay_user_token.json"

    def get_valid_access_token():
        return None

# ---------------------------------------------------------------------------
# eBay Fulfillment API
# ---------------------------------------------------------------------------

FULFILLMENT_URL = "https://api.ebay.com/sell/fulfillment/v1/order"

# Orders per page (eBay max is 200)
PAGE_SIZE = 50


def _setup_instructions():
    """Print setup instructions when token is missing."""
    print()
    print("=" * 60)
    print("eBay User OAuth Token Required")
    print("=" * 60)
    print()
    print("The sold listings tracker needs a User OAuth token to access")
    print("your seller account data. This is different from the Browse")
    print("API token (Client Credentials) used for price lookups.")
    print()
    print("To set up:")
    print("  1. Make sure EBAY_APP_ID, EBAY_CERT_ID, and EBAY_RUNAME")
    print("     are set in your ~/.zshrc")
    print("  2. Run:  python tools/ebay_oauth_setup.py")
    print("  3. Log in to eBay in the browser window and click 'Agree'")
    print("  4. The token is saved to tools/ebay_user_token.json")
    print()
    print("Once authorized, re-run this script.")
    print()


def fetch_orders(access_token, days=30, fetch_all=False):
    """
    Fetch orders from the eBay Fulfillment API.

    Args:
        access_token: Valid User OAuth access token
        days: Number of days of history to pull
        fetch_all: If True, ignore days and pull all available

    Yields:
        dict: Individual order objects from the API response
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Build date filter
    if fetch_all:
        # eBay keeps ~90 days of order history via Fulfillment API
        filter_str = ""
    else:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        # eBay expects ISO 8601 format
        date_str = start_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        filter_str = f"creationdate:[{date_str}..]"

    offset = 0
    total_fetched = 0

    while True:
        params = {
            "limit": str(PAGE_SIZE),
            "offset": str(offset),
        }
        if filter_str:
            params["filter"] = filter_str

        try:
            resp = requests.get(
                FULFILLMENT_URL,
                headers=headers,
                params=params,
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            print(f"  Network error: {e}")
            break

        if resp.status_code == 401:
            print("  ERROR: Access token expired or invalid.")
            print("  Run: python tools/ebay_oauth_setup.py")
            break
        elif resp.status_code == 403:
            print("  ERROR: Insufficient permissions.")
            print("  Your token may not have sell.fulfillment scope.")
            print("  Re-run: python tools/ebay_oauth_setup.py")
            break
        elif resp.status_code != 200:
            print(f"  API error {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        orders = data.get("orders", [])

        if not orders:
            break

        for order in orders:
            yield order
            total_fetched += 1

        # Check for more pages
        total_available = data.get("total", 0)
        offset += len(orders)

        if offset >= total_available:
            break

        # Rate limiting: be polite to eBay
        time.sleep(0.5)

    if total_fetched > 0:
        print(f"  Fetched {total_fetched} orders from eBay")


# ---------------------------------------------------------------------------
# SQLite Database
# ---------------------------------------------------------------------------

def init_database():
    """Create the database and tables if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            buyer_username TEXT,
            creation_date TEXT,
            order_total REAL,
            currency TEXT DEFAULT 'USD',
            order_status TEXT,
            payment_status TEXT,
            fulfillment_status TEXT,
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS line_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            item_id TEXT,
            title TEXT,
            sku TEXT,
            quantity INTEGER DEFAULT 1,
            price REAL,
            ebay_fees REAL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            UNIQUE(order_id, item_id)
        )
    """)

    # Index for common queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_creation_date
        ON orders(creation_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_line_items_order_id
        ON line_items(order_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_line_items_title
        ON line_items(title)
    """)

    conn.commit()
    return conn


def store_order(conn, order):
    """
    Store a single order and its line items in the database.

    Args:
        conn: SQLite connection
        order: Order dict from eBay Fulfillment API

    Returns:
        bool: True if new order was inserted, False if already existed
    """
    cursor = conn.cursor()

    order_id = order.get("orderId", "")
    buyer = order.get("buyer", {}).get("username", "unknown")
    creation_date = order.get("creationDate", "")
    total_info = order.get("pricingSummary", {}).get("total", {})
    order_total = float(total_info.get("value", 0))
    currency = total_info.get("currency", "USD")
    order_status = order.get("orderFulfillmentStatus", "")
    payment_status = order.get("orderPaymentStatus", "")
    fulfillment_status = order.get("orderFulfillmentStatus", "")

    # Insert or update order
    try:
        cursor.execute("""
            INSERT INTO orders
                (order_id, buyer_username, creation_date, order_total,
                 currency, order_status, payment_status, fulfillment_status,
                 updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                order_total = excluded.order_total,
                order_status = excluded.order_status,
                payment_status = excluded.payment_status,
                fulfillment_status = excluded.fulfillment_status,
                updated_at = excluded.updated_at
        """, (
            order_id, buyer, creation_date, order_total,
            currency, order_status, payment_status, fulfillment_status,
            datetime.now(timezone.utc).isoformat(),
        ))
        is_new = cursor.rowcount > 0
    except sqlite3.IntegrityError:
        is_new = False

    # Process line items
    for item in order.get("lineItems", []):
        item_id = item.get("lineItemId", "")
        title = item.get("title", "")
        sku = item.get("sku", "")
        quantity = item.get("quantity", 1)
        price_info = item.get("total", {})
        price = float(price_info.get("value", 0))

        # eBay fees are in deliveryCost.shippingCost or can be
        # calculated from the order-level fees
        fees = 0.0
        delivery = item.get("deliveryCost", {})
        if delivery:
            shipping = delivery.get("shippingCost", {})
            fees = float(shipping.get("value", 0))

        try:
            cursor.execute("""
                INSERT INTO line_items
                    (order_id, item_id, title, sku, quantity, price, ebay_fees)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id, item_id) DO UPDATE SET
                    title = excluded.title,
                    sku = excluded.sku,
                    quantity = excluded.quantity,
                    price = excluded.price,
                    ebay_fees = excluded.ebay_fees
            """, (order_id, item_id, title, sku, quantity, price, fees))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    return is_new


def order_exists(conn, order_id):
    """Check if an order already exists in the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,))
    return cursor.fetchone() is not None


# ---------------------------------------------------------------------------
# Summary / Reporting
# ---------------------------------------------------------------------------

def show_summary(conn, top_n=20):
    """Display a sales summary from the database."""
    cursor = conn.cursor()

    # Total orders and revenue
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(order_total), 0),
               MIN(creation_date), MAX(creation_date)
        FROM orders
    """)
    total_orders, total_revenue, earliest, latest = cursor.fetchone()

    if total_orders == 0:
        print("\nNo orders in database yet.")
        print("Run: python tools/ebay_sold_tracker.py --days 30")
        return

    print()
    print("=" * 60)
    print("Sam's Collectibles -- Sales Summary")
    print("=" * 60)
    print()
    print(f"  Total orders:    {total_orders}")
    print(f"  Total revenue:   ${total_revenue:,.2f}")
    print(f"  Average order:   ${total_revenue / total_orders:,.2f}")
    print(f"  Date range:      {earliest[:10] if earliest else 'N/A'}")
    print(f"                   to {latest[:10] if latest else 'N/A'}")

    # Orders by status
    cursor.execute("""
        SELECT order_status, COUNT(*), SUM(order_total)
        FROM orders
        GROUP BY order_status
        ORDER BY COUNT(*) DESC
    """)
    statuses = cursor.fetchall()
    if statuses:
        print()
        print("  By status:")
        for status, count, revenue in statuses:
            print(f"    {status or 'unknown':20s}  {count:4d} orders  ${revenue:,.2f}")

    # Top selling items
    cursor.execute("""
        SELECT title, SUM(quantity) as total_qty,
               SUM(price) as total_revenue,
               AVG(price) as avg_price,
               COUNT(*) as num_orders
        FROM line_items
        WHERE title != ''
        GROUP BY title
        ORDER BY total_revenue DESC
        LIMIT ?
    """, (top_n,))
    top_items = cursor.fetchall()

    if top_items:
        print()
        print(f"  Top {min(top_n, len(top_items))} items by revenue:")
        print(f"  {'Title':<50s}  {'Qty':>4s}  {'Revenue':>10s}  {'Avg':>8s}")
        print(f"  {'-'*50}  {'-'*4}  {'-'*10}  {'-'*8}")
        for title, qty, revenue, avg_price, num_orders in top_items:
            display_title = title[:50] if len(title) <= 50 else title[:47] + "..."
            print(f"  {display_title:<50s}  {qty:4d}  ${revenue:>9,.2f}  ${avg_price:>7,.2f}")

    # Revenue by month
    cursor.execute("""
        SELECT SUBSTR(creation_date, 1, 7) as month,
               COUNT(*) as num_orders,
               SUM(order_total) as revenue
        FROM orders
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """)
    monthly = cursor.fetchall()

    if monthly:
        print()
        print("  Monthly revenue (last 12 months):")
        print(f"  {'Month':>10s}  {'Orders':>6s}  {'Revenue':>10s}")
        print(f"  {'-'*10}  {'-'*6}  {'-'*10}")
        for month, count, revenue in monthly:
            print(f"  {month:>10s}  {count:6d}  ${revenue:>9,.2f}")

    # Total line items
    cursor.execute("SELECT COUNT(*) FROM line_items")
    total_items = cursor.fetchone()[0]
    print()
    print(f"  Total line items tracked: {total_items}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sam's Collectibles -- eBay Sold Listings Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                    Pull last 30 days of orders
    %(prog)s --days 7           Pull last 7 days
    %(prog)s --all              Pull all available history
    %(prog)s --summary          Show sales dashboard
    %(prog)s --summary --top 10 Top 10 sellers
    %(prog)s --dry-run          Preview without saving

Setup:
    1. Set EBAY_APP_ID, EBAY_CERT_ID, EBAY_RUNAME in ~/.zshrc
    2. Run: python tools/ebay_oauth_setup.py
    3. Authorize in browser
    4. Run this script
        """,
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days of history to pull (default: 30)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Pull all available order history",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Show sales summary from stored data",
    )
    parser.add_argument(
        "--top", type=int, default=20,
        help="Number of top items to show in summary (default: 20)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and display orders without saving to database",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Re-fetch and update orders already in database",
    )
    args = parser.parse_args()

    # Summary mode: just read the database
    if args.summary:
        conn = init_database()
        show_summary(conn, top_n=args.top)
        conn.close()
        return

    # Fetch mode: need a valid token
    print("=" * 60)
    print("Sam's Collectibles -- eBay Sold Listings Tracker")
    print("=" * 60)

    access_token = get_valid_access_token()
    if not access_token:
        _setup_instructions()
        sys.exit(1)

    conn = init_database()

    period = "all available history" if args.all else f"last {args.days} days"
    print(f"\n  Fetching orders: {period}")
    if args.dry_run:
        print("  (DRY RUN -- orders will not be saved)")
    print()

    new_count = 0
    update_count = 0
    skip_count = 0

    for order in fetch_orders(access_token, days=args.days, fetch_all=args.all):
        order_id = order.get("orderId", "unknown")
        total = order.get("pricingSummary", {}).get("total", {})
        amount = total.get("value", "0")
        items = order.get("lineItems", [])
        titles = [i.get("title", "?") for i in items]
        title_str = "; ".join(titles)[:60]

        if args.dry_run:
            print(f"  [{order_id}] ${amount} -- {title_str}")
            new_count += 1
            continue

        if not args.refresh and order_exists(conn, order_id):
            skip_count += 1
            continue

        is_new = store_order(conn, order)
        if is_new:
            new_count += 1
            print(f"  + {order_id}: ${amount} -- {title_str}")
        else:
            update_count += 1

    print()
    if args.dry_run:
        print(f"  Found {new_count} orders (dry run, nothing saved)")
    else:
        print(f"  New orders:     {new_count}")
        print(f"  Updated:        {update_count}")
        print(f"  Already stored: {skip_count}")
        print(f"  Database:       {DB_PATH}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
