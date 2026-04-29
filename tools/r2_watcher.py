#!/usr/bin/env python3
"""
Sam's Collectibles -- R2 Folder Watcher

Monitors a local directory for new images and auto-uploads them to
Cloudflare R2 with proper naming conventions and directory structure.

The watch directory uses a folder-path convention to determine the R2
destination. The last folder segment becomes the SKU identifier.

Directory structure convention:
    ~/Pictures/SC4-Upload/
    +-- star-wars/anh/series-1/1star-101/    <- drop photos here
    |   +-- IMG_1234.jpg                      <- auto-renamed to 1star-101-p01.jpg
    |   +-- IMG_1235.jpg                      <- auto-renamed to 1star-101-p02.jpg
    +-- star-wars/anh/series-2/2star-105/
    +-- posters/star-wars/                    <- keeps original filename
    +-- comic-books/star-wars-marvel/issue-001/

For trading cards, the last folder name is split into {type}-{sku}:
    1star-101  ->  type=1star, sku=101
    2star-105  ->  type=2star, sku=105
    mixed-201  ->  type=mixed, sku=201

For posters and comics, original filenames are preserved (lowercased).

Usage:
    # Watch mode (continuous monitoring)
    python tools/r2_watcher.py --watch ~/Pictures/SC4-Upload/

    # Process existing files once and exit
    python tools/r2_watcher.py --once ~/Pictures/SC4-Upload/

    # Dry run (show what would be uploaded without uploading -- no 1Password access needed)
    python tools/r2_watcher.py --once --dry-run ~/Pictures/SC4-Upload/

    # Custom delay between uploads (default 0.5s)
    python tools/r2_watcher.py --watch --delay 1.0 ~/Pictures/SC4-Upload/

Requirements:
    pip3 install watchdog        (only needed for --watch mode)

    The 1Password CLI (`op`) must be available and the desktop app
    unlocked. Credentials are pulled from
        op://sams.collectibles/Cloudflare R2 - samscollectibles
    on first upload (one Touch ID prompt per process).

    Do NOT run this from launchd / cron / non-TTY contexts unless you
    also set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT_URL
    via EnvironmentVariables (or use a 1Password service account token
    via OP_SERVICE_ACCOUNT_TOKEN). Interactive prompts can't be answered
    from a background process and will hang the whole job.
"""

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import boto3
from botocore.config import Config

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    Observer = None
    FileSystemEventHandler = object  # placeholder so subclassing doesn't NameError
    HAS_WATCHDOG = False

# ---------------------------------------------------------------------------
# R2 Configuration — resolved LAZILY at first use (not at import).
#
# Importing this module no longer triggers any 1Password prompt — that
# only happens when get_s3_client() is actually called. This matters for
# `--dry-run`, `--help`, and any test that just imports the module.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _r2_creds import load as _load_r2_creds  # noqa: E402

_CREDS = None  # populated on first get_s3_client() call


def _ensure_creds():
    """Resolve and memoize R2 credentials. Called lazily."""
    global _CREDS
    if _CREDS is None:
        _CREDS = _load_r2_creds()
    return _CREDS


# These names are read by other modules (and the dry-run path); they fall
# back to env / sane defaults so a `--dry-run` doesn't need 1Password.
BUCKET   = os.environ.get("R2_BUCKET", "samscollectibles")
CDN_BASE = os.environ.get("R2_CDN_BASE", "https://media.samscollectibles.net").rstrip("/")

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

CONTENT_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}

# Categories that keep original filenames (not trading cards)
NON_CARD_PREFIXES = ('posters', 'comic-books')

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent
LOG_FILE = LOG_DIR / 'r2_watcher.log'

logger = logging.getLogger('r2_watcher')


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = '%(asctime)s  %(levelname)-7s  %(message)s'

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(fmt, datefmt='%H:%M:%S'))
    logger.addHandler(ch)

    # File handler
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(fh)

    logger.setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# R2 helpers
