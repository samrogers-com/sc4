from django.conf import settings


def site_settings(request):
    """Make key settings available in all templates."""
    return {
        "IMAGE_BASE_URL": getattr(settings, "IMAGE_BASE_URL", ""),
        "EBAY_STORE_URL": getattr(settings, "EBAY_STORE_URL", ""),
    }
