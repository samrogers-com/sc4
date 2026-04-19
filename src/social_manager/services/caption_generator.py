"""Caption generator placeholder.

Planned to call Claude Haiku 4.5 (ANTHROPIC_API_KEY is already wired through the
Ansible vault → env → container). Real implementation lands in a follow-up PR; for
the Phase-2 skeleton we only define the interface so views / admin actions can
import it.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TypedDict


class CaptionResult(TypedDict):
    caption: str
    hashtags: list[str]
    cost_usd: Decimal


def generate_caption(listing, platform: str, model: str = 'claude-haiku-4-5') -> CaptionResult:
    """Generate a draft caption + hashtags for a listing on a given platform.

    Returns a dict with `caption`, `hashtags`, and `cost_usd`. Saved by the caller
    as a `PostDraft(status='pending')` for Sam's review.

    Not yet implemented — this module exists so other code can `from
    social_manager.services.caption_generator import generate_caption` now.
    The actual Anthropic call lands after the Phase-2 app is deployed and the
    caller integration is wired up.
    """
    raise NotImplementedError(
        'generate_caption is a Phase-2 placeholder. '
        'Implementation pending; see docs/marketing-automation-plan.md §6.'
    )
