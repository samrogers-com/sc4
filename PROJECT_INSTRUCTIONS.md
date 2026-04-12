# Project Instructions — Sam's Collectibles eBay Store

## Session Start Checklist

At the start of every new Cowork session, run this to restore GitHub SSH access:

```bash
bash /Users/samrogers/Claude/sc4/setup-ssh.sh
```

**Why this is needed:** Cowork sessions run in a sandboxed Linux environment that resets completely each time — SSH keys and config don't carry over between sessions. The script restores the key from `.cowork/ssh/` (which persists on your Mac) and writes `~/.ssh/config` with the `github-samrogers-com` host alias.

**Why git push can't run from inside Cowork:** The sandbox blocks outbound SSH connections (port 22), so `git push` must always be run from your Mac terminal at `/Users/samrogers/Claude/sc4`. Claude Code doesn't have this restriction because it runs directly on your Mac with full network access. In Cowork, always push with:

```bash
cd /Users/samrogers/Claude/sc4 && git push origin main
```

## What This Project Is

This is the operational hub for Sam's Collectibles, an eBay store selling non-sport trading cards (sealed boxes, packs, sets, singles), comic books, and posters. Everything here supports listing inventory on eBay, automating that process, and eventually managing the store through a custom dashboard.

## Hosting Stack

- **Hostinger VPS** (KVM 2: 2 CPU, 8GB RAM, 100GB disk, Ubuntu 22.04) — runs Docker containers
- **Cloudflare** — DNS, SSL termination, CDN, and DDoS protection in front of the VPS
- **Cloudflare R2** — image and media file storage (replaces S3), served via `media.samscollectibles.net`
- **Ansible** — automates all server provisioning and deployments (`ansible/` folder)

See `DEPLOYMENT.md` for the full step-by-step deployment guide, Ansible playbook usage, and Cloudflare R2 setup.

### Database Strategy
- **Local development:** SQLite (`src/db.sqlite3`) — fast, no setup needed
- **Production (VPS):** PostgreSQL 13 in Docker container — proper concurrency, full-text search, ACID
- **Schema sync:** Django migrations keep both databases schema-identical
- **Data flow:** Real data lives in Postgres. To seed dev from production: `manage.py dumpdata > fixture.json` on prod, then `manage.py loaddata fixture.json` locally
- The `USE_POSTGRES` env var controls which database Django uses (set in `.env.production`)

### Deployment Readiness Checklist
Before first deploy, you need to:
1. Create `ansible/group_vars/vault.yml` from `vault.yml.example` with real secrets
2. Encrypt it: `ansible-vault encrypt ansible/group_vars/vault.yml`
3. Set up SSH key for the `sam` user on the VPS
4. Run: `ansible-playbook ansible/playbooks/provision.yml -u root --ask-vault-pass`

## Non-Sports Cards Inventory Pipeline

The non-sports cards inventory is being built through a multi-stage CSV-to-database workflow:

1. **Source CSV** (`src/non_sports_cards/static/nstc-core-10-29-22.csv`) — Original printed inventory list
2. **Annotated CSV** (`src/non_sports_cards/static/nstc-core-10-29-22-annotated.csv`) — Handwritten inventory counts and type classifications (box/base/chase/sticker/insert) added from physical review of printed sheets
3. **Enriched CSV** (`src/non_sports_cards/static/nstc-core-10-29-22-enriched.csv`) — Machine-enriched from nslists.com with manufacturer, year, pack counts, set sizes, and chase card details (scheduled task runs this)
4. **Flagged items** (`src/non_sports_cards/static/nstc-flagged-items.csv`) — Items with uncertain data needing manual verification
5. **Margin notes** (`src/non_sports_cards/static/nstc-margin-notes.csv`) — Handwritten margin notes not yet added due to insufficient info
6. **Postgres import** — Final validated data imported into Django models via `load_non_sports_cards` management command

### Django Model: validation_status field
The `NonSportsCards` model includes a `validation_status` field to track data quality:
- `unvalidated` — Default, freshly imported or unmatched by enrichment
- `enriched` — Machine-enriched from nslists.com (needs human review)
- `verified` — Human-reviewed and confirmed accurate

This field is inherited by all child models (Boxes, BaseSets, SpecialSets) and is filterable in Django admin.

### VPS Co-hosting
The Hostinger VPS (KVM 2: 2 CPU, 8GB RAM, 100GB disk) hosts both:
- **Adventures of Lucy Lu** (bassethoundbooks.com) — Django/Gunicorn on port 8000, deployed from `/Users/samrogers/Developer/adventuresoflucylu.com`
- **Sam's Collectibles** (samscollectibles.net) — Django/Gunicorn on port 8001, deployed from this repo

Both sites share the VPS with separate Nginx server blocks, Docker networks, and databases.

## Movie Posters Workflow

The movie_posters app supports a photo-to-listing pipeline:

