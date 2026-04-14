#!/usr/bin/env python3
"""
Sam's Collectibles — eBay User OAuth Setup

One-time setup to authorize your eBay account for accessing
seller-specific data (sold listings, orders, analytics).

This creates a User OAuth token (different from the App token
we already have for browsing). The User token lets us:
- Pull YOUR sold listing history
- Get order details and buyer info
- Access seller analytics
- Create/manage listings via API

Usage:
    python tools/ebay_oauth_setup.py

    This will:
    1. Open your browser to eBay's authorization page
    2. You log in and click "Agree"
    3. eBay redirects back to localhost:8089
    4. We capture the auth code and exchange it for tokens
    5. Tokens are saved to tools/ebay_user_token.json

    The refresh token lasts 18 months. The access token expires
    in 2 hours but auto-refreshes using the refresh token.
"""

import base64
import json
import os
import sys
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests

# eBay OAuth Configuration
EBAY_APP_ID = os.environ.get('EBAY_APP_ID', '')
EBAY_CERT_ID = os.environ.get('EBAY_CERT_ID', '')

# OAuth endpoints
OAUTH_ENDPOINTS = {
    'production': {
        'auth_url': 'https://auth.ebay.com/oauth2/authorize',
        'token_url': 'https://api.ebay.com/identity/v1/oauth2/token',
    },
    'sandbox': {
        'auth_url': 'https://auth.sandbox.ebay.com/oauth2/authorize',
        'token_url': 'https://api.sandbox.ebay.com/identity/v1/oauth2/token',
    },
}

ENVIRONMENT = 'production'
REDIRECT_URI = 'http://localhost:8089/callback'
# This is the RuName (eBay Redirect URL Name) — configured in your eBay
# Developer account under your application's OAuth settings
RUNAME = os.environ.get('EBAY_RUNAME', '')

# Scopes we need for seller data
SCOPES = [
    'https://api.ebay.com/oauth/api_scope',
    'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
    'https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly',
    'https://api.ebay.com/oauth/api_scope/sell.analytics.readonly',
    'https://api.ebay.com/oauth/api_scope/sell.finances',
    'https://api.ebay.com/oauth/api_scope/sell.inventory',
    'https://api.ebay.com/oauth/api_scope/sell.inventory.readonly',
]

TOKEN_FILE = Path(__file__).parent / 'ebay_user_token.json'


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth callback from eBay."""

    auth_code = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if 'code' in params:
            OAuthCallbackHandler.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:sans-serif;text-align:center;padding:50px">
                <h1 style="color:green">Authorization Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                <p>Your eBay account has been authorized for Sam's Collectibles.</p>
                </body></html>
            """)
        elif 'error' in params:
            error = params.get('error', ['unknown'])[0]
            error_desc = params.get('error_description', [''])[0]
            self.send_response(400)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(f"""
                <html><body style="font-family:sans-serif;text-align:center;padding:50px">
                <h1 style="color:red">Authorization Failed</h1>
                <p>Error: {error}</p>
                <p>{error_desc}</p>
                </body></html>
            """.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging


def get_auth_url():
    """Build the eBay authorization URL."""
    endpoints = OAUTH_ENDPOINTS[ENVIRONMENT]
    params = {
        'client_id': EBAY_APP_ID,
        'redirect_uri': RUNAME,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
    }
    return f"{endpoints['auth_url']}?{urlencode(params)}"


def exchange_code_for_token(auth_code):
    """Exchange the authorization code for access + refresh tokens."""
    endpoints = OAUTH_ENDPOINTS[ENVIRONMENT]
    credentials = base64.b64encode(
        f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()
    ).decode()

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {credentials}',
    }
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': RUNAME,
    }

    resp = requests.post(endpoints['token_url'], headers=headers, data=data, timeout=15)
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token):
    """Use a refresh token to get a new access token."""
    endpoints = OAUTH_ENDPOINTS[ENVIRONMENT]
    credentials = base64.b64encode(
        f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()
    ).decode()

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {credentials}',
    }
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'scope': ' '.join(SCOPES),
    }

    resp = requests.post(endpoints['token_url'], headers=headers, data=data, timeout=15)
    resp.raise_for_status()
    return resp.json()


def save_tokens(token_data):
    """Save tokens to disk."""
    token_data['saved_at'] = time.time()
    token_data['environment'] = ENVIRONMENT
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f, indent=2)
    # Restrict permissions
    os.chmod(TOKEN_FILE, 0o600)
    print(f"Tokens saved to: {TOKEN_FILE}")


def load_tokens():
    """Load tokens from disk."""
    if not TOKEN_FILE.exists():
        return None
    with open(TOKEN_FILE, 'r') as f:
        return json.load(f)


