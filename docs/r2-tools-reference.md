# R2 & Image Tools Reference

## Quick Reference

| Tool | What it does |
|------|-------------|
| `tools/r2_tree.py` | Tree view of R2 bucket (like Unix `tree`) |
| `tools/upload_to_r2.py` | Upload images to R2 with naming conventions |
| `tools/r2_watcher.py` | Auto-upload folder watcher |
| `tools/migrate_uploads_to_r2.py` | Bulk migrate local files to R2 |
| `tools/test_r2_setup.py` | Test R2 connectivity and CDN |
| `aws s3 ... --profile r2` | AWS CLI for R2 (S3-compatible) |

## R2 Tree Viewer (`tools/r2_tree.py`)

```bash
# Full tree (all files and folders)
/usr/bin/python3 tools/r2_tree.py

# Summary only (folders + file counts, no individual files)
/usr/bin/python3 tools/r2_tree.py --summary

# Subtree for a specific path
/usr/bin/python3 tools/r2_tree.py trading-cards/boxes/star-wars/

# Limit depth (e.g., 2 levels deep)
/usr/bin/python3 tools/r2_tree.py --depth 2

# JSON output (pipe to jq, etc)
/usr/bin/python3 tools/r2_tree.py --json

# Combine options
/usr/bin/python3 tools/r2_tree.py trading-cards/sets/ --depth 3 --summary
```

## Upload to R2 (`tools/upload_to_r2.py`)

```bash
# Upload trading card set photos with SKU naming
/usr/bin/python3 tools/upload_to_r2.py \
  --sku 101 \
  --category star-wars/anh/series-1 \
  --type 1star \
  photos/*.jpg

# Upload to a specific R2 path
/usr/bin/python3 tools/upload_to_r2.py \
  --dest posters/star-wars/ \
  poster-front.jpg

# Upload with custom filename
/usr/bin/python3 tools/upload_to_r2.py \
  --dest posters/star-wars/ \
  --name sw-anh-style-a-front.jpg \
  IMG_1234.jpg

# List R2 contents under a path
/usr/bin/python3 tools/upload_to_r2.py --list trading-cards/

# Migrate all local ebay_uploads to R2
/usr/bin/python3 tools/upload_to_r2.py --migrate-all
```

## Folder Watcher (`tools/r2_watcher.py`)

```bash
# Create the watch directory structure
mkdir -p ~/Pictures/SC4-Upload/star-wars/anh/series-1/1star-101
mkdir -p ~/Pictures/SC4-Upload/posters/star-wars
mkdir -p ~/Pictures/SC4-Upload/comic-books/star-wars-marvel

# Start watching (continuous mode — runs until Ctrl+C)
/usr/bin/python3 tools/r2_watcher.py --watch ~/Pictures/SC4-Upload/

# Process existing files once and exit
/usr/bin/python3 tools/r2_watcher.py --once ~/Pictures/SC4-Upload/

# Dry run (see what would happen without uploading)
/usr/bin/python3 tools/r2_watcher.py --once --dry-run ~/Pictures/SC4-Upload/

# Install as auto-start service (runs on Mac login)
cp tools/com.samscollectibles.r2-watcher.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.samscollectibles.r2-watcher.plist

# Uninstall auto-start
launchctl unload ~/Library/LaunchAgents/com.samscollectibles.r2-watcher.plist
rm ~/Library/LaunchAgents/com.samscollectibles.r2-watcher.plist
```

### Watcher Folder Convention
Drop photos into folders that match this structure:
```
~/Pictures/SC4-Upload/
├── star-wars/anh/series-1/1star-101/    ← photos auto-renamed to 1star-101-p01.jpg
├── star-wars/anh/series-2/2star-105/    ← photos auto-renamed to 2star-105-p01.jpg
├── posters/star-wars/                   ← keeps original filename
└── comic-books/star-wars-marvel/issue-001/  ← keeps original filename
```

## AWS CLI for R2

```bash
# First-time setup (run once)
aws configure --profile r2
# Access Key ID: 1906b346fcf1a6779ee4cdd19a27fc0b
# Secret Access Key: (your key)
# Region: auto
# Output: json

# Add endpoint to config (run once)
echo '
[profile r2]
endpoint_url = https://c2fa931a6f5d02d3c12552d68c2c379b.r2.cloudflarestorage.com' >> ~/.aws/config

# List top-level folders
aws s3 ls s3://samscollectibles/ --profile r2

# List all files recursively
aws s3 ls s3://samscollectibles/ --recursive --profile r2

# List specific path
aws s3 ls s3://samscollectibles/trading-cards/boxes/star-wars/ --profile r2

# Copy a file to R2
aws s3 cp photo.jpg s3://samscollectibles/posters/star-wars/photo.jpg --profile r2

# Copy entire folder to R2
aws s3 cp ./photos/ s3://samscollectibles/trading-cards/sets/starwars/ --recursive --profile r2

# Download from R2
aws s3 cp s3://samscollectibles/trading-cards/sets/starwars/sw-anh-s2base-1s101-p01.jpg ./download.jpg --profile r2

# Delete a file from R2
aws s3 rm s3://samscollectibles/path/to/file.jpg --profile r2

# Sync local folder to R2 (only uploads new/changed files)
aws s3 sync ./ebay_uploads/ s3://samscollectibles/ebay-uploads/ --profile r2
```

## Migration Script (`tools/migrate_uploads_to_r2.py`)

```bash
# Dry run — see what would be uploaded without doing it
/usr/bin/python3 tools/migrate_uploads_to_r2.py --dry-run

# Run actual migration
/usr/bin/python3 tools/migrate_uploads_to_r2.py

# Migration log saved to: tools/migration_log.txt
```

## Test Suite (`tools/test_r2_setup.py`)

```bash
# Run all R2 connectivity and CDN tests
/usr/bin/python3 tools/test_r2_setup.py
```

## R2 Bucket Details

| Setting | Value |
|---------|-------|
| Bucket name | samscollectibles |
| CDN domain | media.samscollectibles.net |
| R2 endpoint | https://c2fa931a6f5d02d3c12552d68c2c379b.r2.cloudflarestorage.com |
| Access Key | 1906b346fcf1a6779ee4cdd19a27fc0b |
| Region | auto |

## File Naming Conventions

### Trading Card Sets
`{star_variant}-{sku}-p{page_number}.jpg`
- `1star-101-p01.jpg` — SKU 101, 1-star set, photo 1
- `mixed-115-p03.jpg` — SKU 115, mixed star set, photo 3
- `stickers-120-p01.jpg` — SKU 120, sticker set, photo 1

### Comic Books
`{view}-{issue_number}.jpg`
- `front-001.jpg` — Issue #1 front cover
- `back-001.jpg` — Issue #1 back cover

### Posters
`{movie}-{style}-{view}.jpg`
- `sw-anh-style-a-front.jpg`
- `sw-esb-advance-gwtw-front.jpg`

## Photo Workflow (iPhone → R2 → Website)

1. Write SKU number on physical item (e.g., "101")
2. Photograph on iPhone
3. AirDrop to Mac → `~/Pictures/SC4-Upload/{category}/{path}/{type}-{sku}/`
4. Watcher auto-renames and uploads to R2
5. Image appears at `https://media.samscollectibles.net/trading-cards/{path}/{type}-{sku}-p01.jpg`
6. Website gallery page automatically shows the new images
