"""
Base eBay API client with OAuth token management.
Handles both Client Credentials (Browse API) and User OAuth (Fulfillment/Inventory).
"""
import base64
import os
import time
import requests

EBAY_APP_ID = os.environ.get('EBAY_APP_ID', '')
EBAY_CERT_ID = os.environ.get('EBAY_CERT_ID', '')

TOKEN_ENDPOINT = 'https://api.ebay.com/identity/v1/oauth2/token'

_app_token_cache = {'access_token': None, 'expires_at': 0}


def get_app_token():
    """Get Client Credentials token for Browse API."""
    now = time.time()
    if _app_token_cache['access_token'] and now < _app_token_cache['expires_at'] - 60:
        return _app_token_cache['access_token']

    if not EBAY_APP_ID or not EBAY_CERT_ID:
        return None

    credentials = base64.b64encode(f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()).decode()
    resp = requests.post(TOKEN_ENDPOINT, headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {credentials}',
    }, data={
        'grant_type': 'client_credentials',
        'scope': 'https://api.ebay.com/oauth/api_scope',
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    _app_token_cache['access_token'] = data['access_token']
    _app_token_cache['expires_at'] = now + data.get('expires_in', 7200)
    return data['access_token']


def get_user_token():
    """Get User OAuth token for Fulfillment/Inventory APIs."""
    import json
    from pathlib import Path

    token_file = Path(__file__).parent.parent.parent / 'tools' / 'ebay_user_token.json'
    if not token_file.exists():
        return None

    try:
        tokens = json.loads(token_file.read_text())
    except Exception:
        return None

    saved_at = tokens.get('saved_at', 0)
    expires_in = tokens.get('expires_in', 7200)

    # Check if access token is still valid (with 5 min buffer)
    if time.time() < saved_at + expires_in - 300:
        return tokens.get('access_token')

    # Refresh the access token
    refresh_token = tokens.get('refresh_token')
    if not refresh_token:
        return None

    try:
        credentials = base64.b64encode(f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()).decode()
        resp = requests.post(TOKEN_ENDPOINT, headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {credentials}',
        }, data={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'scope': 'https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.fulfillment https://api.ebay.com/oauth/api_scope/sell.inventory',
        }, timeout=15)
        resp.raise_for_status()
        new_tokens = resp.json()
        new_tokens['refresh_token'] = refresh_token
        new_tokens['saved_at'] = time.time()
        new_tokens['environment'] = 'production'
        with open(token_file, 'w') as f:
            json.dump(new_tokens, f, indent=2)
        return new_tokens.get('access_token')
    except Exception:
        return None


def has_user_auth():
    """Check if User OAuth is configured."""
    return get_user_token() is not None


def make_api_request(method, url, token=None, **kwargs):
    """Make an authenticated eBay API request."""
    if not token:
        token = get_app_token()
    if not token:
        raise ValueError("No API token available")

    headers = kwargs.pop('headers', {})
    headers.update({
        'Authorization': f'Bearer {token}',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
        'Content-Type': 'application/json',
    })

    resp = requests.request(method, url, headers=headers, timeout=20, **kwargs)
    resp.raise_for_status()
    return resp.json()
