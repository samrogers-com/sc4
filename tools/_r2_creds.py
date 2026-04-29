"""Shared R2 credential resolution for Sam's Collectibles tools.

Credentials are stored in 1Password under:
    op://sams.collectibles/Cloudflare R2 - samscollectibles/{field}

Resolution order:
    1. R2_* / R2_BUCKET / R2_CDN_BASE environment variables — if all
       required ones are present (useful for CI or `op run` wrappers).
    2. 1Password CLI via `op read` — if `op` is on PATH and signed in.
    3. Hard fail with a helpful message.

Nothing in this module — or anything that imports it — should ever
contain a credential in plaintext. If you find one, that's a bug.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

OP_ITEM = "op://sams.collectibles/Cloudflare R2 - samscollectibles"
OP_FIELDS = {
    "access_key": "username",
    "secret":     "credential",
    "endpoint":   "endpoint",
    "bucket":     "bucket",
    "cdn_base":   "cdn_base",
}


@dataclass(frozen=True)
class R2Creds:
    access_key: str
    secret: str
    endpoint: str
    bucket: str
    cdn_base: str


class R2CredsUnavailable(RuntimeError):
    """Raised when no resolution path produces a complete credential set."""


def _from_env() -> R2Creds | None:
    access = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    endpoint = os.environ.get("R2_ENDPOINT_URL")
    if not (access and secret and endpoint):
        return None
    return R2Creds(
        access_key=access,
        secret=secret,
        endpoint=endpoint,
        bucket=os.environ.get("R2_BUCKET", "samscollectibles"),
        cdn_base=os.environ.get(
            "R2_CDN_BASE", "https://media.samscollectibles.net"
        ).rstrip("/"),
    )


def _from_1password() -> R2Creds:
    """Pull all 5 creds with a single `op inject` call (= one auth prompt).

    `op inject` takes a template from stdin and substitutes every
    `{{ op://... }}` reference in one go. That's a 5x reduction in
    biometric/password prompts versus calling `op read` per-field.
    Falls back to per-field `op read` only if `op inject` itself fails
    for some unexpected reason.
    """
    if not shutil.which("op"):
        raise R2CredsUnavailable(
            "1Password CLI (`op`) not found on PATH and R2_* env vars are "
            "not set.\nInstall via `brew install --cask 1password-cli`, "
            "enable the Developer → CLI integration in the desktop app, or "
            "export R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / "
            "R2_ENDPOINT_URL."
        )

    # Build a key=value template so we get all five secrets back in one
    # response. R2 access keys, secrets, URLs, and bucket names never
    # contain newlines, so newline-delimited is safe and trivial to parse.
    template_lines = [
        f"{slot}={{{{ {OP_ITEM}/{field} }}}}"
        for slot, field in OP_FIELDS.items()
    ]
    template = "\n".join(template_lines) + "\n"

    try:
        res = subprocess.run(
            ["op", "inject"],
            input=template,
            capture_output=True, text=True, timeout=20, check=True,
        )
    except subprocess.CalledProcessError as e:
        # `op inject` fails on the whole template if any one ref is bad.
        # The error message points at the offending reference, so we
        # don't need to fall back to per-field reads — surface it.
        raise R2CredsUnavailable(
            f"Failed to resolve R2 credentials from 1Password.\n"
            f"  → {e.stderr.strip() or e}\n"
            "Make sure the 1Password desktop app is unlocked, the CLI "
            "integration is enabled (Settings → Developer), and the item "
            f"'{OP_ITEM}' exists in the sams.collectibles vault."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise R2CredsUnavailable(
            "Timed out resolving R2 credentials from 1Password (20s).\n"
            "Unlock the desktop app and try again."
        ) from e

    out: dict[str, str] = {}
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()

    missing = [k for k in OP_FIELDS if k not in out or not out[k]]
    if missing:
        raise R2CredsUnavailable(
            f"`op inject` returned but these fields are empty: {', '.join(missing)}.\n"
            f"Check the item '{OP_ITEM}' in 1Password — fields may have been renamed."
        )

    return R2Creds(
        access_key=out["access_key"],
        secret=out["secret"],
        endpoint=out["endpoint"],
        bucket=out["bucket"],
        cdn_base=out["cdn_base"].rstrip("/"),
    )


def load() -> R2Creds:
    """Return a complete R2Creds, raising R2CredsUnavailable on failure."""
    creds = _from_env()
    if creds:
        return creds
    return _from_1password()
