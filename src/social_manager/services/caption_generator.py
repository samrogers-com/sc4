"""Caption generator — Claude Haiku 4.5 drafts of social-media captions.

Takes an EbayListing + platform name and returns a draft `caption` +
`hashtags` + the exact `cost_usd` for this call. Save the result as a
`PostDraft(status='pending')` so Sam can review before publishing.

ANTHROPIC_API_KEY is wired through the Ansible vault → env → container
(see docs/anthropic-api-key-setup.md). The model defaults to Haiku 4.5
per the merged marketing plan (§6): ~$0.36/mo at 50 posts/mo, paid.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import TypedDict

from django.conf import settings

logger = logging.getLogger(__name__)


# Haiku 4.5 pricing — $1/MTok input, $5/MTok output as of 2026-04-18
# (see docs/marketing-automation-plan.md §6). Update if Anthropic changes it.
_PRICING = {
    'claude-haiku-4-5': {'input': Decimal('1'), 'output': Decimal('5')},
    'claude-sonnet-4-6': {'input': Decimal('3'), 'output': Decimal('15')},
    'claude-opus-4-7': {'input': Decimal('5'), 'output': Decimal('25')},
}


class CaptionResult(TypedDict):
    caption: str
    hashtags: list[str]
    cost_usd: Decimal


class CaptionGenerationError(Exception):
    """Raised when the LLM call fails or returns unparseable output."""


def _prompt_for_platform(platform: str) -> str:
    """Platform-specific guidance appended to the system prompt."""
    rules = {
        'instagram': (
            'Instagram Feed post. Caption ≤220 characters. Lead with an '
            'energetic hook — collectors scroll fast. Build excitement about '
            'the era / franchise / scarcity. End with a clear call to action '
            '("link in bio", "DM to grab it"). One emoji max, placed '
            'purposefully. Hashtags go in a separate field, not inside '
            'the caption.'
        ),
        'facebook': (
            'Facebook Group post targeting vintage non-sport collectors. '
            'Caption ≤400 characters. Start with the year + brand + set name '
            'in the first 80 characters. Sound like a fellow collector '
            'sharing a find, but still upbeat — emphasise condition, pack '
            'count, sealed status, or whatever\'s special about this lot. '
            'Always end with a call to action ("link in comments", "DM for '
            'details"). No emojis.'
        ),
        'tiktok': (
            'TikTok caption ≤150 characters. Hook-first, conversational, '
            'punchy — think "⚡ 1977 Star Wars box just hit the store!". '
            'Maximum one emoji. Include a soft CTA ("link in bio"). '
            'Hashtags go in a separate field.'
        ),
        'youtube': (
            'YouTube video title + short description. Title ≤70 characters, '
            'search-friendly (year + brand + set + product type). Then blank '
            'line, then 1–2 sentences that make the viewer want to click — '
            'tease what\'s in the box, why this era matters, or the rarity. '
            'No emojis.'
        ),
        'reddit': (
            'Reddit r/nonsportcards style. Caption ≤300 characters. '
            'Enthusiastic-collector voice — share what\'s cool about this '
            'find (year, sealed status, print run, character lineup). Do NOT '
            'hard-sell or include a price pitch; most subs ban that. No '
            'emojis, no hashtags. Mention condition honestly.'
        ),
        'pinterest': (
            'Pinterest pin description ≤500 characters. SEO-focused but '
            'still engaging — lead sentence has year, brand, set, and '
            'product type; then a sentence or two that makes the collector '
            'click through. Hashtags go in a separate field.'
        ),
    }
    return rules.get(platform.lower(), rules['instagram'])


_SYSTEM_PROMPT = (
    "You are a marketing copywriter for Sam's Collectibles, an eBay store "
    'selling vintage non-sport trading cards, comic books, and movie posters '
    '(1970s–1990s). Sam collected since 1983; his brand is knowledgeable + '
    'enthusiastic + honest. Captions should SELL — build excitement about the '
    "era, scarcity, character lineup, franchise moment, or the collector's "
    'thrill of opening a sealed product from decades ago. Use vivid language. '
    'Always include a call to action.\n\n'
    'Guardrails: never invent grade claims (PSA 10, etc.), set completeness, '
    'or provenance that are not in the listing data. If a listing says '
    '"Factory Sealed", say "factory sealed"; do not upgrade that to "mint" '
    'or "gem mint".\n\n'
    'Return ONLY a JSON object with exactly these keys:\n'
    '  {"caption": "...", "hashtags": ["#tag1", "#tag2", ...]}\n'
    'No prose before or after the JSON. 5–8 hashtags max. The caption must '
    'obey the platform-specific rules below.'
)


def _build_user_message(listing, platform: str, image_url: str = '') -> str:
    """Compose the user message from listing fields. Listing is EbayListing."""
    lines = [
        f'Platform: {platform}',
        '',
        f'Platform rules: {_prompt_for_platform(platform)}',
        '',
        'Listing:',
        f'  Title: {listing.title}',
        f'  SKU: {listing.sku or "(none)"}',
        f'  Price: ${listing.price}',
    ]
    if getattr(listing, 'variant_name', None):
        lines.append(f'  Variant: {listing.variant_name}')
    if getattr(listing, 'category_id', None):
        lines.append(f'  eBay category: {listing.category_id}')
    if getattr(listing, 'ebay_item_id', None):
        lines.append(f'  eBay URL: https://www.ebay.com/itm/{listing.ebay_item_id}')
    if image_url:
        lines.append(f'  Hero image attached at post time: {image_url}')
        lines.append(
            '  (The caption will appear alongside this image — write as if '
            'the reader is already looking at the photo; no need to describe '
            'it in words, but you can reference what they\'re seeing.)'
        )
    return '\n'.join(lines)


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Return USD cost for the call at published per-MTok rates."""
    rates = _PRICING.get(model)
    if not rates:
        logger.warning('No pricing entry for %s; returning 0.0', model)
        return Decimal('0')
    cost_in = (Decimal(input_tokens) / Decimal(1_000_000)) * rates['input']
    cost_out = (Decimal(output_tokens) / Decimal(1_000_000)) * rates['output']
    return (cost_in + cost_out).quantize(Decimal('0.000001'))


