"""HTML sanitization for eBay description HTML rendered in admin views.

Description HTML gets rendered via Django's `|safe` filter in staff-only
pages (preview, variant group detail, listing detail, etc.). Today the
HTML is authored by us under `ebay_uploads/ns_cards/.../*.html` or
generated server-side by `description_generator`, so the trust story is
intact. This sanitizer is a belt-and-suspenders defense for the day
description HTML starts coming from a less trusted source (eBay sync,
scraped listings, user paste-in, etc.) — it strips scripts, event
handlers, and dangerous URL schemes while preserving the eBay-safe
subset of HTML actually used in our descriptions.

The allowlist matches the tag/attribute set documented in the
`ebay-html-builder` skill (tables, <font>, <center>, <b>/<i>/<u>,
<ul>/<li>, <hr>, <br>).  Anything else is escaped.
"""
import bleach
from bleach.css_sanitizer import CSSSanitizer


# Tags eBay's renderer actually honors + the ones our HTML author uses.
# Anything NOT listed here is escaped by bleach.clean().
ALLOWED_TAGS: frozenset[str] = frozenset({
    'a',
    'b',
    'br',
    'center',
    'em',
    'font',
    'hr',
    'i',
    'img',
    'li',
    'ol',
    'p',
    'span',
    'strong',
    'table',
    'tbody',
    'td',
    'th',
    'thead',
    'tr',
    'u',
    'ul',
})


# Attribute allowlist. Keys are tag names; '*' applies to every tag.
# Anything not listed is dropped. NOTE: 'on*' event handlers are absent
# by design — this is the key mitigation for XSS in admin modals.
ALLOWED_ATTRIBUTES: dict = {
    '*': ['align', 'class', 'id', 'style', 'title'],
    'a': ['href', 'rel', 'target'],
    'font': ['color', 'face', 'size', 'rwr'],  # rwr is eBay-proprietary
    'img': ['alt', 'height', 'src', 'width'],
    'table': [
        'background', 'bgcolor', 'border', 'cellpadding', 'cellspacing',
        'height', 'width',
    ],
    'td': [
        'background', 'bgcolor', 'colspan', 'height', 'rowspan',
        'valign', 'width',
    ],
    'th': [
        'background', 'bgcolor', 'colspan', 'height', 'rowspan',
        'valign', 'width',
    ],
    'tr': ['bgcolor', 'valign'],
}


# URL schemes bleach permits in href/src. Explicitly excludes javascript:,
# data:, and vbscript: — all of which are live XSS vectors.
ALLOWED_PROTOCOLS: frozenset[str] = frozenset({'http', 'https', 'mailto'})


# CSS properties we let through in inline `style=""`. Everything else is
# stripped by CSSSanitizer (which also drops url()/expression()/JS-bearing
# values regardless of property name).
_ALLOWED_CSS_PROPERTIES: frozenset[str] = frozenset({
    'background-color',
    'border',
    'border-color',
    'border-spacing',
    'color',
    'font-family',
    'font-size',
    'font-style',
    'font-weight',
    'height',
    'letter-spacing',
    'line-height',
    'margin',
    'margin-bottom',
    'margin-left',
    'margin-right',
    'margin-top',
    'max-height',
    'max-width',
    'min-height',
    'min-width',
    'padding',
    'padding-bottom',
    'padding-left',
    'padding-right',
    'padding-top',
    'text-align',
    'text-decoration',
    'text-transform',
    'vertical-align',
    'width',
})

_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=_ALLOWED_CSS_PROPERTIES)


def sanitize_ebay_html(html: str) -> str:
    """Return a sanitized copy of an eBay description HTML string.

    Preserves the HTML subset that eBay renders and that our description
    templates use. Strips <script>, event-handler attributes (onclick etc.),
    javascript:/data: URLs, and unknown CSS properties.

    Passing ``None`` or a non-string returns an empty string.
    """
    if not html:
        return ''
    if not isinstance(html, str):
        html = str(html)

    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_CSS_SANITIZER,
        strip=True,            # drop disallowed tags entirely rather than escaping
        strip_comments=True,   # no HTML comments (harmless but noisy)
    )