# ---------------------------------------------------------------------------
def get_s3_client():
    """Return a boto3 S3 client for R2. Resolves credentials lazily on first call.

    If we're running in a non-interactive context (no controlling TTY,
    e.g. a launchd background job) and no R2_* env vars are set, the
    `op inject` call will hang or fail because it can't show a prompt.
    Detect that and fail fast with a clear message instead of hanging.
    """
    global BUCKET, CDN_BASE
    no_tty = not sys.stdin.isatty()
    have_env_creds = (
        os.environ.get("R2_ACCESS_KEY_ID")
        and os.environ.get("R2_SECRET_ACCESS_KEY")
        and os.environ.get("R2_ENDPOINT_URL")
    )
    if no_tty and not have_env_creds:
        raise RuntimeError(
            "r2_watcher.py is running without a TTY (likely launchd) and "
            "no R2_* env vars are set. Interactive 1Password prompts will "
            "not work in this context.\n\n"
            "Fix: launch the watcher via `op run -- python3 tools/r2_watcher.py …` "
            "from your shell (one prompt up front, none for the watcher's "
            "lifetime), OR configure a 1Password Service Account token via "
            "OP_SERVICE_ACCOUNT_TOKEN, OR export R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY, R2_ENDPOINT_URL into the launchd plist's "
            "EnvironmentVariables. See docs/r2-tools-reference.md."
        )

    creds = _ensure_creds()
    BUCKET = creds.bucket
    CDN_BASE = creds.cdn_base
    return boto3.client(
        's3',
        endpoint_url=creds.endpoint,
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret,
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def upload_file(s3, local_path, r2_key, dry_run=False):
    """Upload a single file to R2. Returns the CDN URL."""
    ext = Path(local_path).suffix.lower()
    content_type = CONTENT_TYPES.get(ext, 'application/octet-stream')
    url = f"{CDN_BASE}/{r2_key}"

    if dry_run:
        logger.info("[DRY RUN] Would upload: %s -> %s", local_path, url)
        return url

    s3.upload_file(
        str(local_path), BUCKET, r2_key,
        ExtraArgs={'ContentType': content_type}
    )
    logger.info("Uploaded: %s -> %s", Path(local_path).name, url)
    return url


def verify_r2_upload(s3, r2_key):
    """Verify a file exists on R2 by checking its metadata. Returns True if OK."""
    try:
        resp = s3.head_object(Bucket=BUCKET, Key=r2_key)
        size = resp.get('ContentLength', 0)
        if size > 0:
            logger.debug("Verified on R2: %s (%d bytes)", r2_key, size)
            return True
        logger.warning("R2 file has 0 bytes: %s", r2_key)
        return False
    except Exception as e:
        logger.warning("R2 verification failed for %s: %s", r2_key, e)
        return False


# ---------------------------------------------------------------------------
# Path resolution: local path -> R2 key
# ---------------------------------------------------------------------------
def resolve_r2_key(filepath, watch_root):
    """
    Given a file path under watch_root, determine the R2 key.

    For trading cards (anything not under posters/ or comic-books/):
        watch_root/star-wars/anh/series-1/1star-101/IMG_1234.jpg
        -> trading-cards/star-wars/anh/series-1/1star-101-p01.jpg

    For posters/comics:
        watch_root/posters/star-wars/sw-poster.jpg
        -> posters/star-wars/sw-poster.jpg
    """
    filepath = Path(filepath)
    watch_root = Path(watch_root)
    relative = filepath.relative_to(watch_root)
    parts = relative.parts  # e.g. ('star-wars', 'anh', 'series-1', '1star-101', 'IMG_1234.jpg')

    if len(parts) < 2:
        # File is directly in watch root -- use original name
        return filepath.name.lower().replace(' ', '-')

    top_level = parts[0].lower()

    if top_level in ('posters', 'comic-books'):
        # Preserve original filename (lowercased, spaces to dashes)
        clean_parts = [p.lower().replace(' ', '-') for p in parts]
        return '/'.join(clean_parts)

    # Trading cards: folder-based naming
    # The parent directory name is the SKU identifier (e.g. "1star-101")
    sku_folder = filepath.parent.name.lower().replace(' ', '-')
    category_parts = [p.lower().replace(' ', '-') for p in parts[:-2]]
    # parts[:-2] = category path, parts[-2] = sku folder, parts[-1] = filename

    if not category_parts:
        category_parts = [top_level]

    # Count existing files in this sku folder to determine photo number
    existing_images = sorted([
        f for f in filepath.parent.iterdir()
        if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file()
    ])
    try:
        photo_num = existing_images.index(filepath) + 1
    except ValueError:
        photo_num = len(existing_images) + 1

    ext = filepath.suffix.lower()
    filename = f"{sku_folder}-p{photo_num:02d}{ext}"
    r2_key = f"trading-cards/{'/'.join(category_parts)}/{filename}"
    return r2_key


# ---------------------------------------------------------------------------
# Process files
# ---------------------------------------------------------------------------
def process_file(s3, filepath, watch_root, dry_run=False, delay=0.5,
                  delete_after_upload=False):
    """Process a single image file: resolve R2 key, upload, optionally delete."""
    filepath = Path(filepath)
    if not filepath.is_file():
        return None
    if filepath.suffix.lower() not in IMAGE_EXTENSIONS:
        return None
    if filepath.name.startswith('.'):
        return None

    r2_key = resolve_r2_key(filepath, watch_root)
    url = upload_file(s3, filepath, r2_key, dry_run=dry_run)

    if delete_after_upload and not dry_run and url:
        if verify_r2_upload(s3, r2_key):
            filepath.unlink()
            logger.info("Deleted local file: %s", filepath)
        else:
            logger.warning("Keeping local file (R2 verify failed): %s", filepath)

    if delay > 0 and not dry_run:
        time.sleep(delay)

    return url


def process_directory(s3, watch_root, dry_run=False, delay=0.5,
                      delete_after_upload=False):
    """Walk the watch directory and process all existing image files."""
    watch_root = Path(watch_root)
    if not watch_root.exists():
        logger.error("Watch directory does not exist: %s", watch_root)
        return 0, 0, 0

    uploaded = 0
    skipped = 0
    errors = 0

    for root, dirs, files in os.walk(watch_root):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in sorted(files):
            if filename.startswith('.'):
                continue
            filepath = Path(root) / filename
            if filepath.suffix.lower() not in IMAGE_EXTENSIONS:
                skipped += 1
                continue

            try:
                url = process_file(s3, filepath, watch_root,
                                   dry_run=dry_run, delay=delay,
                                   delete_after_upload=delete_after_upload)
                if url:
                    uploaded += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("Failed to upload %s: %s", filepath, e)
                errors += 1

    return uploaded, skipped, errors


# ---------------------------------------------------------------------------
# Watchdog event handler
# ---------------------------------------------------------------------------
class R2UploadHandler(FileSystemEventHandler):
    """Handles new/moved image files and uploads them to R2."""

    def __init__(self, s3, watch_root, dry_run=False, delay=0.5,
                 delete_after_upload=False):
        super().__init__()
        self.s3 = s3
        self.watch_root = Path(watch_root)
        self.dry_run = dry_run
        self.delay = delay
        self.delete_after_upload = delete_after_upload
        self.processed = set()

    def _handle(self, filepath):
        filepath = Path(filepath)
        if filepath.suffix.lower() not in IMAGE_EXTENSIONS:
            return
        if filepath.name.startswith('.'):
            return
        if str(filepath) in self.processed:
            return

        # Wait a moment for file to finish writing
        time.sleep(0.5)
        if not filepath.is_file():
            return

        self.processed.add(str(filepath))
        try:
            process_file(self.s3, filepath, self.watch_root,
                         dry_run=self.dry_run, delay=self.delay,
                         delete_after_upload=self.delete_after_upload)
        except Exception as e:
            logger.error("Failed to upload %s: %s", filepath, e)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Sam's Collectibles -- R2 Folder Watcher\n\n"
                    "Monitors a directory for new images and auto-uploads\n"
                    "them to Cloudflare R2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Directory structure convention:
  ~/Pictures/SC4-Upload/
  +-- star-wars/anh/series-1/1star-101/   <- trading card SKU folder
  |   +-- IMG_1234.jpg                     <- becomes 1star-101-p01.jpg
  +-- posters/star-wars/                   <- keeps original filename
  +-- comic-books/star-wars-marvel/        <- keeps original filename

Examples:
  # Watch continuously
  %(prog)s --watch ~/Pictures/SC4-Upload/

  # Process existing files once
  %(prog)s --once ~/Pictures/SC4-Upload/

  # Dry run (no actual uploads)
  %(prog)s --once --dry-run ~/Pictures/SC4-Upload/
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--watch', action='store_true',
                      help='Watch directory continuously for new files')
    mode.add_argument('--once', action='store_true',
                      help='Process existing files once and exit')

    parser.add_argument('directory',
                        help='Directory to watch/process '
                             '(default: ~/Pictures/SC4-Upload/)',
                        nargs='?',
                        default=os.path.expanduser('~/Pictures/SC4-Upload'))
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be uploaded without uploading')
    parser.add_argument('--delete-after-upload', action='store_true',
                        help='Delete local file after upload + R2 verification (200 OK)')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay between uploads in seconds (default: 0.5)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose/debug logging')

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    watch_dir = Path(args.directory).expanduser().resolve()
    logger.info("R2 Watcher starting")
    logger.info("Watch directory: %s", watch_dir)
    logger.info("R2 bucket: %s", BUCKET)
    logger.info("CDN base: %s", CDN_BASE)

    if args.dry_run:
        logger.info("** DRY RUN MODE -- no files will be uploaded **")
    if args.delete_after_upload:
        logger.info("** DELETE AFTER UPLOAD -- local files will be removed after R2 verification **")

    # Ensure the watch directory exists
    if not watch_dir.exists():
        logger.info("Creating watch directory: %s", watch_dir)
        watch_dir.mkdir(parents=True, exist_ok=True)

    s3 = None if args.dry_run else get_s3_client()

    if args.once:
        logger.info("Processing existing files...")
        uploaded, skipped, errors = process_directory(
            s3, watch_dir, dry_run=args.dry_run, delay=args.delay,
            delete_after_upload=args.delete_after_upload)
        logger.info("Done. Uploaded: %d | Skipped: %d | Errors: %d",
                     uploaded, skipped, errors)

    elif args.watch:
        if not HAS_WATCHDOG:
            logger.error("watchdog library required for --watch mode. "
                         "Install with: pip3 install watchdog")
            sys.exit(1)

        # First process any existing files
        logger.info("Processing existing files before watching...")
        uploaded, skipped, errors = process_directory(
            s3, watch_dir, dry_run=args.dry_run, delay=args.delay,
            delete_after_upload=args.delete_after_upload)
        logger.info("Initial scan: Uploaded: %d | Skipped: %d | Errors: %d",
                     uploaded, skipped, errors)

        # Start watching
        handler = R2UploadHandler(s3, watch_dir,
                                  dry_run=args.dry_run, delay=args.delay,
                                  delete_after_upload=args.delete_after_upload)
        observer = Observer()
        observer.schedule(handler, str(watch_dir), recursive=True)
        observer.start()

        logger.info("Watching for new files... (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping watcher...")
            observer.stop()
        observer.join()
        logger.info("Watcher stopped.")


if __name__ == '__main__':
    main()
