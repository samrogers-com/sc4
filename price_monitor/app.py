"""
Sam's Collectibles - Price Monitor
FastAPI app for tracking eBay sold prices across inventory.

Usage:
    cd price_monitor
    pip install -r requirements.txt
    uvicorn app:app --port 8080
"""

import asyncio
import csv
import os
import sqlite3
import statistics
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# eBay API integration - import from sibling ebay_automation package
# ---------------------------------------------------------------------------
EBAY_AUTOMATION_DIR = Path(__file__).parent.parent / "ebay_automation"
sys.path.insert(0, str(EBAY_AUTOMATION_DIR))

try:
    from sold_price_lookup import search_sold_items, calculate_price
    HAS_EBAY = True
except ImportError:
    HAS_EBAY = False

try:
    from config import EBAY_APP_ID, EBAY_CERT_ID
except ImportError:
    EBAY_APP_ID = os.environ.get("EBAY_APP_ID", "")
    EBAY_CERT_ID = os.environ.get("EBAY_CERT_ID", "")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "prices.db"
CSV_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "non_sports_cards"
    / "static"
    / "nstc-core-10-29-22-annotated.csv"
)
TEMPLATES_DIR = BASE_DIR / "templates"

# Rate limiting state for refresh-all
_refresh_lock = asyncio.Lock()
_refresh_running = False
_refresh_progress = {"total": 0, "completed": 0, "errors": 0, "current_item": "", "status": "idle"}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            title TEXT,
            maker TEXT,
            year_made TEXT,
            type TEXT,
            type_number INTEGER,
            quantity INTEGER,
            category TEXT
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_id INTEGER REFERENCES inventory(id),
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            search_query TEXT,
            num_results INTEGER,
            min_price REAL,
            avg_price REAL,
            median_price REAL,
            max_price REAL,
            recommended_price REAL
        );

        CREATE INDEX IF NOT EXISTS idx_price_history_inv
            ON price_history(inventory_id);
        CREATE INDEX IF NOT EXISTS idx_price_history_date
            ON price_history(checked_at);
        """
    )
    conn.close()


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------
def import_csv(csv_path: Path | str = CSV_PATH) -> dict:
    conn = get_db()
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return {"error": f"CSV not found: {csv_path}"}

    inserted = 0
    skipped = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qty_raw = row.get("quantity", "0")
            try:
                qty = int(qty_raw)
            except (ValueError, TypeError):
                qty = 0
            if qty <= 0:
                skipped += 1
                continue

            product_id = int(row.get("product_id", 0) or 0)
            title = row.get("title", "").strip()
            maker = row.get("maker", "").strip() or None
            year_made = row.get("year_made", "").strip() or None
            item_type = row.get("type", "").strip() or "base"
            type_number = int(row.get("type_number", 0) or 0)

            # Check if already imported (by product_id)
            existing = conn.execute(
                "SELECT id FROM inventory WHERE product_id = ?", (product_id,)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            conn.execute(
                """INSERT INTO inventory
                   (product_id, title, maker, year_made, type, type_number, quantity, category)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (product_id, title, maker, year_made, item_type, type_number, qty, "ns-cards"),
            )
            inserted += 1

    conn.commit()
    conn.close()
    return {"inserted": inserted, "skipped": skipped}


# ---------------------------------------------------------------------------
# eBay lookup helper
# ---------------------------------------------------------------------------
def build_search_query(item: dict) -> str:
    """Build eBay search keywords from an inventory item."""
    parts = []
    if item.get("year_made"):
        parts.append(str(item["year_made"]))
    if item.get("maker"):
        parts.append(str(item["maker"]))
    parts.append(str(item["title"]))

    item_type = item.get("type", "base")
    if item_type == "box":
        parts.append("sealed box trading cards")
    elif item_type == "base":
        parts.append("complete set trading cards")
    elif item_type == "chase":
        parts.append("chase set trading cards")
    elif item_type == "insert":
        parts.append("insert set trading cards")
    elif item_type == "sticker":
        parts.append("sticker set trading cards")
    else:
        parts.append("trading cards")

    return " ".join(parts)


