"""eBay Inventory API service — requires User OAuth."""
from .api_client import get_user_token, make_api_request

INVENTORY_URL = 'https://api.ebay.com/sell/inventory/v1'


def create_listing(listing):
    """Create a new eBay listing. Returns item_id or None."""
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured. Run tools/ebay_oauth_setup.py first.")

    # TODO: Implement eBay Inventory API create_or_replace_inventory_item
    # + create offer + publish offer flow
    raise NotImplementedError("Direct API listing not yet implemented. Use CSV upload for now.")


def revise_listing(listing):
    """Revise an active eBay listing."""
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured.")
    raise NotImplementedError("Revise listing not yet implemented.")


def end_listing(listing):
    """End an active eBay listing."""
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured.")
    raise NotImplementedError("End listing not yet implemented.")


def relist_item(listing):
    """Relist an ended item."""
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured.")
    raise NotImplementedError("Relist not yet implemented.")


def sync_active_listings():
    """Pull active listings from eBay and sync to local DB."""
    token = get_user_token()
    if not token:
        raise PermissionError("User OAuth not configured.")
    raise NotImplementedError("Listing sync not yet implemented.")
