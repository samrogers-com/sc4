#!/usr/bin/env python3
"""
Sam's Collectibles -- Nightly Sold Listings Sync

Scheduled task wrapper for the eBay sold listings tracker.
Pulls the last 2 days of orders (overlap ensures nothing is missed)
and logs the result.

Designed to be run via cron, launchd, or Claude scheduled tasks.

Usage:
    python tools/ebay_nightly_sync.py

Crontab example (run at 2:00 AM daily):
    0 2 * * * cd /Users/samrogers/Claude/sc4 && /usr/bin/python3 tools/ebay_nightly_sync.py >> tools/data/nightly_sync.log 2>&1

LaunchAgent: see tools/com.samscollectibles.ebay-sync.plist
"""

import sys
import subprocess
from datetime import datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).parent
TRACKER_SCRIPT = TOOLS_DIR / "ebay_sold_tracker.py"
LOG_FILE = TOOLS_DIR / "data" / "nightly_sync.log"


def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] Starting nightly eBay sync...")

    # Pull last 2 days to ensure overlap coverage
    result = subprocess.run(
        [sys.executable, str(TRACKER_SCRIPT), "--days", "2"],
        capture_output=True,
        text=True,
        cwd=str(TOOLS_DIR.parent),
    )

    # Print stdout/stderr for logging
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"[{timestamp}] Sync failed with exit code {result.returncode}")
        sys.exit(1)

    print(f"[{timestamp}] Nightly sync complete.")


if __name__ == "__main__":
    main()
