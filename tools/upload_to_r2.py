#!/usr/bin/env python3
"""
Sam's Collectibles — Upload images to Cloudflare R2

Uploads photos to R2 with proper naming convention and directory structure.
Can also migrate existing ebay_uploads to R2.

Usage:
    # Upload specific photos for a trading card set
    python upload_to_r2.py --sku 101 --category star-wars/anh/series-1 --type 1star photo1.jpg photo2.jpg

    # Upload a poster photo
    python upload_to_r2.py --dest posters/star-wars/ photo.jpg --name sw-anh-style-a-front.jpg

    # Upload comic book photos
    python upload_to_r2.py --dest comic-books/star-wars-marvel/issue-001/ front.jpg back.jpg spine.jpg

    # Migrate entire ebay_uploads directory to R2
    python upload_to_r2.py --migrate-all

    # List what's currently in R2
    python upload_to_r2.py --list trading-cards/star-wars/

    -h, --help    Show this help
"""

import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config

# R2 Configuration — reads from environment or defaults
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID', '1906b346fcf1a6779ee4cdd19a27fc0b')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', 'a71f3baccd32346f41d70494bdb9eab9f7ade7873f62794affc88e2f62c8c103')
R2_ENDPOINT = os.environ.get('R2_ENDPOINT_URL', 'https://c2fa931a6f5d02d3c12552d68c2c379b.r2.cloudflarestorage.com')
BUCKET = 'samscollectibles'
CDN_BASE = 'https://media.samscollectibles.net'

# Content types
CONTENT_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
    '.html': 'text/html',
}


def get_s3_client():
    return boto3.client('s3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def upload_file(s3, local_path, r2_key):
    """Upload a single file to R2."""
    ext = Path(local_path).suffix.lower()
    content_type = CONTENT_TYPES.get(ext, 'application/octet-stream')

    s3.upload_file(
        str(local_path), BUCKET, r2_key,
        ExtraArgs={'ContentType': content_type}
    )
    url = f"{CDN_BASE}/{r2_key}"
    print(f"  ✓ {url}")
    return url


def upload_set_photos(s3, sku, category, star_type, files):
    """Upload photos for a trading card set with proper naming."""
    urls = []
    for i, filepath in enumerate(files, 1):
        ext = Path(filepath).suffix.lower()
        r2_key = f"trading-cards/{category}/{star_type}-{sku}-p{i:02d}{ext}"
        url = upload_file(s3, filepath, r2_key)
        urls.append(url)
    return urls


def upload_to_dest(s3, dest, files, name=None):
    """Upload files to a specific R2 destination path."""
    urls = []
    for filepath in files:
        filename = name or Path(filepath).name
        r2_key = f"{dest.rstrip('/')}/{filename}"
        url = upload_file(s3, filepath, r2_key)
        urls.append(url)
    return urls


def list_objects(s3, prefix):
    """List objects in R2 under a prefix."""
    response = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, MaxKeys=100)
    objects = response.get('Contents', [])
    if not objects:
        print(f"  No objects found under: {prefix}")
        return

    print(f"  {len(objects)} objects under {prefix}:")
    for obj in objects:
        size_kb = obj['Size'] / 1024
        print(f"    {CDN_BASE}/{obj['Key']}  ({size_kb:.1f} KB)")


def migrate_all(s3):
    """Migrate entire ebay_uploads directory to R2."""
    project_root = Path(__file__).parent.parent
    uploads_dir = project_root / 'ebay_uploads'

    if not uploads_dir.exists():
        print(f"ERROR: {uploads_dir} not found")
        return

    uploaded = 0
    for root, dirs, files in os.walk(uploads_dir):
        for filename in files:
            ext = Path(filename).suffix.lower()
            if ext not in CONTENT_TYPES:
                continue

            local_path = Path(root) / filename
            # Convert local path to R2 key
            relative = local_path.relative_to(uploads_dir)
            r2_key = str(relative).replace(' ', '-').lower()
            r2_key = f"ebay-uploads/{r2_key}"

            upload_file(s3, local_path, r2_key)
            uploaded += 1

    print(f"\nMigrated {uploaded} files to R2")


def main():
    parser = argparse.ArgumentParser(
        description="Upload images to Cloudflare R2 for Sam's Collectibles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload trading card set photos
  %(prog)s --sku 101 --category star-wars/anh/series-1 --type 1star photos/*.jpg

  # Upload to a specific R2 path
  %(prog)s --dest posters/star-wars/ poster-front.jpg

  # List R2 contents
  %(prog)s --list trading-cards/star-wars/

  # Migrate all local ebay_uploads to R2
  %(prog)s --migrate-all
        """,
    )

    parser.add_argument('files', nargs='*', help='Image files to upload')
    parser.add_argument('--sku', help='SKU/Custom Label number (e.g., 101)')
    parser.add_argument('--category', help='R2 category path (e.g., star-wars/anh/series-1)')
    parser.add_argument('--type', dest='star_type', help='Star variant type (1star, 2star, mixed, sticker)')
    parser.add_argument('--dest', help='Direct R2 destination path')
    parser.add_argument('--name', help='Override filename for single file upload')
    parser.add_argument('--list', dest='list_prefix', help='List R2 objects under prefix')
    parser.add_argument('--migrate-all', action='store_true', help='Migrate all ebay_uploads to R2')

    args = parser.parse_args()

    s3 = get_s3_client()

    if args.list_prefix:
        list_objects(s3, args.list_prefix)

    elif args.migrate_all:
        migrate_all(s3)

    elif args.sku and args.category and args.star_type and args.files:
        print(f"Uploading {len(args.files)} photos for SKU {args.sku}:")
        upload_set_photos(s3, args.sku, args.category, args.star_type, args.files)

    elif args.dest and args.files:
        print(f"Uploading {len(args.files)} files to {args.dest}:")
        upload_to_dest(s3, args.dest, args.files, args.name)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
