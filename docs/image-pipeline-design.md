# Image Pipeline Design — R2 Storage & Photo Workflow

## Goals
1. All images stored on Cloudflare R2 (media.samscollectibles.net)
2. Directory structure matches the website navigation hierarchy
3. File naming convention ties photos to SKU/Custom Label
4. Automated upload from local machine to R2
5. Website and eBay automation both reference R2 URLs
6. iPhone photo workflow: shoot → rename → upload → appears on site + eBay

## R2 Directory Structure

```
samscollectibles/                          (R2 bucket root)
├── trading-cards/
│   ├── star-wars/
│   │   ├── anh/                           (A New Hope)
│   │   │   ├── series-1/
│   │   │   │   ├── 1star-101-p01.jpg      (SKU 101, page/photo 1)
│   │   │   │   ├── 1star-101-p02.jpg      (SKU 101, page/photo 2)
│   │   │   │   ├── 2star-102-p01.jpg
│   │   │   │   ├── mixed-103-p01.jpg
│   │   │   │   └── stickers-104-p01.jpg
│   │   │   ├── series-2/
│   │   │   └── ...
│   │   ├── esb/
│   │   ├── rotj/
│   │   ├── vehicles/
│   │   ├── widevision/
│   │   └── ...
│   ├── star-trek/
│   ├── marvel/
│   ├── dc-comics/
│   ├── movies/
│   ├── tv-shows/
│   ├── fantasy-art/
│   ├── sci-fi/
│   ├── historical-military/
│   ├── pop-culture/
│   └── disney/
├── comic-books/
│   ├── star-wars-marvel/
│   │   ├── covers/                        (stock cover images)
│   │   │   ├── StarWarsMarvel-001.webp
│   │   │   └── ...
│   │   ├── issue-001/                     (actual photos of Sam's copy)
│   │   │   ├── front.jpg
│   │   │   ├── back.jpg
│   │   │   └── spine.jpg
│   │   └── ...
│   └── star-wars-darkhorse/
├── posters/
│   ├── star-wars/
│   │   ├── sw-anh-style-a.jpg
│   │   ├── sw-anh-style-b-teaser.jpg
│   │   └── ...
│   └── other/
├── boxes/                                 (sealed box product photos)
├── packs/
└── singles/
```

## File Naming Convention

### Trading Card Sets
Format: `{star_variant}-{sku}-p{page_number}.jpg`

Examples:
- `1star-101-p01.jpg` — SKU 101, 1-star set, photo 1
- `1star-101-p02.jpg` — SKU 101, 1-star set, photo 2 (showing backs/puzzle)
- `mixed-115-p01.jpg` — SKU 115, mixed star set, photo 1
- `stickers-120-p01.jpg` — SKU 120, sticker set, photo 1

### Comic Books
Format: `{view}-{issue_number}.jpg`

Examples:
- `front-001.jpg` — Issue #1 front cover
- `back-001.jpg` — Issue #1 back cover
- `spine-001.jpg` — Issue #1 spine close-up

### Posters
Format: `{movie}-{style}-{view}.jpg`

Examples:
- `sw-anh-style-a-front.jpg`
- `sw-esb-advance-gwtw-front.jpg`
- `sw-rotj-style-b-detail.jpg`

## iPhone Photo Workflow

### Option A: Shortcut + Script (Recommended)
1. **Shoot** photos on iPhone in a dedicated album (e.g., "SC4 Upload")
2. **iPhone Shortcut** prompts for SKU number when saving
3. **AirDrop** or **iCloud sync** moves photos to Mac
4. **Watcher script** on Mac:
   - Monitors `~/Pictures/SC4-Upload/` for new files
   - Renames based on SKU input
   - Uploads to R2 automatically
   - Updates Django database with image URL

### Option B: Manual + Upload Script
1. Shoot photos, AirDrop to Mac
2. Put in `ebay_uploads/{category}/{subcategory}/`
3. Run upload script: `python upload_to_r2.py --sku 101 --path ebay_uploads/...`
4. Script renames, uploads to R2, updates database

### Option C: Web Upload (Future)
1. Django admin or custom upload page
2. Select set from dropdown, upload photos
3. Auto-renames and sends to R2

## Upload Script Design

```python
# tools/upload_to_r2.py
# Usage: python upload_to_r2.py --sku 101 --category star-wars/anh/series-1 --type 1star photos/*.jpg

# What it does:
# 1. Takes SKU, category path, star type, and photo files
# 2. Renames files to convention: {type}-{sku}-p{nn}.jpg
# 3. Uploads to R2 at: trading-cards/{category}/{filename}
# 4. Updates NonSportsCards database record with image URLs
# 5. Prints the R2 URLs for verification
```

## Migration Plan

### Phase 1: Migrate existing ebay_uploads to R2
- Already done: SW Marvel covers (107), poster images (2)
- TODO: Move all existing ebay_uploads photos to R2 matching new structure
- Update ebay_automation to reference R2 URLs instead of local paths

### Phase 2: Create upload script
- Python script using boto3 to upload to R2
- Takes SKU + photos as input
- Auto-renames and uploads
- Updates Django database

### Phase 3: iPhone workflow
- Create iOS Shortcut for naming
- Set up Mac watcher or manual AirDrop + script

### Phase 4: Website auto-discovery
- Website templates check R2 for images matching the SKU pattern
- If images exist, show photo gallery on detail page
- If no images, show "Photos coming soon" placeholder

## ebay_automation Refactoring Needed
- `inventory_tracker.py` currently scans local `ebay_uploads/` — needs to also check R2
- `csv_generator.py` needs to generate R2 URLs for PicURL column instead of blank
- `config.py` IMAGE_BASE_URL already points to R2 ✅
- HTML descriptions can reference R2 URLs for images

## eBay Listing Connection
- Custom Label (SKU) in eBay = `custom_label` in database = photo filename prefix
- When creating eBay listing, the PicURL column in CSV points to R2
- Physical label on the set shelf matches the SKU
- Everything chains: shelf label → photo → R2 → database → eBay → website
