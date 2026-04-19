"""Template filters for social_manager templates."""
from django import template

register = template.Library()


@register.filter
def get_item(dct, key):
    """Dictionary lookup by variable key in a template — `{{ dct|get_item:k }}`."""
    if dct is None:
        return ''
    try:
        return dct.get(key, '')
    except (AttributeError, TypeError):
        return ''
