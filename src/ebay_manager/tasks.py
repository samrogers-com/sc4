"""Background tasks for eBay sync operations."""


def sync_active_listings():
    """Pull current active listings from eBay and update local DB."""
    from .services.inventory import sync_active_listings as _sync
    return _sync()


def sync_orders(days=7):
    """Pull recent orders and update statuses."""
    from .services.fulfillment import sync_orders_to_db
    return sync_orders_to_db(days=days)


def auto_relist():
    """Relist ended items that meet criteria."""
    # TODO: Implement auto-relist logic
    pass


def update_prices():
    """Check market prices and flag items needing adjustment."""
    # TODO: Implement price update logic
    pass
