"""eBay Taxonomy API — fetch item aspects (item specifics) for a category.

eBay's Item Aspects API returns the full schema of item specifics that a
seller can or must populate for a given category. Required aspects fail
the listing if missing; recommended aspects boost search visibility but
won't block publish.

Categories Sam's Collectibles uses (per `feedback_preferences.md`):
- 261035  Sealed Trading Card Boxes
- 183052  Trading Card Sets
- 183050  Trading Card Singles
- 183053  Sealed Trading Card Packs
- 183054  Wrappers & Empty Card Boxes
- 183051  Trading Card Lots
- 183059  Card Albums, Binders & Pages

API docs:
https://developer.ebay.com/api-docs/commerce/taxonomy/resources/category_tree/methods/getItemAspectsForCategory

Auth: requires the **App** OAuth token (Client Credentials), not the
User token. The Browse API uses the same token, so `get_app_token()`
from `api_client` is what we want.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import requests

from .api_client import get_app_token

CATEGORY_TREE_ID_US = "0"  # eBay US marketplace
ASPECTS_URL = (
    "https://api.ebay.com/commerce/taxonomy/v1/category_tree/{tree_id}"
    "/get_item_aspects_for_category"
)

# Cache aspects to disk for 7 days — eBay rarely changes them and we'd
# rather not hit the API for every listing.
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "ebay_aspect_cache"
CACHE_TTL_SECONDS = 7 * 24 * 3600


@dataclass
class Aspect:
    """One item aspect (item specific) eBay accepts for a category.

    Attributes:
        name: Display name eBay shows the seller (e.g. "Manufacturer").
        required: True if eBay rejects the listing without this aspect.
        mode: "FREE_TEXT" (any value) or "SELECTION_ONLY" (must pick from values).
        max_values: Max distinct values the seller can submit for this aspect.
        sample_values: First N values from eBay's suggestion list (for prompts).
        all_values: Full value list (rarely needed; can be huge).
        applicable_to_variations: True if this can vary across variant listings.
        cardinality: "SINGLE" (one value) or "MULTI" (multiple comma-separated).
    """
    name: str
    required: bool
    mode: str  # FREE_TEXT | SELECTION_ONLY
    max_values: int = 1
    sample_values: list[str] = field(default_factory=list)
    all_values: list[str] = field(default_factory=list)
    applicable_to_variations: bool = False
    cardinality: str = "SINGLE"


def _cache_path(category_id: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"category_{category_id}.json"


def _read_cache(category_id: str) -> list[dict] | None:
    p = _cache_path(category_id)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - payload.get("fetched_at", 0) > CACHE_TTL_SECONDS:
        return None
    return payload.get("aspects")


def _write_cache(category_id: str, aspects: list[dict]) -> None:
    try:
        _cache_path(category_id).write_text(json.dumps({
            "fetched_at": time.time(),
            "category_id": category_id,
            "aspects": aspects,
        }))
    except OSError:
        pass  # Cache failure is non-fatal


def get_item_aspects(category_id: str, *, sample_n: int = 8,
                     use_cache: bool = True) -> list[Aspect]:
    """Return all aspects (item specifics) eBay accepts for a category.

    Args:
        category_id: Numeric eBay leaf category, e.g. "261035".
        sample_n: How many sample values to surface per aspect (for prompts).
            Set to a larger number if you need full enumerations.
        use_cache: Honor the 7-day disk cache. Set False to force-refresh.

    Returns:
        List of `Aspect` dataclasses. Required aspects come first; remaining
        aspects preserve eBay's order (which roughly corresponds to UI prominence).

    Raises:
        RuntimeError: If the App OAuth token is missing or the API errors.
    """
    raw = _read_cache(category_id) if use_cache else None
    if raw is None:
        token = get_app_token()
        if not token:
            raise RuntimeError(
                "eBay App OAuth token unavailable — set EBAY_APP_ID and "
                "EBAY_CERT_ID env vars (in .env.production) so api_client."
                "get_app_token() can fetch a Client Credentials token."
            )
        url = ASPECTS_URL.format(tree_id=CATEGORY_TREE_ID_US)
        resp = requests.get(
            url,
            params={"category_id": category_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"eBay Taxonomy API returned {resp.status_code} for "
                f"category {category_id}: {resp.text[:300]}"
            )
        raw = resp.json().get("aspects", [])
        _write_cache(category_id, raw)

    out: list[Aspect] = []
    for a in raw:
        constraint = a.get("aspectConstraint", {})
        values = a.get("aspectValues", []) or []
        out.append(Aspect(
            name=a.get("localizedAspectName", ""),
            required=bool(constraint.get("aspectRequired", False)),
            mode=constraint.get("aspectMode", "FREE_TEXT"),
            max_values=int(constraint.get("aspectMaxLength", 1) or 1),
            sample_values=[v["localizedValue"] for v in values[:sample_n]],
            all_values=[v["localizedValue"] for v in values],
            applicable_to_variations=bool(constraint.get(
                "aspectApplicableTo", []) and "PRODUCT" not in (
                constraint.get("aspectApplicableTo", []))),
            cardinality=constraint.get("itemToAspectCardinality", "SINGLE"),
        ))
    # Required first, otherwise preserve eBay's order
    out.sort(key=lambda x: (not x.required, 0))
    return out


def split_required_optional(aspects: Iterable[Aspect]
                             ) -> tuple[list[Aspect], list[Aspect]]:
    """Convenience: split into (required, optional) lists."""
    required, optional = [], []
    for a in aspects:
        (required if a.required else optional).append(a)
    return required, optional


def auto_fill_known(aspects: Iterable[Aspect], known: dict[str, str]
                     ) -> tuple[dict[str, str], list[Aspect]]:
    """Pre-fill any aspect we already have a value for; return remainder.

    Args:
        aspects: Output of `get_item_aspects(...)`.
        known: Dict of values we've already gathered, keyed by the same
            aspect name eBay returns (e.g. "Manufacturer", "Year Manufactured").

    Returns:
        (filled, unfilled) where `filled` is a dict ready to attach to
        EbayListing.item_specifics, and `unfilled` is the list of aspects
        the caller still needs to gather (typically via AskUserQuestion).
    """
    filled: dict[str, str] = {}
    unfilled: list[Aspect] = []
    for a in aspects:
        if a.name in known and known[a.name]:
            filled[a.name] = known[a.name]
        else:
            unfilled.append(a)
    return filled, unfilled
