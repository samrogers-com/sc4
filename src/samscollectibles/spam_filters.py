"""Anti-spam helpers for the public contact form.

Ported from bassethoundbooks/aboutus/views.py (where these layers cut form
spam from ~12/day to zero) with one extension: the random-gibberish filter
catches XRumer/SpamBot submissions whose body is a single 20-30 char
lowercase blob with no whitespace (e.g. ``oyvuzqzzokephomneldtumjjrdnzor``).

Layered defenses, applied in this order in the view:
    1. Honeypot ``website`` field — bots auto-fill, humans don't see it
    2. Rate limit — 3 submissions per IP per 5 min via Django cache
    3. Cloudflare Turnstile — server-verified token (skipped if not configured)
    4. Content filter — silent drop on known signatures + gibberish heuristic
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
RATE_LIMIT_MAX = 3
RATE_LIMIT_WINDOW = 300  # seconds (5 min)


def get_client_ip(request) -> str:
    """Real client IP, respecting X-Forwarded-For from Cloudflare/Nginx."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def is_rate_limited(ip: str) -> bool:
    """Return True if this IP has exceeded the submission limit."""
    cache_key = f'sc4_contact_rl_{ip}'
    submissions = cache.get(cache_key, [])
    now = time.time()
    recent = [ts for ts in submissions if now - ts < RATE_LIMIT_WINDOW]
    if len(recent) >= RATE_LIMIT_MAX:
        return True
    recent.append(now)
    cache.set(cache_key, recent, RATE_LIMIT_WINDOW)
    return False


# ---------------------------------------------------------------------------
# Content filter — silent drop, never tell the bot why
# ---------------------------------------------------------------------------
# Site audience is English-speaking US collectors. Submissions whose body has
# no Latin letters at all are almost always XRumer/GSA bot traffic.
_SPAM_PHRASES = (
    'qiymət',           # Azerbaijani "price" (BHB pattern)
    'bilmək istədim',   # Azerbaijani "I wanted to know"
    'price for reseller',
    'writing about your the prices',
)
_SPAM_NAMES = ('robertgog',)


def _is_random_gibberish(text: str) -> bool:
    """Heuristic: a long-ish string with no whitespace and no punctuation
    is almost certainly bot-generated random characters.

    Real human messages have spaces between words. This catches the
    'oyvuzqzzokephomneldtumjjrdnzor' / 'rtiewngszp' patterns currently
    pounding the sc4 form without false-positiving short greetings.
    """
    s = (text or '').strip()
    if len(s) < 15:
        return False
    # Any whitespace at all = real word boundaries
    if re.search(r'\s', s):
        return False
    # Any punctuation that suggests structured content
    if re.search(r"[.!?,@:;'\"\-/]", s):
        return False
    return True


def is_spam_content(name: str, subject: str, message: str) -> bool:
    """Return True if the submission matches a known spam signature.

    Caller should silently render success when this trips so bots don't
    learn which signatures are detected.
    """
    body = f'{subject}\n{message}'
    lowered_body = body.lower()
    lowered_name = (name or '').lower()

    if any(pattern in lowered_name for pattern in _SPAM_NAMES):
        return True
    if any(phrase in lowered_body for phrase in _SPAM_PHRASES):
        return True
    # Reject body with no Latin letters at all (foreign-script bots)
    if message and not re.search(r'[A-Za-z]', message):
        return True
    # Reject absurdly short messages — real inquiries are >10 chars
    if message and len(message.strip()) < 10:
        return True
    # Reject random-string spam (no spaces, no punctuation, ≥15 chars)
    if _is_random_gibberish(message) or _is_random_gibberish(name):
        return True
    return False


# ---------------------------------------------------------------------------
# Cloudflare Turnstile — fail open if Cloudflare is unreachable
# ---------------------------------------------------------------------------
def verify_turnstile(token: str, ip: str) -> bool:
    """Verify a Turnstile token. Returns True if valid OR if Turnstile is unconfigured."""
    secret = getattr(settings, 'TURNSTILE_SECRET_KEY', '')
    if not secret:
        return True
    try:
        data = (
            f'secret={secret}&response={token}&remoteip={ip}'
        ).encode()
        req = urllib.request.Request(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data=data,
            method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            return result.get('success', False)
    except Exception:
        logger.exception('Turnstile verification failed — allowing submission')
        return True  # fail open