def generate_caption(
    listing,
    platform: str,
    model: str = 'claude-haiku-4-5',
    client=None,
    image_url: str = '',
) -> CaptionResult:
    """Generate a draft caption + hashtags for a listing on a given platform.

    Args:
        listing: an `ebay_manager.models.EbayListing` instance.
        platform: one of 'instagram', 'facebook', 'tiktok', 'youtube',
            'reddit', 'pinterest'. Unknown values fall back to Instagram rules.
        model: Anthropic model id. Defaults to the cheap Haiku per the plan.
        client: injectable for testing; production callers omit this.

    Returns:
        CaptionResult dict — `caption`, `hashtags`, `cost_usd`.

    Raises:
        CaptionGenerationError if the API key is missing, the response is not
        valid JSON in the expected shape, or hashtag count is outside 0–12.
    """
    if client is None:
        import anthropic
        api_key = getattr(settings, 'ANTHROPIC_API_KEY', '') or ''
        if not api_key:
            raise CaptionGenerationError(
                'ANTHROPIC_API_KEY is not configured in settings. '
                'Check the Ansible vault mapping.'
            )
        client = anthropic.Anthropic(api_key=api_key)

    user_message = _build_user_message(listing, platform, image_url=image_url)

    response = client.messages.create(
        model=model,
        max_tokens=500,
        system=_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_message}],
    )

    raw = response.content[0].text.strip()

    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise CaptionGenerationError(f'No JSON object in response: {raw[:200]}')
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise CaptionGenerationError(f'Invalid JSON: {exc}; body={raw[:200]}') from exc

    caption = (parsed.get('caption') or '').strip()
    hashtags = parsed.get('hashtags') or []
    if not caption:
        raise CaptionGenerationError(f'Empty caption in response: {raw[:200]}')
    if not isinstance(hashtags, list) or not all(isinstance(h, str) for h in hashtags):
        raise CaptionGenerationError(
            f'hashtags must be a list of strings; got {type(hashtags).__name__}'
        )
    if len(hashtags) > 12:
        raise CaptionGenerationError(
            f'Too many hashtags ({len(hashtags)}); model should return 5–8'
        )
    hashtags = [
        ('#' + h.lstrip('#').strip()) for h in hashtags if h.strip()
    ]

    usage = getattr(response, 'usage', None)
    in_tokens = getattr(usage, 'input_tokens', 0) if usage else 0
    out_tokens = getattr(usage, 'output_tokens', 0) if usage else 0
    cost = _compute_cost(model, in_tokens, out_tokens)

    return CaptionResult(caption=caption, hashtags=hashtags, cost_usd=cost)
