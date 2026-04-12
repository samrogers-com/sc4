#!/usr/bin/env python3
"""
Sam's Collectibles -- Test R2 setup

Validates that:
1. R2 credentials work (can list bucket)
2. Migration uploaded files correctly (spot checks)
3. CDN URLs resolve (curl check)
4. Watcher path resolution logic works

Usage:
    python tools/test_r2_setup.py
"""

import os
import subprocess
import sys
import tempfile
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


def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def test_r2_connection():
    """Test that R2 credentials work."""
    print("Test 1: R2 connection")
    try:
        s3 = get_s3_client()
        resp = s3.list_objects_v2(Bucket=BUCKET, MaxKeys=1)
        count = resp.get('KeyCount', 0)
        print(f"  PASS - Connected to bucket '{BUCKET}', "
              f"found {count} object(s) in sample")
        return s3
    except Exception as e:
        print(f"  FAIL - {e}")
        return None


def test_list_prefixes(s3):
    """List objects under key prefixes to verify migration."""
    print("\nTest 2: List R2 contents by prefix")
    prefixes = [
        'trading-cards/boxes/',
        'trading-cards/sets/',
        'trading-cards/singles/',
        'posters/',
        'comic-books/',
    ]
    for prefix in prefixes:
        try:
            resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, MaxKeys=10)
            count = resp.get('KeyCount', 0)
            objects = resp.get('Contents', [])
            print(f"  {prefix:40s} -> {count} objects")
            for obj in objects[:3]:
                size_kb = obj['Size'] / 1024
                print(f"    {obj['Key']}  ({size_kb:.1f} KB)")
        except Exception as e:
            print(f"  {prefix} -> ERROR: {e}")


def test_cdn_urls(s3):
    """Check a few CDN URLs are accessible."""
    print("\nTest 3: CDN URL accessibility")
    resp = s3.list_objects_v2(Bucket=BUCKET, MaxKeys=5)
    objects = resp.get('Contents', [])

    if not objects:
        print("  SKIP - No objects found in bucket")
        return

    for obj in objects[:3]:
        url = f"{CDN_BASE}/{obj['Key']}"
        try:
            result = subprocess.run(
                ['curl', '-sI', '-o', '/dev/null', '-w', '%{http_code}', url],
                capture_output=True, text=True, timeout=10
            )
            status = result.stdout.strip()
            if status == '200':
                print(f"  PASS - {url} -> HTTP {status}")
            else:
                print(f"  WARN - {url} -> HTTP {status}")
        except Exception as e:
            print(f"  FAIL - {url} -> {e}")


def test_watcher_path_resolution():
    """Test that the watcher resolves paths correctly."""
    print("\nTest 4: Watcher path resolution")
    # Import the watcher's resolve function
    sys.path.insert(0, str(Path(__file__).parent))
    from r2_watcher import resolve_r2_key

    with tempfile.TemporaryDirectory() as tmpdir:
        watch_root = Path(tmpdir)

        # Create test directory structure
        test_cases = [
            (
                'star-wars/anh/series-1/1star-101/IMG_001.jpg',
                'trading-cards/star-wars/anh/series-1/1star-101-p01.jpg'
            ),
            (
                'posters/star-wars/sw-poster.jpg',
                'posters/star-wars/sw-poster.jpg'
            ),
            (
                'comic-books/marvel/issue-001/cover.jpg',
                'comic-books/marvel/issue-001/cover.jpg'
            ),
        ]

        for rel_path, expected_key in test_cases:
            filepath = watch_root / rel_path
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(b'\xff\xd8\xff')  # minimal JPEG header

            actual_key = resolve_r2_key(filepath, watch_root)
            status = "PASS" if actual_key == expected_key else "FAIL"
            print(f"  {status} - {rel_path}")
            if status == "FAIL":
                print(f"         Expected: {expected_key}")
                print(f"         Got:      {actual_key}")


def test_watcher_dry_run():
    """Test watcher in --once --dry-run mode."""
    print("\nTest 5: Watcher dry-run mode")
    with tempfile.TemporaryDirectory() as tmpdir:
        watch_root = Path(tmpdir)
        test_dir = watch_root / 'star-wars' / 'anh' / 'series-1' / '1star-101'
        test_dir.mkdir(parents=True)

        # Create a test image
        test_file = test_dir / 'test-image.jpg'
        test_file.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)

        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).parent / 'r2_watcher.py'),
                 '--once', '--dry-run', str(watch_root)],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and 'DRY RUN' in result.stdout:
                print(f"  PASS - Watcher dry-run completed")
                # Show relevant output
                for line in result.stdout.strip().split('\n'):
                    if 'DRY RUN' in line or 'Uploaded' in line or 'Done' in line:
                        print(f"    {line.strip()}")
            else:
                print(f"  FAIL - Return code: {result.returncode}")
                if result.stderr:
                    print(f"    stderr: {result.stderr[:200]}")
        except Exception as e:
            print(f"  FAIL - {e}")


def main():
    print("=" * 60)
    print("Sam's Collectibles -- R2 Setup Test")
    print("=" * 60)

    s3 = test_r2_connection()
    if s3:
        test_list_prefixes(s3)
        test_cdn_urls(s3)

    test_watcher_path_resolution()
    test_watcher_dry_run()

    print("\n" + "=" * 60)
    print("Test suite complete")
    print("=" * 60)


if __name__ == '__main__':
    main()