def get_valid_access_token():
    """Get a valid access token, refreshing if needed."""
    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run this script to authorize first.")
        return None

    saved_at = tokens.get('saved_at', 0)
    expires_in = tokens.get('expires_in', 7200)

    # Check if access token is still valid (with 5 min buffer)
    if time.time() < saved_at + expires_in - 300:
        return tokens['access_token']

    # Refresh the access token
    print("Access token expired, refreshing...")
    refresh_token = tokens.get('refresh_token')
    if not refresh_token:
        print("No refresh token. Re-run authorization.")
        return None

    try:
        new_tokens = refresh_access_token(refresh_token)
        # Keep the refresh token (it doesn't change on refresh)
        new_tokens['refresh_token'] = refresh_token
        save_tokens(new_tokens)
        return new_tokens['access_token']
    except Exception as e:
        print(f"Token refresh failed: {e}")
        print("Re-run authorization.")
        return None


def main():
    print("=" * 60)
    print("Sam's Collectibles — eBay User OAuth Setup")
    print("=" * 60)

    # Check credentials
    if not EBAY_APP_ID or not EBAY_CERT_ID:
        print("\nERROR: EBAY_APP_ID and EBAY_CERT_ID must be set.")
        print("Add to ~/.zshrc:")
        print('  export EBAY_APP_ID="your-app-id"')
        print('  export EBAY_CERT_ID="your-cert-id"')
        sys.exit(1)

    if not RUNAME:
        print("\n" + "=" * 60)
        print("SETUP REQUIRED: eBay RuName (Redirect URL Name)")
        print("=" * 60)
        print()
        print("Before running this script, you need to configure a")
        print("Redirect URL (RuName) in your eBay Developer account:")
        print()
        print("1. Go to: https://developer.ebay.com/my/keys")
        print("2. Click on your Production App ID")
        print("3. Click 'User Tokens' next to your Production keyset")
        print("4. Under 'Get a Token from eBay via Your Application':")
        print("   - Set Auth accepted URL: http://localhost:8089/callback")
        print("   - Set Auth declined URL: http://localhost:8089/callback")
        print("   - Click 'Save'")
        print("5. Copy the RuName shown (looks like: SamRoger-s-SamRoge-PRD-xxxxx)")
        print("6. Add to ~/.zshrc:")
        print('   export EBAY_RUNAME="your-runame-here"')
        print("7. Run: source ~/.zshrc")
        print("8. Re-run this script")
        print()
        sys.exit(1)

    # Check if we already have tokens
    existing = load_tokens()
    if existing and existing.get('refresh_token'):
        print(f"\nExisting tokens found (saved at {time.ctime(existing.get('saved_at', 0))})")
        print(f"Environment: {existing.get('environment', 'unknown')}")
        choice = input("Re-authorize? (y/N): ").strip().lower()
        if choice != 'y':
            # Try to refresh
            token = get_valid_access_token()
            if token:
                print(f"\nAccess token is valid!")
                print(f"Token: {token[:20]}...")
                print("\nYou're all set. The sold listings tracker can use this token.")
            return

    # Start the OAuth flow
    auth_url = get_auth_url()
    print(f"\nOpening eBay authorization in your browser...")
    print(f"If it doesn't open, go to:\n{auth_url}\n")

    # Start local callback server
    server = HTTPServer(('localhost', 8089), OAuthCallbackHandler)
    server.timeout = 120  # 2 minute timeout

    # Open browser
    webbrowser.open(auth_url)

    print("Waiting for authorization callback...")
    print("(Log in to eBay and click 'Agree' in the browser)")
    print()

    # Wait for callback
    while OAuthCallbackHandler.auth_code is None:
        server.handle_request()
        if OAuthCallbackHandler.auth_code:
            break

    server.server_close()

    if not OAuthCallbackHandler.auth_code:
        print("ERROR: No authorization code received.")
        sys.exit(1)

    print("Authorization code received! Exchanging for tokens...")

    # Exchange code for tokens
    try:
        token_data = exchange_code_for_token(OAuthCallbackHandler.auth_code)
        save_tokens(token_data)

        print("\n" + "=" * 60)
        print("SUCCESS! eBay account authorized.")
        print("=" * 60)
        print(f"Access token expires in: {token_data.get('expires_in', 0)} seconds")
        print(f"Refresh token expires in: {token_data.get('refresh_token_expires_in', 0)} seconds")
        print(f"  ({token_data.get('refresh_token_expires_in', 0) // 86400} days)")
        print(f"\nTokens saved to: {TOKEN_FILE}")
        print("\nNext steps:")
        print("  - The sold listings tracker will use this token automatically")
        print("  - The refresh token lasts 18 months")
        print("  - Access token auto-refreshes every 2 hours")

    except requests.exceptions.HTTPError as e:
        print(f"\nERROR exchanging code for tokens: {e}")
        print(f"Response: {e.response.text}")
        sys.exit(1)


if __name__ == '__main__':
    main()
