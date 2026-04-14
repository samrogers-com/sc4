"""
Pre-built eBay HTML description file discovery and loading.

Scans the ebay_uploads/ directory for HTML description files that
can be loaded into new eBay listing drafts. Supports fuzzy matching
between R2 folder names and HTML filenames.

Directory structure:
    ebay_uploads/
        ns_cards/
            box/          <- Sealed boxes
            sets/         <- Complete sets
            packs/        <- Sealed packs
            singles/      <- Single cards
        comic_books/      <- Comic book listings
        posters/          <- Poster listings
"""
import os
import re
from pathlib import Path

# Project root (one level above src/)
EBAY_UPLOADS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / 'ebay_uploads'


def list_description_files(subfolder=None):
    """List all available pre-built HTML description files.

    Args:
        subfolder: Optional subfolder to filter (e.g. 'ns_cards/box')

    Returns:
        List of dicts: [{'name': 'Human-Readable Name', 'path': 'relative/path.html', 'filename': 'file.html'}]
    """
    results = []
    search_root = EBAY_UPLOADS_ROOT / subfolder if subfolder else EBAY_UPLOADS_ROOT

    if not search_root.exists():
        return results

    for html_file in sorted(search_root.rglob('*.html')):
        rel_path = str(html_file.relative_to(EBAY_UPLOADS_ROOT))
        # Convert filename to human-readable: "1995-007-goldeneye-sealed-box.html" -> "1995 007 Goldeneye Sealed Box"
        name = html_file.stem.replace('-', ' ').title()
        results.append({
            'name': name,
            'path': rel_path,
            'filename': html_file.name,
        })

    return results


def find_matching_description(r2_prefix):
    """Find a pre-built HTML description matching an R2 product folder.

    Uses slug overlap between the R2 folder name and HTML filenames.
    For example:
        R2: trading-cards/boxes/007-goldeneye
        Matches: ns_cards/box/1995-007-goldeneye-sealed-box.html

    Args:
        r2_prefix: R2 folder path (e.g. 'trading-cards/boxes/007-goldeneye')

    Returns:
        Dict with 'name', 'path', 'content' if found, None otherwise.
    """
    if not EBAY_UPLOADS_ROOT.exists():
        return None

    # Extract the product slug from the R2 prefix
    folder_name = r2_prefix.rstrip('/').split('/')[-1]
    folder_words = set(re.split(r'[-_]', folder_name.lower()))
    # Remove very common words that would cause false matches
    folder_words -= {'the', 'a', 'an', 'of', 'and', 'in', 'on', 'for'}

    best_match = None
    best_overlap = 0

    for html_file in EBAY_UPLOADS_ROOT.rglob('*.html'):
        file_words = set(re.split(r'[-_]', html_file.stem.lower()))
        file_words -= {'the', 'a', 'an', 'of', 'and', 'in', 'on', 'for', 'sealed', 'box', 'set', 'complete'}

        overlap = len(folder_words & file_words)
        if overlap > best_overlap and overlap >= 2:
            best_overlap = overlap
            best_match = html_file

    if best_match:
        return {
            'name': best_match.stem.replace('-', ' ').title(),
            'path': str(best_match.relative_to(EBAY_UPLOADS_ROOT)),
            'content': best_match.read_text(),
        }

    return None


def read_description_file(relative_path):
    """Read a pre-built HTML description file safely.

    Args:
        relative_path: Path relative to ebay_uploads/ root

    Returns:
        HTML content string, or None if file not found / invalid path.
    """
    # Security: ensure path doesn't escape ebay_uploads/
    target = (EBAY_UPLOADS_ROOT / relative_path).resolve()
    if not str(target).startswith(str(EBAY_UPLOADS_ROOT.resolve())):
        return None

    if target.exists() and target.suffix == '.html':
        return target.read_text()

    return None
