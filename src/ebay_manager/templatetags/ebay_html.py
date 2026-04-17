"""Template tags / filters for rendering eBay description HTML safely."""
from django import template
from django.utils.safestring import mark_safe

from ebay_manager.services.html_sanitizer import sanitize_ebay_html


register = template.Library()


@register.filter(name='ebay_safe', is_safe=True)
def ebay_safe(value):
    """Sanitize an eBay description HTML string and mark the result safe.

    Drop-in replacement for ``|safe`` that strips <script>, event
    handlers, dangerous URL schemes, and unknown CSS. Use this for any
    template rendering ``description_html`` (or comparable fields) in
    admin views.
    """
    return mark_safe(sanitize_ebay_html(value or ''))
