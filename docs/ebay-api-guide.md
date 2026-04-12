# eBay API Guide -- Sam's Collectibles

## Overview

Sam's Collectibles uses three eBay APIs, each serving a different purpose:

| API | Auth Type | Status | Used For |
|-----|-----------|--------|----------|
| Browse API | Client Credentials (App token) | Working | Price lookups, market data, competition analysis |
| Fulfillment API | User OAuth | Pending setup | Pulling sold order history, buyer info |
| Trading API | User OAuth | Planned | Direct listing creation (bypass CSV upload) |

## Authentication Types

### 1. Client Credentials (App Token)

Used by the Browse API. This is a simple server-to-server token that doesn't require any user login. It gives read-only access to public eBay data (active listings, item details, prices).

**Already working.** Used by `ebay_automation/sold_price_lookup.py` and `tools/ebay_best_sellers.py`.

**How it works:**
1. Base64-encode `APP_ID:CERT_ID`
2. POST to `/identity/v1/oauth2/token` with `grant_type=client_credentials`
3. Token lasts 2 hours, auto-refreshes

**Scope:** `https://api.ebay.com/oauth/api_scope`

### 2. User OAuth Token

Used by Fulfillment API and Trading API. Requires the seller (Sam) to log into eBay in a browser and authorize the app. This grants access to seller-specific data like orders, sales history, and listing management.

**Status: Pending setup.** The authorization framework is built (`tools/ebay_oauth_setup.py`), but Sam needs to complete the browser auth flow.

**How it works:**
1. App redirects to eBay login page
2. Sam logs in and clicks "Agree"
3. eBay redirects back to `localhost:8089/callback` with an auth code
4. App exchanges code for access + refresh tokens
5. Tokens saved to `tools/ebay_user_token.json` (gitignored)

**Token lifetimes:**
- Access token: 2 hours (auto-refreshes using refresh token)
- Refresh token: 18 months

**Scopes requested:**
- `sell.fulfillment` / `sell.fulfillment.readonly` -- order history
- `sell.analytics.readonly` -- seller analytics
- `sell.finances` -- financial data
- `sell.inventory` / `sell.inventory.readonly` -- listing management

## How to Set Up User OAuth

### Step 1: Get your RuName

1. Go to https://developer.ebay.com/my/keys
2. Click on your Production App ID
3. Click "User Tokens" next to your Production keyset
4. Under "Get a Token from eBay via Your Application":
   - Set Auth accepted URL: `http://localhost:8089/callback`
   - Set Auth declined URL: `http://localhost:8089/callback`
   - Click "Save"
5. Copy the RuName shown (looks like: `SamRoger-s-SamRoge-PRD-xxxxx`)

### Step 2: Set environment variables

Add to `~/.zshrc`:
```bash
export EBAY_APP_ID="your-client-id"
export EBAY_CERT_ID="your-client-secret"
export EBAY_RUNAME="your-runame-here"
```

Then: `source ~/.zshrc`

### Step 3: Run the auth flow

```bash
cd /Users/samrogers/Claude/sc4
python tools/ebay_oauth_setup.py
```

This opens a browser window. Log in to eBay, click "Agree", and the tokens are saved automatically.

### Step 4: Verify

```bash
python tools/ebay_sold_tracker.py --days 7
```

If you see orders, the setup worked.

## Environment Variables

| Variable | Required For | Description |
|----------|-------------|-------------|
| `EBAY_APP_ID` | All APIs | Client ID from eBay Developer portal |
| `EBAY_CERT_ID` | All APIs | Client Secret from eBay Developer portal |
| `EBAY_DEV_ID` | Trading API | Developer ID (same for sandbox and production) |
| `EBAY_RUNAME` | User OAuth | Redirect URL Name for the auth flow |
| `EBAY_SANDBOX_APP_ID` | Sandbox testing | Sandbox Client ID |
| `EBAY_SANDBOX_CERT_ID` | Sandbox testing | Sandbox Client Secret |

## API Endpoints

### Browse API (Client Credentials)

- **Search active listings:** `GET /buy/browse/v1/item_summary/search`
- **Get item details:** `GET /buy/browse/v1/item/{item_id}`
- **Base URL:** `https://api.ebay.com`

### Fulfillment API (User OAuth)

- **Get orders:** `GET /sell/fulfillment/v1/order`
- **Get single order:** `GET /sell/fulfillment/v1/order/{orderId}`
- **Base URL:** `https://api.ebay.com`

### Trading API (User OAuth -- planned)

- **Add item:** `POST` with `AddItem` call
- **Revise item:** `POST` with `ReviseItem` call
- **Base URL:** `https://api.ebay.com/ws/api.dll`

## Rate Limits

| API | Limit | Notes |
|-----|-------|-------|
| Browse API | 5,000 calls/day | More than enough for price lookups |
| Fulfillment API | 1,000 calls/day | Sufficient for order sync |
| OAuth token refresh | No hard limit | But don't call more than needed |

Best practices:
- Cache results locally (price cache, market cache, order database)
- Use pagination properly (don't re-fetch pages you already have)
- Add 0.5s delays between API calls to be polite
- Store tokens and only refresh when expired (check `expires_in`)

## Tools Reference

| Tool | API Used | Purpose |
|------|----------|---------|
| `ebay_automation/sold_price_lookup.py` | Browse API | Price lookups for active listings |
| `tools/ebay_best_sellers.py` | Browse API | Market analysis and sell recommendations |
| `tools/ebay_sold_tracker.py` | Fulfillment API | Pull sold order history to SQLite |
| `tools/ebay_nightly_sync.py` | Fulfillment API | Nightly cron wrapper for order sync |
| `tools/ebay_oauth_setup.py` | OAuth endpoints | One-time User OAuth authorization |

## Token File Location

- **User OAuth tokens:** `tools/ebay_user_token.json` (gitignored)
- **Browse API tokens:** In-memory cache only (no file, refreshes automatically)
- **Price cache:** `ebay_automation/data/price_cache.json`
- **Market cache:** `tools/data/market_cache.json`
- **Sold history DB:** `tools/data/sold_history.db`

## Sandbox vs Production

The `EBAY_API_ENVIRONMENT` setting in `ebay_automation/config.py` controls which endpoints are used. Default is `production`. Sandbox is available for testing but has limited data.

Sandbox endpoints use `api.sandbox.ebay.com` instead of `api.ebay.com`.
