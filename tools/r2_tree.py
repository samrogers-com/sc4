#!/usr/bin/env python3
"""
Sam's Collectibles — R2 Bucket Tree Viewer

Shows all folders and files in the R2 bucket as an indented tree,
similar to the Unix `tree` command.

Usage:
    python3 tools/r2_tree.py                    # Full tree
    python3 tools/r2_tree.py trading-cards/     # Subtree
    python3 tools/r2_tree.py --files-only       # Only show files, not empty dirs
    python3 tools/r2_tree.py --summary          # Just folder counts, no files
    python3 tools/r2_tree.py --json             # JSON output
    python3 tools/r2_tree.py --depth 2          # Limit depth
"""

import argparse
import json
import os
import sys

import boto3
from botocore.config import Config

R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID', '1906b346fcf1a6779ee4cdd19a27fc0b')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', 'a71f3baccd32346f41d70494bdb9eab9f7ade7873f62794affc88e2f62c8c103')
R2_ENDPOINT = os.environ.get('R2_ENDPOINT_URL', 'https://c2fa931a6f5d02d3c12552d68c2c379b.r2.cloudflarestorage.com')
BUCKET = 'samscollectibles'
CDN_BASE = 'https://media.samscollectibles.net'


def get_all_objects(prefix=''):
    s3 = boto3.client('s3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )
    all_objects = []
    continuation = None
    while True:
        kwargs = {'Bucket': BUCKET, 'MaxKeys': 1000}
        if prefix:
            kwargs['Prefix'] = prefix
        if continuation:
            kwargs['ContinuationToken'] = continuation
        resp = s3.list_objects_v2(**kwargs)
        all_objects.extend(resp.get('Contents', []))
        if not resp.get('IsTruncated'):
            break
        continuation = resp.get('NextContinuationToken')
    return all_objects


def build_tree(objects):
    tree = {}
    for obj in objects:
        parts = obj['Key'].split('/')
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Leaf node — store size
                current[part] = {'__size__': obj['Size']}
            else:
                current = current.setdefault(part, {})
    return tree


def format_size(size_bytes):
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f}MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f}KB"
    else:
        return f"{size_bytes}B"


def count_files(node):
    count = 0
    total_size = 0
    for key, val in node.items():
        if key == '__size__':
            continue
        if '__size__' in val:
            count += 1
            total_size += val['__size__']
        else:
            c, s = count_files(val)
            count += c
            total_size += s
    return count, total_size


def print_tree(node, prefix='', depth=0, max_depth=None, summary=False):
    if max_depth is not None and depth >= max_depth:
        fc, fs = count_files(node)
        if fc > 0:
            print(f"{prefix}... ({fc} files, {format_size(fs)})")
        return

    # Separate directories and files
    dirs = {}
    files = {}
    for key, val in sorted(node.items()):
        if key == '__size__':
            continue
        if '__size__' in val and len(val) == 1:
            files[key] = val['__size__']
        else:
            dirs[key] = val

    items = list(dirs.items()) + ([] if summary else list(files.items()))

    for i, (name, val) in enumerate(items):
        is_last = (i == len(items) - 1)
        connector = '└── ' if is_last else '├── '
        extension = '    ' if is_last else '│   '

        if name in dirs:
            fc, fs = count_files(val)
            size_info = f" ({fc} files, {format_size(fs)})" if fc > 0 else ""
            print(f"{prefix}{connector}{name}/{size_info}")
            print_tree(val, prefix + extension, depth + 1, max_depth, summary)
        else:
            # File
            print(f"{prefix}{connector}{name} ({format_size(val)})")


def main():
    parser = argparse.ArgumentParser(
        description="R2 bucket tree viewer — like `tree` for Cloudflare R2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Full tree of entire bucket
  %(prog)s trading-cards/boxes/     Just the boxes subtree
  %(prog)s --summary                Folders only, no individual files
  %(prog)s --depth 2                Limit to 2 levels deep
  %(prog)s --json                   JSON output
  %(prog)s posters/ --depth 1       Quick overview of posters
        """,
    )
    parser.add_argument('prefix', nargs='?', default='', help='R2 prefix/path to list (default: entire bucket)')
    parser.add_argument('--summary', action='store_true', help='Show only folders with file counts, not individual files')
    parser.add_argument('--depth', type=int, default=None, help='Max depth to display')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    objects = get_all_objects(args.prefix)

    if not objects:
        print(f"No objects found under: {args.prefix or '(root)'}")
        return

    tree = build_tree(objects)
    total_files = len(objects)
    total_size = sum(o['Size'] for o in objects)

    if args.json:
        # For JSON, build a cleaner structure
        def clean_tree(node):
            result = {}
            for key, val in sorted(node.items()):
                if key == '__size__':
                    continue
                if '__size__' in val and len(val) == 1:
                    result[key] = format_size(val['__size__'])
                else:
                    result[key] = clean_tree(val)
            return result
        print(json.dumps(clean_tree(tree), indent=2))
    else:
        bucket_label = f"s3://samscollectibles/{args.prefix}" if args.prefix else "s3://samscollectibles/"
        print(f"{bucket_label} ({total_files} files, {format_size(total_size)})")
        print_tree(tree, '', 0, args.depth, args.summary)
        print(f"\n{total_files} files, {format_size(total_size)}")


if __name__ == '__main__':
    main()
