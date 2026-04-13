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
    import sys
    from pathlib import Path

    tools_dir = Path(__file__).parent.parent.parent.parent / 'tools'
    sys.path.insert(0, str(tools_dir))

    try:
        from ebay_oauth_setup import get_valid_access_token
        return get_valid_access_token()
    except (ImportError, Exception):
        return None
    finally:
        if str(tools_dir) in sys.path:
            sys.path.remove(str(tools_dir))


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
