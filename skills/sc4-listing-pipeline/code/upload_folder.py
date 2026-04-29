#!/usr/bin/env python3
"""Mirror a local photo folder to Cloudflare R2.

Given a local directory under `~/Pictures/SC4-Upload/<section>/<franchise>/<slug>/`,
uploads every image (and only images) to the `samscollectibles` R2 bucket
preserving the path 1:1 — i.e. the folder structure becomes the R2 key
prefix. Returns the list of public CDN URLs (one per line on stdout, plus
a JSON summary on stderr if --json is set).

Examples
--------
    # Mirror upload — keys derived from the folder structure
    python upload_folder.py ~/Pictures/SC4-Upload/boxes/marvel/x-men-93-skybox-s2/

    # Custom R2 prefix instead of the auto-mirror
    python upload_folder.py ~/some/folder --prefix boxes/marvel/x-men-93-skybox-s2

    # Dry-run — show what would be uploaded, don't transfer
    python upload_folder.py ~/Pictures/SC4-Upload/sets/marvel/x-men-93-skybox-s2/ --dry-run

Conventions
-----------
* The local path is matched against `~/Pictures/SC4-Upload/`. The portion
  after that becomes the R2 key prefix. Example:
      Local:  ~/Pictures/SC4-Upload/boxes/marvel/x-men-93-skybox-s2/img-001.jpg
      Key:    boxes/marvel/x-men-93-skybox-s2/img-001.jpg
      URL:    https://media.samscollectibles.net/boxes/marvel/x-men-93-skybox-s2/img-001.jpg
* Filenames are NOT renamed; if you have IMG_4781.HEIC, it goes up as that.
* Existing R2 objects are overwritten without prompting — re-runs are
  idempotent.
* Credentials are pulled from 1Password (or R2_* env vars) via
  tools/_r2_creds.py — never hardcoded here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# This skill lives at .../skills/sc4-listing-pipeline/code/upload_folder.py
# Walk up to the SC4 project root, then into tools/ for the creds loader.
SKILL_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SKILL_DIR.parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import boto3  # noqa: E402
from botocore.config import Config  # noqa: E402

from _r2_creds import load as load_r2_creds  # noqa: E402


PHOTO_ROOT = Path.home() / "Pictures" / "SC4-Upload"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
CONTENT_TYPES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
    ".heic": "image/heic",
}


def derive_prefix(folder: Path) -> str:
    """Derive the R2 key prefix from the folder location.

    If `folder` is under `~/Pictures/SC4-Upload/`, the relative path is used
    verbatim. Otherwise we fall back to the folder's basename and require
    the caller to pass --prefix explicitly.
    """
    folder = folder.resolve()
    try:
        rel = folder.relative_to(PHOTO_ROOT.resolve())
        return str(rel).replace("\\", "/")
    except ValueError:
        raise SystemExit(
            f"Folder {folder} is not under {PHOTO_ROOT}.\n"
            "Pass --prefix to set the R2 prefix manually."
        )


def collect_images(folder: Path) -> list[Path]:
    """Return sorted list of image files directly inside `folder`."""
    if not folder.is_dir():
        raise SystemExit(f"Not a directory: {folder}")
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    if not files:
        raise SystemExit(f"No image files found in {folder}")
    return files


def make_client(creds):
    return boto3.client(
        "s3",
        endpoint_url=creds.endpoint,
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_one(s3, creds, local: Path, key: str) -> str:
    content_type = CONTENT_TYPES.get(local.suffix.lower(), "application/octet-stream")
    s3.upload_file(
        str(local), creds.bucket, key,
        ExtraArgs={
            "ContentType": content_type,
            "CacheControl": "public, max-age=31536000",
        },
    )
    return f"{creds.cdn_base}/{key}"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(__doc__.split("\n\n")[1:]),
    )
    ap.add_argument("folder", help="Local folder to upload (e.g. ~/Pictures/SC4-Upload/boxes/marvel/x-men-93-skybox-s2/)")
    ap.add_argument("--prefix", help="Override the R2 key prefix (default: derived from path under ~/Pictures/SC4-Upload/)")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without transferring")
    ap.add_argument("--json", action="store_true", help="Emit a machine-readable summary on stdout instead of one URL per line")
    args = ap.parse_args()

    folder = Path(args.folder).expanduser()
    files = collect_images(folder)
    prefix = args.prefix.strip("/") if args.prefix else derive_prefix(folder)

    plan = [(f, f"{prefix}/{f.name}") for f in files]

    if args.dry_run:
        print(f"# Would upload {len(plan)} files to bucket samscollectibles:", file=sys.stderr)
        for local, key in plan:
            print(f"  {local}  →  {key}", file=sys.stderr)
        return 0

    creds = load_r2_creds()
    s3 = make_client(creds)

    print(f"# Uploading {len(plan)} files to {creds.bucket}/{prefix}/ ...", file=sys.stderr)
    urls: list[str] = []
    for i, (local, key) in enumerate(plan, 1):
        url = upload_one(s3, creds, local, key)
        urls.append(url)
        print(f"# [{i}/{len(plan)}] {local.name} → {url}", file=sys.stderr)

    if args.json:
        json.dump({"prefix": prefix, "count": len(urls), "urls": urls},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for u in urls:
            print(u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
