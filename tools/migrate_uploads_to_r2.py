#!/usr/bin/env python3
"""
Sam's Collectibles -- Migrate ebay_uploads to Cloudflare R2

Scans the local ebay_uploads/ directory and uploads all images to R2
with proper path mapping:

    ebay_uploads/NS-Boxes/Star Wars/...   -> trading-cards/boxes/star-wars/...
    ebay_uploads/NS-Packs/...             -> trading-cards/packs/...
    ebay_uploads/NS-cvs-sets/...          -> trading-cards/sets/...
    ebay_uploads/NS-Singles/...           -> trading-cards/singles/...
    ebay_uploads/NS-Binders/...           -> trading-cards/binders/...
    ebay_uploads/ns_cards/...             -> trading-cards/...
    ebay_uploads/Posters/...              -> posters/...
    ebay_uploads/Comics-SW-Marvel/...     -> comic-books/star-wars-marvel/...
    ebay_uploads/Comics-SW-DarkHorse/...  -> comic-books/star-wars-darkhorse/...
    ebay_uploads/Comics-Other/...         -> comic-books/other/...

Usage:
    # Dry run (show what would be uploaded)
    python tools/migrate_uploads_to_r2.py --dry-run

    # Run migration
    python tools/migrate_uploads_to_r2.py

    # Custom delay between uploads
    python tools/migrate_uploads_to_r2.py --delay 1.0
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import boto3
from botocore.config import Config

# ---------------------------------------------------------------------------
# R2 Configuration
# ---------------------------------------------------------------------------
R2_ACCESS_KEY = os.environ.get(
    'R2_ACCESS_KEY_ID', '1906b346fcf1a6779ee4cdd19a27fc0b')
R2_SECRET_KEY = os.environ.get(
    'R2_SECRET_ACCESS_KEY',
    'a71f3baccd32346f41d70494bdb9eab9f7ade7873f62794affc88e2f62c8c103')
R2_ENDPOINT = os.environ.get(
    'R2_ENDPOINT_URL',
    'https://c2fa931a6f5d02d3c12552d68c2c379b.r2.cloudflarestorage.com')
BUCKET = 'samscollectibles'
CDN_BASE = 'https://media.samscollectibles.net'

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

CONTENT_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}

# ---------------------------------------------------------------------------
# Directory mapping: local prefix -> R2 prefix
# ---------------------------------------------------------------------------
# Order matters: more specific prefixes first
DIR_MAPPINGS = [
    ('NS-Boxes',            'trading-cards/boxes'),
    ('NS-Packs',            'trading-cards/packs'),
    ('NS-cvs-sets',         'trading-cards/sets'),
    ('NS-Singles',          'trading-cards/singles'),
    ('NS-Binders',          'trading-cards/binders'),
    ('ns_cards/box',        'trading-cards/boxes'),
    ('ns_cards/sets',       'trading-cards/sets'),
    ('ns_cards',            'trading-cards'),
    ('Posters',             'posters'),
    ('Comics-SW-Marvel',    'comic-books/star-wars-marvel'),
    ('Comics-SW-DarkHorse', 'comic-books/star-wars-darkhorse'),
    ('Comics-Other',        'comic-books/other'),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
UPLOADS_DIR = PROJECT_ROOT / 'ebay_uploads'
LOG_FILE = Path(__file__).parent / 'migration_log.txt'


def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def sanitize_path(path_str):
    """Lowercase, replace spaces/underscores with dashes, collapse dashes."""
    result = path_str.lower()
    result = result.replace(' ', '-')
    result = result.replace('_', '-')
    # Collapse multiple dashes
    while '--' in result:
        result = result.replace('--', '-')
    return result


def map_local_to_r2(local_path):
    """
    Map a local file path (relative to ebay_uploads/) to an R2 key.

    Returns the R2 key string, or None if unmapped.
    """
    relative = local_path.relative_to(UPLOADS_DIR)
    relative_str = str(relative)

    for local_prefix, r2_prefix in DIR_MAPPINGS:
        if relative_str.startswith(local_prefix):
            # Get the remainder after the matched prefix
            remainder = relative_str[len(local_prefix):]
            if remainder.startswith('/') or remainder.startswith(os.sep):
                remainder = remainder[1:]
            elif remainder:
                # Prefix didn't match at a boundary
                continue

            # Sanitize the remainder path
            remainder = sanitize_path(remainder)
            if remainder:
                r2_key = f"{r2_prefix}/{remainder}"
            else:
                r2_key = r2_prefix
            return r2_key

    # Fallback: use original relative path under ebay-uploads/
    return f"ebay-uploads/{sanitize_path(str(relative))}"


def upload_file(s3, local_path, r2_key, dry_run=False):
    """Upload a single file to R2."""
    ext = Path(local_path).suffix.lower()
    content_type = CONTENT_TYPES.get(ext, 'application/octet-stream')
    url = f"{CDN_BASE}/{r2_key}"

    if dry_run:
        print(f"  [DRY RUN] {local_path.name} -> {r2_key}")
        return url

    s3.upload_file(
        str(local_path), BUCKET, r2_key,
        ExtraArgs={'ContentType': content_type}
    )
    print(f"  -> {url}")
    return url


def run_migration(dry_run=False, delay=0.5):
    """Run the full migration."""
    if not UPLOADS_DIR.exists():
        print(f"ERROR: {UPLOADS_DIR} not found")
        sys.exit(1)

    print(f"{'='*60}")
    print(f"Sam's Collectibles -- Migrate ebay_uploads to R2")
    print(f"{'='*60}")
    print(f"Source: {UPLOADS_DIR}")
    print(f"Bucket: {BUCKET}")
    print(f"CDN:    {CDN_BASE}")
    if dry_run:
        print(f"** DRY RUN -- no files will be uploaded **")
    print(f"{'='*60}")
    print()

    s3 = None if dry_run else get_s3_client()

    # Collect all image files
    all_files = []
    for root, dirs, files in os.walk(UPLOADS_DIR):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in sorted(files):
            if filename.startswith('.'):
                continue
            filepath = Path(root) / filename
            if filepath.suffix.lower() in IMAGE_EXTENSIONS:
                all_files.append(filepath)

    total = len(all_files)
    print(f"Found {total} image files to migrate\n")

    uploaded = 0
    skipped = 0
    errors = 0
    log_entries = []
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for i, filepath in enumerate(all_files, 1):
        try:
            r2_key = map_local_to_r2(filepath)
            if r2_key is None:
                print(f"  [SKIP] No mapping for: {filepath}")
                skipped += 1
                log_entries.append(f"{timestamp}  SKIP  {filepath}")
                continue

            print(f"[{i}/{total}] {filepath.relative_to(UPLOADS_DIR)}")
            url = upload_file(s3, filepath, r2_key, dry_run=dry_run)
            uploaded += 1
            log_entries.append(f"{timestamp}  OK    {filepath}  ->  {r2_key}")

            if delay > 0 and not dry_run:
                time.sleep(delay)

        except Exception as e:
            print(f"  [ERROR] {filepath}: {e}")
            errors += 1
            log_entries.append(f"{timestamp}  ERROR {filepath}  {e}")

    # Write log file
    if not dry_run:
        with open(LOG_FILE, 'a') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Migration run: {timestamp}\n")
            f.write(f"{'='*60}\n")
            for entry in log_entries:
                f.write(entry + '\n')
            f.write(f"\nSummary: {uploaded} uploaded, "
                    f"{skipped} skipped, {errors} errors\n")
        print(f"\nLog written to: {LOG_FILE}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Migration {'(DRY RUN) ' if dry_run else ''}Summary")
    print(f"{'='*60}")
    print(f"  Total files found: {total}")
    print(f"  Uploaded:          {uploaded}")
    print(f"  Skipped:           {skipped}")
    print(f"  Errors:            {errors}")
    print(f"{'='*60}")

    return uploaded, skipped, errors


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Migrate ebay_uploads/ images to Cloudflare R2")
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be uploaded without uploading')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay between uploads in seconds (default: 0.5)')
    args = parser.parse_args()

    run_migration(dry_run=args.dry_run, delay=args.delay)


if __name__ == '__main__':
    main()