def do_price_lookup(inventory_id: int) -> dict:
    """Run a price lookup for one inventory item and store results."""
    conn = get_db()
    item = conn.execute("SELECT * FROM inventory WHERE id = ?", (inventory_id,)).fetchone()
    if not item:
        conn.close()
        return {"error": "Item not found"}

    item_dict = dict(item)
    query = build_search_query(item_dict)

    if not HAS_EBAY:
        conn.close()
        return {"error": "eBay API module not available (check sold_price_lookup.py)", "search_query": query}

    if not EBAY_APP_ID or not EBAY_CERT_ID:
        conn.close()
        return {"error": "EBAY_APP_ID and EBAY_CERT_ID not configured", "search_query": query}

    sold_items = search_sold_items(query)
    pricing = calculate_price(sold_items, strategy="highest")

    num_results = pricing.get("num_sold", 0)
    min_price = pricing.get("lowest") if num_results else None
    avg_price = pricing.get("average") if num_results else None
    max_price = pricing.get("highest") if num_results else None
    recommended = pricing.get("recommended_price")

    # Calculate median from prices list
    prices = pricing.get("prices", [])
    median_price = statistics.median(prices) if prices else None

    conn.execute(
        """INSERT INTO price_history
           (inventory_id, search_query, num_results, min_price, avg_price, median_price, max_price, recommended_price)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (inventory_id, query, num_results, min_price, avg_price, median_price, max_price, recommended),
    )
    conn.commit()
    conn.close()

    return {
        "inventory_id": inventory_id,
        "search_query": query,
        "num_results": num_results,
        "min_price": min_price,
        "avg_price": avg_price,
        "median_price": median_price,
        "max_price": max_price,
        "recommended_price": recommended,
    }


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Sam's Collectibles - Price Monitor",
    description="Local eBay sold price tracker for non-sport trading cards, comic books, and movie posters. "
                "Import inventory from CSV, fetch sold prices from eBay Finding API, and track trends over time.",
    version="1.0.0",
    lifespan=lifespan,
)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, summary="Dashboard", description="Interactive HTML dashboard showing all inventory with prices, trends, and controls.")
async def dashboard(request: Request):
    conn = get_db()

    # Get all inventory items with their latest price data
    rows = conn.execute(
        """
        SELECT
            i.*,
            ph.checked_at,
            ph.num_results,
            ph.min_price,
            ph.avg_price,
            ph.median_price,
            ph.max_price,
            ph.recommended_price,
            ph.search_query
        FROM inventory i
        LEFT JOIN price_history ph ON ph.id = (
            SELECT ph2.id FROM price_history ph2
            WHERE ph2.inventory_id = i.id
            ORDER BY ph2.checked_at DESC LIMIT 1
        )
        ORDER BY i.title
        """
    ).fetchall()

    # For trend calculation, get previous price too
    items = []
    for row in rows:
        item = dict(row)

        # Get previous price for trend
        prev = conn.execute(
            """
            SELECT recommended_price FROM price_history
            WHERE inventory_id = ? ORDER BY checked_at DESC LIMIT 1 OFFSET 1
            """,
            (item["id"],),
        ).fetchone()

        trend = "none"
        if item.get("recommended_price") is not None and prev and prev["recommended_price"] is not None:
            diff = item["recommended_price"] - prev["recommended_price"]
            if diff > 0.5:
                trend = "up"
            elif diff < -0.5:
                trend = "down"
            else:
                trend = "stable"
        elif item.get("recommended_price") is not None:
            trend = "stable"

        item["trend"] = trend
        items.append(item)

    conn.close()

    # Collect unique types for filter
    types = sorted(set(i["type"] for i in items if i.get("type")))

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "items": items,
            "types": types,
            "total_items": len(items),
            "has_ebay": HAS_EBAY,
            "has_api_key": bool(EBAY_APP_ID) and bool(EBAY_CERT_ID),
        },
    )


@app.get("/api/inventory", summary="List inventory", description="All inventory items with their latest price data from eBay.")
async def api_inventory():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT
            i.*,
            ph.checked_at,
            ph.num_results,
            ph.min_price,
            ph.avg_price,
            ph.median_price,
            ph.max_price,
            ph.recommended_price
        FROM inventory i
        LEFT JOIN price_history ph ON ph.id = (
            SELECT ph2.id FROM price_history ph2
            WHERE ph2.inventory_id = i.id
            ORDER BY ph2.checked_at DESC LIMIT 1
        )
        ORDER BY i.title
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/inventory/{item_id}", summary="Get single item", description="Single inventory item with full price history (all past lookups).")
async def api_inventory_item(item_id: int):
    conn = get_db()
    item = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, "Item not found")

    history = conn.execute(
        """SELECT * FROM price_history
           WHERE inventory_id = ?
           ORDER BY checked_at DESC""",
        (item_id,),
    ).fetchall()
    conn.close()

    return {
        "item": dict(item),
        "price_history": [dict(h) for h in history],
    }


@app.get("/api/prices/refresh/{item_id}", summary="Refresh one item", description="Trigger a fresh eBay Finding API lookup for a single item. Stores result in price history.")
async def api_refresh_price(item_id: int):
    result = do_price_lookup(item_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/prices/refresh-all", summary="Refresh all prices", description="Refresh prices for all inventory items in the background. Rate-limited to 1 eBay API call per 5 seconds.")
async def api_refresh_all(background_tasks: BackgroundTasks):
    global _refresh_running, _refresh_progress
    if _refresh_running:
        return {"status": "already_running", "message": "A refresh is already in progress", "progress": _refresh_progress}

    _refresh_running = True

    def run_all():
        global _refresh_running, _refresh_progress
        try:
            conn = get_db()
            items = conn.execute("SELECT id, title FROM inventory ORDER BY id").fetchall()
            conn.close()
            total = len(items)
            _refresh_progress = {"total": total, "completed": 0, "errors": 0, "current_item": "", "status": "running"}

            for i, row in enumerate(items):
                _refresh_progress["current_item"] = row["title"]
                _refresh_progress["completed"] = i
                try:
                    do_price_lookup(row["id"])
                except Exception as e:
                    _refresh_progress["errors"] += 1
                    print(f"Error refreshing item {row['id']} ({row['title']}): {e}")
                time.sleep(7)  # Rate limit: 1 request per 5 seconds

            _refresh_progress["completed"] = total
            _refresh_progress["status"] = "done"
        finally:
            _refresh_running = False

    background_tasks.add_task(run_all)
    return {"status": "started", "message": f"Refresh started in background", "progress": _refresh_progress}


@app.post("/api/prices/refresh-filtered", summary="Refresh filtered items", description="Refresh prices only for specific inventory item IDs. Pass {item_ids: [1,2,3]}.")
async def api_refresh_filtered(request: Request, background_tasks: BackgroundTasks):
    global _refresh_running, _refresh_progress
    if _refresh_running:
        return {"status": "already_running", "message": "A refresh is already in progress", "progress": _refresh_progress}

    body = await request.json()
    item_ids = body.get("item_ids", [])
    if not item_ids:
        return {"status": "error", "message": "No item_ids provided"}

    _refresh_running = True

    def run_filtered():
        global _refresh_running, _refresh_progress
        try:
            conn = get_db()
            placeholders = ",".join("?" for _ in item_ids)
            items = conn.execute(f"SELECT id, title FROM inventory WHERE id IN ({placeholders}) ORDER BY id", item_ids).fetchall()
            conn.close()
            total = len(items)
            _refresh_progress = {"total": total, "completed": 0, "errors": 0, "current_item": "", "status": "running"}

            for i, row in enumerate(items):
                _refresh_progress["current_item"] = row["title"]
                _refresh_progress["completed"] = i
                try:
                    do_price_lookup(row["id"])
                except Exception as e:
                    _refresh_progress["errors"] += 1
                    print(f"Error refreshing item {row['id']} ({row['title']}): {e}")
                time.sleep(7)

            _refresh_progress["completed"] = total
            _refresh_progress["status"] = "done"
        finally:
            _refresh_running = False

    background_tasks.add_task(run_filtered)
    return {"status": "started", "message": f"Refreshing {len(item_ids)} items in background", "progress": _refresh_progress}


@app.get("/api/prices/refresh-status", summary="Refresh status", description="Check progress of a running refresh-all operation.")
async def api_refresh_status():
    return {"running": _refresh_running, "progress": _refresh_progress}


@app.get("/api/prices/summary", summary="Price summary", description="Overall stats: total inventory value, highest/lowest prices, items without prices, top 10 by value.")
async def api_price_summary():
    conn = get_db()

    total_items = conn.execute("SELECT COUNT(*) as c FROM inventory").fetchone()["c"]
    total_qty = conn.execute("SELECT COALESCE(SUM(quantity), 0) as q FROM inventory").fetchone()["q"]

    # Items with at least one price check
    priced = conn.execute(
        """
        SELECT
            COUNT(DISTINCT i.id) as count,
            SUM(i.quantity * ph.recommended_price) as total_value,
            MAX(ph.recommended_price) as highest_price,
            MIN(ph.recommended_price) as lowest_price,
            AVG(ph.recommended_price) as avg_price
        FROM inventory i
        JOIN price_history ph ON ph.id = (
            SELECT ph2.id FROM price_history ph2
            WHERE ph2.inventory_id = i.id
            ORDER BY ph2.checked_at DESC LIMIT 1
        )
        WHERE ph.recommended_price IS NOT NULL
        """
    ).fetchone()

    without_prices = conn.execute(
        """
        SELECT COUNT(*) as c FROM inventory i
        WHERE NOT EXISTS (
            SELECT 1 FROM price_history ph WHERE ph.inventory_id = i.id
        )
        """
    ).fetchone()["c"]

    # Highest value items
    top_items = conn.execute(
        """
        SELECT i.title, i.type, i.quantity, ph.recommended_price,
               (i.quantity * ph.recommended_price) as total_value
        FROM inventory i
        JOIN price_history ph ON ph.id = (
            SELECT ph2.id FROM price_history ph2
            WHERE ph2.inventory_id = i.id
            ORDER BY ph2.checked_at DESC LIMIT 1
        )
        WHERE ph.recommended_price IS NOT NULL
        ORDER BY total_value DESC LIMIT 10
        """
    ).fetchall()

    conn.close()

    return {
        "total_items": total_items,
        "total_quantity": total_qty,
        "items_with_prices": priced["count"] if priced["count"] else 0,
        "items_without_prices": without_prices,
        "total_inventory_value": round(priced["total_value"], 2) if priced["total_value"] else 0,
        "highest_price": priced["highest_price"],
        "lowest_price": priced["lowest_price"],
        "average_price": round(priced["avg_price"], 2) if priced["avg_price"] else None,
        "top_items": [dict(r) for r in top_items],
    }


@app.get("/api/prices/trends", summary="Price trends", description="Items with biggest price changes between consecutive lookups. Requires at least 2 price checks per item.")
async def api_price_trends():
    conn = get_db()

    # Items with at least 2 price checks - compare latest vs previous
    rows = conn.execute(
        """
        SELECT
            i.id, i.title, i.type, i.quantity,
            latest.recommended_price as current_price,
            latest.checked_at as current_date,
            prev.recommended_price as previous_price,
            prev.checked_at as previous_date
        FROM inventory i
        JOIN price_history latest ON latest.id = (
            SELECT ph.id FROM price_history ph
            WHERE ph.inventory_id = i.id ORDER BY ph.checked_at DESC LIMIT 1
        )
        JOIN price_history prev ON prev.id = (
            SELECT ph.id FROM price_history ph
            WHERE ph.inventory_id = i.id ORDER BY ph.checked_at DESC LIMIT 1 OFFSET 1
        )
        WHERE latest.recommended_price IS NOT NULL
          AND prev.recommended_price IS NOT NULL
          AND prev.recommended_price > 0
        ORDER BY ABS(latest.recommended_price - prev.recommended_price) DESC
        LIMIT 20
        """
    ).fetchall()

    conn.close()

    trends = []
    for r in rows:
        d = dict(r)
        change = d["current_price"] - d["previous_price"]
        pct = (change / d["previous_price"]) * 100 if d["previous_price"] else 0
        d["price_change"] = round(change, 2)
        d["price_change_pct"] = round(pct, 1)
        d["direction"] = "up" if change > 0 else "down" if change < 0 else "stable"
        trends.append(d)

    return trends


@app.post("/api/inventory/import", summary="Import inventory", description="Load inventory from the annotated CSV. Only imports items with quantity > 0. Skips duplicates.")
async def api_import_inventory():
    result = import_csv()
    return result


@app.get("/api/status", summary="Health check", description="App health, eBay SDK status, API key status, and DB/CSV paths.")
async def api_status():
    return {
        "app": "Sam's Collectibles Price Monitor",
        "ebay_module_available": HAS_EBAY,
        "ebay_credentials_set": bool(EBAY_APP_ID) and bool(EBAY_CERT_ID),
        "db_path": str(DB_PATH),
        "csv_path": str(CSV_PATH),
        "csv_exists": CSV_PATH.exists(),
        "refresh_running": _refresh_running,
    }


# ---------------------------------------------------------------------------
# CLI entry point with --help
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Sam's Collectibles - Price Monitor",
        epilog="""
Endpoints (once running):
  http://localhost:PORT/              Dashboard (interactive HTML)
  http://localhost:PORT/docs          Swagger UI (interactive API docs)
  http://localhost:PORT/redoc         ReDoc (API reference)
  http://localhost:PORT/api/status    Health check

  http://localhost:PORT/api/inventory           List all items with latest prices
  http://localhost:PORT/api/inventory/{id}      Single item with price history
  http://localhost:PORT/api/prices/refresh/{id} Refresh price for one item
  http://localhost:PORT/api/prices/refresh-all  Refresh all (POST, rate-limited)
  http://localhost:PORT/api/prices/summary      Overall stats and top items
  http://localhost:PORT/api/prices/trends       Biggest price changes
  http://localhost:PORT/api/inventory/import    Import from CSV (POST)

First run:
  1. Start the app
  2. Open the dashboard and click "Import from CSV"
  3. Click refresh buttons to fetch eBay sold prices

Requires: export EBAY_APP_ID="your-key" (from developer.ebay.com)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=8080, help="Port to run on (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev mode)")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
