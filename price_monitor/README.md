# Sam's Collectibles - Price Monitor

Local FastAPI tool for monitoring eBay sold prices across your collectibles inventory.

## Quick Start

```bash
cd price_monitor
pip install -r requirements.txt
uvicorn app:app --port 8080
```

Then open http://localhost:8080 in your browser.

## First Run

1. Start the app - the database tables are created automatically
2. Click "Import from CSV" on the dashboard to load your inventory
3. Click individual refresh buttons or "Refresh All" to fetch eBay sold prices

## Prerequisites

- Python 3.10+
- eBay Developer API key (free at https://developer.ebay.com)
- Set your API key: `export EBAY_APP_ID="your-app-id"`

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard with inventory table |
| `/api/inventory` | GET | All inventory items with latest prices |
| `/api/inventory/{id}` | GET | Single item with full price history |
| `/api/prices/refresh/{id}` | GET | Trigger eBay lookup for one item |
| `/api/prices/refresh-all` | POST | Refresh all items (rate-limited) |
| `/api/prices/summary` | GET | Overall stats and top items |
| `/api/prices/trends` | GET | Items with biggest price changes |
| `/api/inventory/import` | POST | Import inventory from CSV |
| `/api/status` | GET | App health and configuration check |

## Rate Limiting

The "Refresh All" endpoint adds a 3-second delay between eBay API calls to avoid rate limiting. It runs in the background - reload the dashboard to see updated prices.

## Data Storage

Price history is stored in `data/prices.db` (SQLite). This file is gitignored. Each price check creates a new row so you can track trends over time.
