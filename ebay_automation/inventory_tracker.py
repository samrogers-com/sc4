"""
Sam's Collectibles - Inventory Tracker (Phase 1)
Compares ebay_uploads/ (photos) and ebay_descriptions/ (HTML) against
the active eBay listings report to identify what's ready to list.

Usage:
    python inventory_tracker.py
    python inventory_tracker.py --active-report path/to/report.csv
    python inventory_tracker.py --verbose
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None


def _split_camel_case(text: str) -> str:
    """Insert space before uppercase letters that follow lowercase (camelCase → camel Case)."""
    # Handle transitions like "WizardOfOz" → "Wizard Of Oz"
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    # Handle transitions like "TNG" → "T N G" ... skip, keep acronyms together
    return text


def _normalize(text: str) -> str:
    """Normalize a string for comparison: split camelCase, lowercase, replace separators."""
    text = _split_camel_case(text)
    text = text.lower()
    text = re.sub(r'[/_\-.]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _fuzzy_score(a: str, b: str) -> float:
    """
    Score how well two strings match (0-100).
    Uses thefuzz if available, otherwise difflib SequenceMatcher.
    """
    if fuzz:
        return fuzz.token_sort_ratio(a, b)
    # difflib returns 0.0-1.0, scale to 0-100
    return SequenceMatcher(None, a, b).ratio() * 100


def _keyword_overlap_score(words_a: set[str], text_b: str) -> float:
    """
    Score based on how many keywords from set A appear in text B.
    Returns 0-100. Counts ALL word lengths (not just > 3).
    """
    if not words_a:
        return 0
    matches = sum(1 for w in words_a if w in text_b)
    return (matches / len(words_a)) * 100

from config import (
    UPLOADS_DIR,
    DESCRIPTIONS_DIR,
    ACTIVE_LISTINGS_PATH,
    DATA_DIR,
    UPLOAD_FOLDER_MAP,
    FRANCHISE_MAP,
)


# =============================================================================
# URL INDEX HELPER
# =============================================================================

def build_url_index(report_path: Path, data_dir: Path) -> dict:
    """
    Build (or refresh) ebay_url_index.json from the active listings CSV.
    Returns the index dict keyed by item number.
    """
    index_path = data_dir / "ebay_url_index.json"
    source_csv = report_path.name

    # Check if existing index is already from this CSV
    if index_path.exists():
        with open(index_path) as f:
            existing = json.load(f)
        if existing.get("source_csv") == source_csv:
            return existing.get("listings", {})

    # Rebuild from CSV
    listings = {}
    if report_path.exists():
        with open(report_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                item_number = row.get("Item number", "").strip().strip('"')
                if not item_number or item_number in listings:
                    continue
                listings[item_number] = {
                    "item_number": item_number,
                    "title": row.get("Title", "").strip().strip('"'),
                    "url": f"https://www.ebay.com/itm/{item_number}",
                    "price": row.get("Current price", "").strip().strip('"'),
                    "quantity": row.get("Available quantity", "").strip().strip('"'),
                    "report_date": datetime.now().strftime("%Y-%m-%d"),
                }

        data_dir.mkdir(parents=True, exist_ok=True)
        index = {
            "generated": datetime.now().isoformat(),
            "source_csv": source_csv,
            "total_listings": len(listings),
            "listings": listings,
        }
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)
        print(f"  Rebuilt URL index: {len(listings)} listings from {source_csv}")

    return listings


# =============================================================================
# SCANNING FUNCTIONS
# =============================================================================

def scan_uploads(uploads_dir: Path) -> list[dict]:
    """
    Scan ebay_uploads/ and return a list of products with photos.
    Each product is a dict with: name, path, product_type, franchise,
    photo_count, photo_files.
    """
    products = []

    for type_folder_name, mapping in UPLOAD_FOLDER_MAP.items():
        type_folder = uploads_dir / type_folder_name
        if not type_folder.exists():
            continue

        product_type = mapping["product_type"]

        for item_folder in sorted(type_folder.iterdir()):
            if not item_folder.is_dir():
                continue

            # Check if this folder has sub-items (e.g., box-1, box-2)
            # or direct photos
            sub_items = _scan_product_folder(item_folder, product_type)
            if sub_items:
                products.extend(sub_items)

    return products


def _scan_product_folder(folder: Path, product_type: str, parent_name: str = "") -> list[dict]:
    """
    Recursively scan a product folder for photos.
    Handles nested structures like:
        Star Trek/Deep Space Nine S1/IMG_001.JPG
        007-Moonraker/box-1/moonraker-01.webp
        Star Wars/sw-first_anthology/box1/IMG_001.JPG
    """
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
    results = []

    # Get direct image files in this folder
    direct_images = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in image_extensions
    ]

    # Get subdirectories
    subdirs = [d for d in sorted(folder.iterdir()) if d.is_dir()]

    if direct_images and not subdirs:
        # Leaf folder with photos — this IS a product
        full_name = f"{parent_name}/{folder.name}" if parent_name else folder.name
        franchise = _detect_franchise(full_name)
        results.append({
            "name": full_name,
            "path": str(folder),
            "product_type": product_type,
            "franchise": franchise,
            "photo_count": len(direct_images),
            "photo_files": [str(f) for f in direct_images],
        })
    elif subdirs:
        # Has subdirectories — recurse into each
        new_parent = f"{parent_name}/{folder.name}" if parent_name else folder.name
        for sub in subdirs:
            results.extend(_scan_product_folder(sub, product_type, new_parent))

        # Also grab any direct images at this level (some folders have both)
        if direct_images:
            franchise = _detect_franchise(new_parent)
            results.append({
                "name": new_parent,
                "path": str(folder),
                "product_type": product_type,
                "franchise": franchise,
                "photo_count": len(direct_images),
                "photo_files": [str(f) for f in direct_images],
            })

    return results


def _detect_franchise(folder_path: str) -> str:
    """
    Detect the franchise from a folder path using FRANCHISE_MAP.
    Checks each component of the path against the map.
    """
    parts = folder_path.replace("\\", "/").split("/")
    for part in parts:
        if part in FRANCHISE_MAP:
            return FRANCHISE_MAP[part]
        # Try case-insensitive
        for key, value in FRANCHISE_MAP.items():
            if part.lower() == key.lower():
                return value
    # Default: slugify the first meaningful folder name
    return parts[0].lower().replace(" ", "-").replace("_", "-")


def scan_descriptions(descriptions_dir: Path) -> list[dict]:
    """
    Scan ebay_descriptions/ and return a list of completed HTML files.
    Each entry is a dict with: name, path, product_type, franchise.
    """
    descriptions = []

    for html_file in sorted(descriptions_dir.rglob("*.html")):
        rel_path = html_file.relative_to(descriptions_dir)
        parts = rel_path.parts

        # Expected structure: ns-cards/boxes/starwars/filename.html
        product_type = parts[1] if len(parts) > 1 else "unknown"
        franchise = parts[2] if len(parts) > 2 else "unknown"

        descriptions.append({
            "name": html_file.stem,
            "path": str(html_file),
            "product_type": product_type,
            "franchise": franchise,
            "filename": html_file.name,
        })

    return descriptions


def load_active_listings(report_path: Path) -> list[dict]:
    """
    Load the eBay active listings report CSV.
    Returns a list of dicts with item data.
    """
    listings = []

    if not report_path.exists():
        print(f"  [WARN] Active listings report not found: {report_path}")
        print(f"         Download from Seller Hub > Reports > Downloads")
        return listings

    with open(report_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("Title", "").strip().strip('"')
            if title:
                listings.append({
                    "item_number": row.get("Item number", "").strip().strip('"'),
                    "title": title,
                    "price": row.get("Current price", "").strip().strip('"'),
                    "quantity": row.get("Available quantity", "").strip().strip('"'),
                    "category": row.get("eBay category 1 name", "").strip().strip('"'),
                    "condition": row.get("Condition", "").strip().strip('"'),
                    "format": row.get("Format", "").strip().strip('"'),
                })

    # Deduplicate by item number (variations create multiple rows)
    seen = set()
    unique = []
    for listing in listings:
        if listing["item_number"] not in seen:
            seen.add(listing["item_number"])
            unique.append(listing)

    # Ensure URL index is up to date
    build_url_index(report_path, DATA_DIR)

    return unique


# =============================================================================
# MATCHING LOGIC
# =============================================================================

def match_upload_to_description(upload: dict, descriptions: list[dict]) -> dict | None:
    """
    Try to match an upload folder to an HTML description file.
    Uses product_type + franchise filtering, then fuzzy name matching.
    """
    candidates = [
        d for d in descriptions
        if d["product_type"] == upload["product_type"]
        and d["franchise"] == upload["franchise"]
    ]

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Multiple candidates — score each one
    upload_name = _normalize(upload["name"])

    best_match = None
    best_score = 0

    for desc in candidates:
        desc_name = _normalize(desc["name"])
        score = _fuzzy_score(upload_name, desc_name)

        if score > best_score:
            best_score = score
            best_match = desc

    return best_match if best_score > 30 else None


def _load_manual_matches(data_dir: Path) -> dict:
    """Load manual folder→eBay title mappings from data/manual_matches.json if it exists."""
    path = data_dir / "manual_matches.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def is_already_listed(upload: dict, active_listings: list[dict], manual_matches: dict = None) -> dict | None:
    """
    Check if a product appears to already be listed on eBay.
    Uses a combination of fuzzy matching and keyword overlap.
    Requires strong evidence to declare a match — avoids false positives
    like "Space 1999" matching "Lost in Space".

    manual_matches: dict mapping upload folder name (or path) → eBay item number or
    partial title substring for explicit overrides.
    """
    # Check manual overrides first (exact folder name match)
    if manual_matches:
        folder_name = upload.get("name", "")
        if folder_name in manual_matches:
            override = manual_matches[folder_name]
            # Find the matching listing by item number or title substring
            for listing in active_listings:
                if (str(listing.get("item_number", "")) == str(override) or
                        override.lower() in listing["title"].lower()):
                    return listing
            # If we have a manual match key but can't find the listing,
            # still skip fuzzy — return a placeholder so it shows as "already listed"
            return {"title": f"[Manual] {override}", "item_number": override, "price": "N/A"}

    upload_name = _normalize(upload["name"])
    upload_words = set(w for w in upload_name.split() if w)
    # Significant words are 4+ chars (more distinctive)
    significant_words = {w for w in upload_words if len(w) >= 4}

    for listing in active_listings:
        title_norm = _normalize(listing["title"])

        # Method 1: Fuzzy string similarity (needs high threshold)
        fuzzy = _fuzzy_score(upload_name, title_norm)
        if fuzzy > 55:
            return listing

        # Method 2: ALL keywords from the folder name appear in the title
        if upload_words and len(upload_words) >= 2:
            all_match = all(w in title_norm for w in upload_words)
            if all_match:
                return listing

        # Method 3: High significant keyword overlap
        # Need at least 2 significant words matching, or 100% of them
        if significant_words:
            sig_matches = sum(1 for w in significant_words if w in title_norm)
            if len(significant_words) == 1 and sig_matches == 1:
                # Single keyword — also require it to be a substantial
                # portion of the title (avoid "space" matching everything)
                word = list(significant_words)[0]
                if len(word) >= 6 and word in title_norm:
                    return listing
            elif sig_matches >= 2 and sig_matches / len(significant_words) >= 0.6:
                return listing

    return None


# =============================================================================
# STATUS REPORT
# =============================================================================

def generate_status_report(
    uploads: list[dict],
    descriptions: list[dict],
    active_listings: list[dict],
    verbose: bool = False,
    data_dir: Path = None,
) -> dict:
    """
    Cross-reference uploads, descriptions, and active listings.
    Returns a categorized status report.
    """
    report = {
        "generated": datetime.now().isoformat(),
        "summary": {},
        "ready_to_list": [],
        "needs_description": [],
        "already_listed": [],
        "descriptions_without_photos": [],
    }

    # Load manual overrides
    manual_matches = _load_manual_matches(data_dir) if data_dir else {}
    if manual_matches:
        print(f"  Loaded {len(manual_matches)} manual match override(s).")

    matched_descriptions = set()

    for upload in uploads:
        # Check if already on eBay
        listing_match = is_already_listed(upload, active_listings, manual_matches)
        if listing_match:
            report["already_listed"].append({
                **upload,
                "ebay_item_number": listing_match["item_number"],
                "ebay_title": listing_match["title"],
                "ebay_price": listing_match["price"],
                "ebay_url": f"https://www.ebay.com/itm/{listing_match['item_number']}" if listing_match.get("item_number") and listing_match["item_number"] != "N/A" else "",
            })
            continue

        # Check if we have an HTML description
        desc_match = match_upload_to_description(upload, descriptions)
        if desc_match:
            matched_descriptions.add(desc_match["path"])
            report["ready_to_list"].append({
                **upload,
                "description_file": desc_match["path"],
                "description_name": desc_match["name"],
            })
        else:
            report["needs_description"].append(upload)

    # Find descriptions that don't have matching uploads
    for desc in descriptions:
        if desc["path"] not in matched_descriptions:
            report["descriptions_without_photos"].append(desc)

    report["summary"] = {
        "total_upload_folders": len(uploads),
        "ready_to_list": len(report["ready_to_list"]),
        "needs_description": len(report["needs_description"]),
        "already_listed": len(report["already_listed"]),
        "descriptions_without_photos": len(report["descriptions_without_photos"]),
        "total_html_descriptions": len(descriptions),
        "total_active_listings": len(active_listings),
    }

    return report


def print_report(report: dict, verbose: bool = False):
    """Pretty-print the status report to the console."""

    summary = report["summary"]

    print("\n" + "=" * 60)
    print("  SAM'S COLLECTIBLES - INVENTORY STATUS REPORT")
    print("=" * 60)
    print(f"  Generated: {report['generated']}")
    print(f"  Active eBay Listings: {summary['total_active_listings']}")
    print(f"  Upload Folders Scanned: {summary['total_upload_folders']}")
    print(f"  HTML Descriptions Found: {summary['total_html_descriptions']}")
    print()

    # Ready to list
    print(f"  ✅ READY TO LIST: {summary['ready_to_list']}")
    if report["ready_to_list"]:
        for item in report["ready_to_list"]:
            print(f"     • {item['name']} ({item['photo_count']} photos)")
            if verbose:
                print(f"       HTML: {item['description_name']}")

    print()

    # Needs description
    print(f"  📝 NEEDS DESCRIPTION (has photos, no HTML): {summary['needs_description']}")
    if report["needs_description"]:
        for item in report["needs_description"]:
            print(f"     • {item['name']} ({item['photo_count']} photos)")
            if verbose:
                print(f"       Franchise: {item['franchise']}, Type: {item['product_type']}")

    print()

    # Already listed
    print(f"  🔵 ALREADY ON EBAY: {summary['already_listed']}")
    if report["already_listed"] and verbose:
        for item in report["already_listed"]:
            print(f"     • {item['name']}")
            print(f"       eBay: {item['ebay_title']} (${item['ebay_price']})")

    print()

    # Descriptions without photos
    print(f"  📸 DESCRIPTIONS WITHOUT PHOTOS: {summary['descriptions_without_photos']}")
    if report["descriptions_without_photos"]:
        for item in report["descriptions_without_photos"]:
            print(f"     • {item['name']} ({item['product_type']}/{item['franchise']})")

    print()
    print("=" * 60)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Sam's Collectibles Inventory Tracker"
    )
    parser.add_argument(
        "--active-report",
        type=Path,
        default=ACTIVE_LISTINGS_PATH,
        help="Path to eBay active listings report CSV",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DATA_DIR / "inventory_status.json",
        help="Output path for JSON status file",
    )
    args = parser.parse_args()

    print("Scanning uploads folder...")
    uploads = scan_uploads(UPLOADS_DIR)
    print(f"  Found {len(uploads)} product folders with photos")

    print("Scanning descriptions folder...")
    descriptions = scan_descriptions(DESCRIPTIONS_DIR)
    print(f"  Found {len(descriptions)} HTML descriptions")

    print("Loading active listings report...")
    active_listings = load_active_listings(args.active_report)
    print(f"  Found {len(active_listings)} active eBay listings")

    if not fuzz:
        print("  [NOTE] Install 'thefuzz' for better matching: pip install thefuzz")

    print("Generating status report...")
    report = generate_status_report(uploads, descriptions, active_listings, args.verbose, data_dir=DATA_DIR)

    # Save JSON report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        # Remove photo_files from JSON to keep it manageable
        clean_report = json.loads(json.dumps(report, default=str))
        for section in ["ready_to_list", "needs_description", "already_listed"]:
            for item in clean_report.get(section, []):
                item.pop("photo_files", None)
        json.dump(clean_report, f, indent=2)
    print(f"  Saved to {args.output}")

    # Print to console
    print_report(report, verbose=args.verbose)


if __name__ == "__main__":
    main()
