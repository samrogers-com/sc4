"""
Sam's Collectibles - CSV Generator (Phase 3)
Generates eBay-compatible CSV files for bulk upload via Seller Hub Reports.

Uses data from:
    - inventory_tracker.py (inventory_status.json)
    - sold_price_lookup.py (price_cache.json)
    - ebay_descriptions/ (HTML files)
    - config.py (eBay defaults, category mappings, etc.)

Usage:
    python csv_generator.py
    python csv_generator.py --items "ds9-series-1,master-series"
    python csv_generator.py --drafts
    python csv_generator.py --default-price 99.95
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from config import (
    DATA_DIR,
    OUTPUT_DIR,
    DESCRIPTIONS_DIR,
    CSV_TEMPLATE_PATH,
    CATEGORY_MAP,
    CONDITION_MAP,
    COMIC_CONDITION_MAP,
    LISTING_DEFAULTS,
    SHIPPING_DEFAULTS,
    RETURN_DEFAULTS,
    ITEM_SPECIFICS_DEFAULTS,
    COMIC_ITEM_SPECIFICS,
    POSTER_ITEM_SPECIFICS,
    COMIC_ERAS,
    COMIC_PUBLISHERS,
)


# =============================================================================
# HTML PARSING
# =============================================================================

def extract_title_from_html(html_path: str) -> str:
    """
    Extract the listing title from an HTML description file.
    Looks for the first large font tag with sky blue color (#87ceeb),
    which is the header in Sam's template.
    """
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    if HAS_BS4:
        soup = BeautifulSoup(content, "html.parser")
        # Find the title — it's in a font tag with color="#87ceeb" and size="5"
        title_tag = soup.find("font", {"color": "#87ceeb", "size": "5"})
        if title_tag:
            # Get text, strip whitespace
            title = title_tag.get_text(strip=True)
            # eBay title limit is 80 characters
            if len(title) > 80:
                title = title[:77] + "..."
            return title

    # Fallback: regex extraction
    match = re.search(
        r'color="#87ceeb"[^>]*>\s*<b>(.*?)</b>',
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        if len(title) > 80:
            title = title[:77] + "..."
        return title

    # Last resort: use filename
    return Path(html_path).stem.replace("-", " ").title()


def extract_item_specifics_from_html(html_path: str) -> dict:
    """
    Extract item specifics from the HTML description content.
    Looks for keywords in the description text to populate C: fields.
    """
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read().lower()

    specifics = {}

    # Franchise detection
    franchise_keywords = {
        "star wars": "Star Wars",
        "star trek": "Star Trek",
        "marvel": "Marvel",
        "x-files": "The X-Files",
        "x-men": "X-Men",
        "james bond": "James Bond",
        "007": "James Bond",
        "dune": "Dune",
        "godzilla": "Godzilla",
        "lost in space": "Lost in Space",
        "disney": "Disney",
        "wizard of oz": "The Wizard of Oz",
        "space: 1999": "Space: 1999",
        "space 1999": "Space: 1999",
        "outer limits": "The Outer Limits",
        "valiant": "Valiant",
    }
    for keyword, franchise in franchise_keywords.items():
        if keyword in content:
            specifics["C:Franchise"] = franchise
            break

    # Manufacturer detection
    manufacturer_keywords = {
        "topps": "Topps",
        "skybox": "SkyBox",
        "impel": "Impel",
        "fleer": "Fleer",
        "donruss": "Donruss",
        "inkworks": "Inkworks",
        "upper deck": "Upper Deck",
        "decipher": "Decipher",
        "duocards": "DuoCards",
        "pacific": "Pacific",
        "merlin": "Merlin",
        "jpp/amada": "JPP/Amada",
    }
    for keyword, manufacturer in manufacturer_keywords.items():
        if keyword in content:
            specifics["C:Manufacturer"] = manufacturer
            break

    # Year detection
    year_match = re.search(r'\b(19[6-9]\d|20[0-2]\d)\b', content)
    if year_match:
        specifics["C:Year Manufactured"] = year_match.group(1)

    # Configuration detection (box, pack, set, etc.)
    if "sealed box" in content or "wax box" in content or "sealed wax box" in content:
        specifics["C:Configuration"] = "Box"
        specifics["C:Features"] = "Factory Sealed"
    elif "sealed pack" in content or "wax pack" in content:
        specifics["C:Configuration"] = "Pack"
        specifics["C:Features"] = "Factory Sealed"
    elif "complete set" in content or "base set" in content:
        specifics["C:Configuration"] = "Set"
    elif "single card" in content:
        specifics["C:Configuration"] = "Single Card"

    # Set name detection (look for bold text after the title)
    set_match = re.search(
        r'<b>(.*?)</b>.*?trading card',
        content,
        re.IGNORECASE,
    )
    if set_match:
        set_name = re.sub(r'<[^>]+>', '', set_match.group(1)).strip()
        if len(set_name) < 60:
            specifics["C:Set"] = set_name

    # Character detection
    character_keywords = [
        "captain jean-luc picard", "luke skywalker", "darth vader",
        "william shatner", "patrick stewart", "prince xizor",
        "deanna troi", "leonard nimoy", "han solo", "princess leia",
        "chewbacca", "boba fett", "yoda", "obi-wan kenobi",
        "emperor palpatine", "lando calrissian",
    ]
    found_characters = []
    for char in character_keywords:
        if char in content:
            found_characters.append(char.title())
    if found_characters:
        specifics["C:Character"] = ", ".join(found_characters[:3])

    # --- Comic Book specifics ---
    publisher_keywords = {
        "marvel comics": "Marvel",
        "marvel": "Marvel",
        "dark horse": "Dark Horse",
        "dc comics": "DC",
        "image comics": "Image",
        "valiant": "Valiant",
        "idw": "IDW",
    }
    for keyword, publisher in publisher_keywords.items():
        if keyword in content:
            specifics["C:Publisher"] = publisher
            break

    # Issue number detection
    issue_match = re.search(r'#\s*(\d+)', content) or re.search(r'issue\s+(\d+)', content)
    if issue_match:
        specifics["C:Issue Number"] = issue_match.group(1)

    # Comic era classification
    year_str = specifics.get("C:Year Manufactured", "")
    if year_str:
        try:
            year_int = int(year_str)
            for era_name, (start, end) in COMIC_ERAS.items():
                if start <= year_int <= end:
                    specifics["C:Era"] = era_name.replace("_", " ").title()
                    break
        except ValueError:
            pass

    # Key issue indicators
    key_issue_keywords = [
        "first appearance", "1st appearance", "origin story", "origin of",
        "death of", "first issue", "last issue", "key issue",
    ]
    for keyword in key_issue_keywords:
        if keyword in content:
            specifics["C:Key Issue"] = "Yes"
            break

    # --- Poster specifics ---
    poster_type_keywords = {
        "original theatrical": "Original Theatrical Release",
        "original one sheet": "Original Theatrical Release",
        "re-issue": "Re-issue",
        "reissue": "Re-issue",
        "re-release": "Re-issue",
        "reproduction": "Reproduction",
        "reprint": "Reproduction",
        "advance": "Advance/Teaser",
        "teaser": "Advance/Teaser",
        "special edition": "Special Edition",
        "commercial": "Commercial Print",
        "promotional": "Promotional",
    }
    for keyword, ptype in poster_type_keywords.items():
        if keyword in content:
            specifics["C:Poster Type"] = ptype
            break

    # Poster size detection
    poster_size_keywords = {
        "one sheet": "One Sheet (27x41)",
        "one-sheet": "One Sheet (27x41)",
        "27x41": "One Sheet (27x41)",
        "half sheet": "Half Sheet (22x28)",
        "22x28": "Half Sheet (22x28)",
        "insert 14x36": "Insert (14x36)",
        "14x36": "Insert (14x36)",
        "lobby card": "Lobby Card (11x14)",
        "11x14": "Lobby Card (11x14)",
        "24x36": "Standard (24x36)",
        "three sheet": "Three Sheet (41x81)",
    }
    for keyword, psize in poster_size_keywords.items():
        if keyword in content:
            specifics["C:Size"] = psize
            break

    # Artist detection for posters
    artist_match = re.search(r'artist[:\s]+([a-z\s\.\-]+)', content)
    if artist_match:
        specifics["C:Artist"] = artist_match.group(1).strip().title()

    return specifics


def read_html_description(html_path: str) -> str:
    """Read the full HTML description file content."""
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read().strip()


# =============================================================================
# SKU GENERATOR
# =============================================================================

def generate_sku(item: dict) -> str:
    """
    Generate a custom label/SKU for an item.
    Format varies by product type:
      Trading cards: NS-{TYPE}-{FRANCHISE}-{NAME_SLUG}
      Comic books:   CB-{PUBLISHER}-{FRANCHISE}-{SLUG}
      Posters:       MP-{FRANCHISE}-{SLUG}
    """
    product_type = item.get("product_type", "unknown")
    franchise = item.get("franchise", "unknown").upper()[:4]
    name = item.get("description_name", item.get("name", "unknown"))
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower())[:30].strip('-')

    if product_type == "comic_books":
        # Try to detect publisher from the path or name
        publisher = "UNK"
        name_lower = name.lower()
        if "marvel" in name_lower or "sw-marvel" in name_lower:
            publisher = "MRVL"
        elif "dark horse" in name_lower or "darkhorse" in name_lower:
            publisher = "DH"
        elif "dc" in name_lower:
            publisher = "DC"
        return f"CB-{publisher}-{franchise}-{slug}"

    elif product_type == "posters":
        return f"MP-{franchise}-{slug}"

    else:
        # Trading cards (default)
        type_prefix = product_type.upper()[:3]
        return f"NS-{type_prefix}-{franchise}-{slug}"


# =============================================================================
# CSV BUILDING
# =============================================================================

def load_template_headers(template_path: Path) -> list[str]:
    """
    Load column headers from the eBay CSV template.
    The first 3 lines are metadata; actual headers start at line 4.
    """
    if not template_path.exists():
        print(f"  [WARN] Template not found: {template_path}")
        print(f"         Using default column set.")
        return get_default_headers()

    with open(template_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    # The template has metadata lines first, then the actual headers
    # Find the line that starts with the header columns
    for i, line in enumerate(lines):
        if line.startswith("Info") or line.startswith("Version") or line.startswith("Template"):
            continue
        # This should be the header row
        headers = line.strip().split(",")
        return headers

    return get_default_headers()


def get_default_headers() -> list[str]:
    """Return the minimal required headers for eBay CSV upload."""
    return [
        "*Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)",
        "CustomLabel",
        "*Category",
        "StoreCategory",
        "*Title",
        "Subtitle",
        "*ConditionID",
        "C:Franchise",
        "C:Set",
        "C:Manufacturer",
        "C:Configuration",
        "C:Year Manufactured",
        "C:Character",
        "C:Material",
        "C:Features",
        "C:Country of Origin",
        "C:Language",
        "C:Vintage",
        "PicURL",
        "*Description",
        "*Format",
        "*Duration",
        "*StartPrice",
        "BuyItNowPrice",
        "BestOfferEnabled",
        "*Quantity",
        "ImmediatePayRequired",
        "*Location",
        "ShippingType",
        "ShippingService-1:Option",
        "ShippingService-1:Cost",
        "*DispatchTimeMax",
        "*ReturnsAcceptedOption",
        "ReturnsWithinOption",
        "RefundOption",
        "ShippingCostPaidByOption",
    ]


def build_row(item: dict, price: float | None, headers: list[str]) -> dict:
    """
    Build a single CSV row for an item.
    Returns a dict mapping header -> value.
    """
    html_path = item.get("description_file", "")
    description_html = read_html_description(html_path) if html_path else ""
    title = extract_title_from_html(html_path) if html_path else item.get("name", "")
    specifics = extract_item_specifics_from_html(html_path) if html_path else {}
    sku = generate_sku(item)

    product_type = item.get("product_type", "boxes")
    category = CATEGORY_MAP.get(product_type, "261035")

    # Start with empty row
    row = {h: "" for h in headers}

    # Action column (first column, has the complex name)
    action_col = headers[0] if headers else "*Action"
    row[action_col] = "Add"

    # Core fields
    row["CustomLabel"] = sku
    row["*Category"] = category
    row["*Title"] = title
    row["*ConditionID"] = LISTING_DEFAULTS["condition_id"]
    row["*Description"] = description_html
    row["*Format"] = LISTING_DEFAULTS["format"]
    row["*Duration"] = LISTING_DEFAULTS["duration"]
    row["*Quantity"] = LISTING_DEFAULTS["quantity"]
    row["*Location"] = LISTING_DEFAULTS["location"]
    row["ImmediatePayRequired"] = LISTING_DEFAULTS["immediate_pay"]

    # Price
    if price:
        row["*StartPrice"] = str(price)
    else:
        row["*StartPrice"] = ""  # Must be filled manually

    # Best Offer (optional)
    row["BestOfferEnabled"] = "1"

    # Shipping
    row["ShippingType"] = SHIPPING_DEFAULTS["shipping_type"]
    row["ShippingService-1:Option"] = SHIPPING_DEFAULTS["shipping_service_1"]
    row["ShippingService-1:Cost"] = SHIPPING_DEFAULTS["shipping_cost_1"]
    row["*DispatchTimeMax"] = SHIPPING_DEFAULTS["dispatch_time_max"]

    # Returns
    row["*ReturnsAcceptedOption"] = RETURN_DEFAULTS["returns_accepted"]
    row["ReturnsWithinOption"] = RETURN_DEFAULTS["returns_within"]
    row["RefundOption"] = RETURN_DEFAULTS["refund_option"]
    row["ShippingCostPaidByOption"] = RETURN_DEFAULTS["shipping_cost_paid_by"]

    # Item Specifics — choose defaults based on product type
    if product_type == "comic_books":
        base_specifics = COMIC_ITEM_SPECIFICS
    elif product_type == "posters":
        base_specifics = POSTER_ITEM_SPECIFICS
    else:
        base_specifics = ITEM_SPECIFICS_DEFAULTS

    merged_specifics = {**base_specifics, **specifics}
    for key, value in merged_specifics.items():
        if key in row:
            row[key] = value

    # PicURL stays blank for now (photos added manually in Seller Hub)
    row["PicURL"] = ""

    return row


def generate_csv(
    items: list[dict],
    prices: dict,
    output_path: Path | None = None,
    default_price: float | None = None,
) -> Path:
    """
    Generate the eBay bulk upload CSV.

    Args:
        items: List of ready-to-list items from inventory_status.json
        prices: Price cache dict from price_cache.json
        output_path: Where to save the CSV (default: auto-named in output/)
        default_price: Fallback price if no sold data found

    Returns:
        Path to the generated CSV file.
    """
    if not output_path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        output_path = OUTPUT_DIR / f"ebay_upload_{timestamp}.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = get_default_headers()
    rows = []

    for item in items:
        # Look up price from cache
        name_key = item.get("name", "").replace("/", " ").replace("-", " ").replace("_", " ").lower()
        # Try a few cache key patterns
        price = None
        for key, cached in prices.items():
            if name_key in key or key in name_key:
                price = cached.get("recommended_price")
                break

        if not price and default_price:
            price = default_price

        row = build_row(item, price, headers)
        rows.append(row)

    # Write CSV
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return output_path


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Sam's Collectibles - eBay CSV Generator"
    )
    parser.add_argument(
        "--items",
        help="Comma-separated list of item name fragments to include (default: all ready items)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output CSV file path",
    )
    parser.add_argument(
        "--default-price",
        type=float,
        help="Default price for items without sold data",
    )
    parser.add_argument(
        "--drafts",
        action="store_true",
        help="Generate as drafts (no price required, leave blank for manual entry)",
    )
    args = parser.parse_args()

    # Load inventory status
    inventory_file = DATA_DIR / "inventory_status.json"
    if not inventory_file.exists():
        print("ERROR: No inventory_status.json found.")
        print("       Run inventory_tracker.py first.")
        sys.exit(1)

    with open(inventory_file, "r") as f:
        inventory = json.load(f)

    ready_items = inventory.get("ready_to_list", [])
    if not ready_items:
        print("No items ready to list. Run inventory_tracker.py to check status.")
        sys.exit(0)

    # Filter items if requested
    if args.items:
        filter_terms = [t.strip().lower() for t in args.items.split(",")]
        ready_items = [
            item for item in ready_items
            if any(term in item.get("name", "").lower() or
                   term in item.get("description_name", "").lower()
                   for term in filter_terms)
        ]
        if not ready_items:
            print(f"No items matched filter: {args.items}")
            sys.exit(0)

    print(f"Generating CSV for {len(ready_items)} items...")

    # Load price cache
    price_cache_file = DATA_DIR / "price_cache.json"
    prices = {}
    if price_cache_file.exists():
        with open(price_cache_file, "r") as f:
            prices = json.load(f)
        print(f"  Loaded {len(prices)} cached prices")
    else:
        print("  No price cache found (prices will be blank)")

    # Generate CSV
    output_path = generate_csv(
        items=ready_items,
        prices=prices,
        output_path=args.output,
        default_price=args.default_price,
    )

    print(f"\n  CSV generated: {output_path}")
    print(f"  Items: {len(ready_items)}")

    # Summary of what's in the CSV
    print("\n  Items included:")
    for item in ready_items:
        name = item.get("description_name", item.get("name", "?"))
        print(f"    • {name}")

    print(f"\n  Next steps:")
    print(f"    1. Review the CSV in a spreadsheet app")
    print(f"    2. Fill in any blank prices")
    print(f"    3. Upload to eBay Seller Hub > Reports > Uploads")
    print(f"    4. Open each draft to add photos and publish")


if __name__ == "__main__":
    main()