1. **Photograph** the poster
2. **Identify** — Claude reads the image, identifies title, artist, edition, size, condition
3. **Cross-reference** — Compare against SW/movie poster databases for details (print type, country of origin, rarity)
4. **Generate eBay listing** — Create branded HTML description via `ebay-html-builder` skill
5. **Link back** — Store `ebay_listing_url` and `ebay_item_id` on the Django model for tracking

### MoviePosters model fields
Core: `title`, `year`, `franchise`, `artist`, `description`
Poster specifics: `poster_type` (original/reissue/advance/etc.), `size` (one sheet/half sheet/etc.), `dimensions`, `country_of_origin`, `condition`, `linen_backed`, `rolled_or_folded`
eBay: `ebay_listing_url`, `ebay_item_id`
Tracking: `validation_status` (unvalidated/enriched/verified)
Images: `MoviePosterImage` model with S3/R2 paths (front, back, detail, other)

### eBay integration (both apps)
Both `NonSportsCards` and `MoviePosters` have `ebay_listing_url` and `ebay_item_id` fields for linking Django records to live eBay listings.

## Key Folders

- `ebay_automation/` — Python pipeline that tracks inventory, looks up sold prices, and generates bulk-upload CSVs for eBay Seller Hub. See `ebay_automation/PLAN.md` for the full workflow, column reference, and category/condition mappings.
- `ebay_descriptions/` — Branded HTML listing descriptions organized by product type and franchise (boxes, packs, sets, singles, comics). Generated using the `ebay-html-builder` skill.
- `ebay_uploads/` — Product photos organized by type (NS-Boxes, NS-Packs, NS-Singles, NS-Binders, NS-cvs-sets).
- `ebay_downloads/` — Reference images and listing data downloaded from eBay.
- `csvs/` — Active listing reports from Seller Hub, upload CSVs, and templates.
- `src/` — Django app (Sam's Collectibles website) with Dockerfiles and production docker-compose. Foundation for the store dashboard.
- `ansible/` — Ansible playbooks and roles for provisioning the Hostinger VPS and deploying the app. Contains encrypted secrets via ansible-vault.
- `skills/` — Custom Cowork skill files for eBay automation.
- `tools/` — Standalone utility scripts (R2 image tools, eBay API tools, OAuth setup). See below for full list.

## Tools Directory (`tools/`)

### R2 / Image Tools (deployed, working)
| Tool | Purpose |
|------|---------|
| `tools/r2_tree.py` | Tree view of R2 bucket contents |
| `tools/upload_to_r2.py` | Upload images to R2 with naming conventions |
| `tools/r2_watcher.py` | Auto-upload folder watcher (launchd service) |
| `tools/migrate_uploads_to_r2.py` | Bulk migrate local files to R2 |
| `tools/test_r2_setup.py` | Test R2 connectivity and CDN |

### eBay API Tools (framework built, pending User OAuth setup)
| Tool | Purpose | Status |
|------|---------|--------|
| `tools/ebay_oauth_setup.py` | User OAuth authorization flow | Ready -- Sam needs to run browser auth |
| `tools/ebay_sold_tracker.py` | Pull sold orders to SQLite database | Ready -- needs User OAuth token |
| `tools/ebay_nightly_sync.py` | Cron/scheduled wrapper for nightly order sync | Ready -- needs User OAuth token |
| `tools/ebay_best_sellers.py` | Rank inventory by sell potential using Browse API | Working -- uses Client Credentials |

### Data Files (gitignored or auto-generated)
| File | Purpose |
|------|---------|
| `tools/ebay_user_token.json` | User OAuth tokens (gitignored) |
| `tools/data/sold_history.db` | SQLite database of sold orders |
| `tools/data/market_cache.json` | Cached Browse API market data |
| `tools/data/nightly_sync.log` | Log output from nightly sync |

See `docs/ebay-api-guide.md` for full API documentation, authentication setup, and environment variables.

## How Listings Get Created

Listings are created two ways:

1. **Manual** — Paste product text into Cowork and use the `ebay-html-builder` skill to generate a branded HTML description. Upload to eBay manually or via CSV.
2. **Automated** — Run the three-phase pipeline in `ebay_automation/`:
   - `inventory_tracker.py` — Cross-references photos, HTML descriptions, and active eBay listings to find what's ready to list.
   - `sold_price_lookup.py` — Queries eBay's Finding API for recent sold prices to set competitive pricing.
   - `csv_generator.py` — Produces bulk-upload CSVs compatible with Seller Hub Reports.

## How Deployment Works

The app is deployed to Hostinger via Ansible — not manually. The two commands to know:

```bash
# First-time server setup (run once on a new VPS)
ansible-playbook ansible/playbooks/provision.yml -u root --ask-vault-pass

# Deploy a code update
ansible-playbook ansible/playbooks/deploy.yml --ask-vault-pass
```

Secrets (API keys, passwords) are stored encrypted in `ansible/group_vars/vault.yml` using ansible-vault. Never commit an unencrypted vault file.

## Movie Posters — Provenance & Authentication Notes

**Collection provenance:** Almost all posters were purchased between 1983–1990 (after ROTJ release) from 1–2 reputable poster dealers. This predates the known bootleg era (mid-to-late 1980s onward), which is a strong authenticity selling point.

**Key authentication details to ALWAYS include in listings:**
- **Star Wars Style B Teaser (1977):** One of the most commonly bootlegged SW posters. The **77/21 code** and **GAU logo** on the bottom border confirm authenticity. Always highlight these in eBay descriptions.
- **Empire Strikes Back Advance (1980):** The "Gone with the Wind" style with **800001 NSS code**. This poster was **recalled from theaters** because it omitted Billy Dee Williams — making originals rarer. Always mention the recall history.
- **General rule:** For every poster, research and include authentication markers (NSS codes, printer codes, studio logos, paper stock details) in both eBay listings and website descriptions. This differentiates from bootleg sellers.
- **Bootleg controversy:** There is at least one major eBay poster seller who actively raises bootleg concerns. Proactively providing authentication evidence (codes, provenance, purchase timeline) neutralizes this.

**Condition terminology for posters:**
- Rolled vs. Folded (all pre-1980s one-sheets were shipped folded — this is expected, not a defect)
- Linen-backed = professionally mounted for preservation (increases value)
- Note: tear, pinholes, tape residue, foxing, fading in condition descriptions

## Comic Books Inventory

### Star Wars Marvel (#1-107, 1977-1986)
- 4 complete sets of #1-107 (best condition copies)
- 100s of additional individual issues
- Key issues sold individually, complete sets as single listings, common issues in lots
- Django models: `StarWarsMarvelComic` with condition grading, eBay fields, validation_status

### Star Wars Dark Horse (1990s)
- 300-600 issues across multiple series
- Series include: Dark Empire, Crimson Empire, Tales of the Jedi, X-Wing Rogue Squadron, Classic Star Wars, and others
- Django model: `StarWarsDarkHorseComic`

### eBay automation folder structure
```
ebay_uploads/Comics-SW-Marvel/{complete-sets,key-issues,lots}/
ebay_uploads/Comics-SW-DarkHorse/{dark-empire,crimson-empire,tales-of-the-jedi,...}/
ebay_uploads/Posters/{Star Wars,Marvel,Other}/
```

## eBay API Integration

### Current State
- **Browse API (Client Credentials):** Working. Used for active listing price lookups and market analysis.
- **Fulfillment API (User OAuth):** Framework built, pending Sam's browser authorization.
- **Trading API (User OAuth):** Planned for direct listing creation (bypass CSV upload).

### Setup Remaining
1. Sam runs `python tools/ebay_oauth_setup.py` in terminal
2. Logs into eBay in the browser, clicks "Agree"
3. Token saved automatically to `tools/ebay_user_token.json`
4. Then `python tools/ebay_sold_tracker.py --days 30` will work

See `docs/ebay-api-guide.md` for complete API documentation.

## Cloudflare R2 Image Hosting

R2 migration is complete. 326 images uploaded to the `samscollectibles` bucket, served via `media.samscollectibles.net`.

Key tools:
- `tools/r2_watcher.py` -- watches `~/Pictures/SC4-Upload/` and auto-uploads to R2
- `tools/upload_to_r2.py` -- manual uploads with naming conventions
- `tools/r2_tree.py` -- view R2 bucket structure

The watcher supports `--delete-after-upload` to clean up local files after successful upload.

See `docs/r2-tools-reference.md` for full documentation.

## What I Need Help With

- Creating and refining HTML listing descriptions for new products
- Running and improving the automation pipeline
- Building a store management dashboard (tracking sales, active listings, inventory status, pricing)
- Generating and uploading bulk listing CSVs
- Researching sold prices and market trends for collectibles
- Setting up User OAuth for eBay seller APIs (sold history, order management)
- Completing the non-sports cards inventory enrichment from nslists.com and importing into Postgres
- Deploying Sam's Collectibles alongside Lucy Lu on the Hostinger VPS

## Important Notes

- Always refer to `ebay_automation/PLAN.md` before modifying the automation scripts — it documents the full strategy, eBay CSV column reference, category numbers, and condition IDs.
- HTML descriptions follow the Sam's Collectibles brand style. Use the `ebay-html-builder` skill to maintain consistency.
- The `ebay-collectibles-automation` skill can run the full pipeline end-to-end.
- eBay listing HTML files still reference the old S3 image URLs — these will be updated when the R2 migration is completed.
- `ansible/group_vars/vault.yml` contains encrypted secrets. To edit: `ansible-vault edit ansible/group_vars/vault.yml`.
