---
name: sc4-listing-pipeline
description: >
  Builds a complete eBay listing for Sam's Collectibles in one go: uploads photos from a local folder under `~/Pictures/SC4-Upload/` to Cloudflare R2 (mirroring the folder path), then generates the branded HTML description with those image URLs embedded, and saves the file under `ebay_descriptions/`. Use this whenever the user wants to "build a listing for <product>", "list the X-Men 93 Skybox box", "create an eBay listing from these photos", "upload these photos and make the listing", or any phrasing that combines photos + listing for a non-sport trading card box, set, pack, wrappers, singles, or binder. Do NOT use for posters or comic books — those have their own folder conventions (use ebay-html-builder directly). Triggers strongly when the user names a folder under `~/Pictures/SC4-Upload/` or names a product whose folder lives there.
---

# SC4 Listing Pipeline

You are building a **complete eBay listing** for Sam's Collectibles in one
shot — photos uploaded, URLs captured, HTML generated, file saved.

## When to use this skill

Trigger on any phrasing that combines **photos** + **listing** for a
non-sport trading card product:

- "Build a listing for X-Men 93 Skybox S2 box"
- "Upload the photos and create the eBay listing for marvel-92"
- "Make a listing from the photos in `boxes/marvel/x-men-93-skybox-s2/`"
- "List the wrappers for star-trek-tng"

Do **not** use this for posters or comic books — they have separate
folder conventions and the `ebay-html-builder` skill handles them
directly. This skill is for non-sport cards (boxes, sets, packs,
wrappers, singles, binders).

## The folder convention (do not deviate)

Sam organizes photos under:

```
~/Pictures/SC4-Upload/<section>/<franchise>/<slug>/
```

| Section | Maps to product type |
|---|---|
| `boxes/`    | Sealed wax boxes & empty boxes |
| `sets/`     | Complete card sets |
| `packs/`    | Sealed packs |
| `wrappers/` | Wrappers (paper) |
| `singles/`  | Individual cards |
| `binders/`  | Binders |

`<franchise>` is `marvel`, `dc-comics`, `star-trek`, `movies`, etc.
`<slug>` is the lowercase hyphenated set identifier — e.g.
`x-men-93-skybox-s2`, `marvel-91-impel`, `avengers-the-1`.

The same `<franchise>/<slug>/` exists across all six sections so a single
product set has parallel folders for each photo type.

## Workflow

Walk through these steps in order. **Do not skip the confirmation step.**

### 1. Identify the folder

If the user named a product (e.g. "X-Men 93 Skybox S2"), resolve it to a
folder by looking under `~/Pictures/SC4-Upload/<section>/<franchise>/<slug>/`.
You'll usually need to ask which **section** they mean — most products
have parallel folders in `boxes/`, `sets/`, `wrappers/`, etc.

If the user pasted a path, use it directly.

### 2. Confirm the upload plan

Before uploading, run a dry-run and show the user what's about to happen:

```bash
python ~/Claude/sc4/skills/sc4-listing-pipeline/code/upload_folder.py \
    "<folder>" --dry-run
```

Show the output. The user must confirm before you proceed. Mention:
- How many files
- Where they'll land in R2 (the key prefix)
- The CDN URLs they'll get

### 3. Upload to R2

```bash
python ~/Claude/sc4/skills/sc4-listing-pipeline/code/upload_folder.py \
    "<folder>" --json
```

Capture the JSON output — `urls` is the ordered list. The script reads
credentials from 1Password (`op://sams.collectibles/Cloudflare R2 -
samscollectibles`), so the desktop app must be unlocked. If `op read`
fails, the script's error will explain — relay it to the user.

### 4. Gather product details

Ask for whatever isn't obvious from the folder name:

- **Title** (eBay title, ≤80 chars — this is a hard cap, listings fail at 81+)
- **Asking price** (USD)
- **Condition** — refer to memory `feedback_preferences.md` and use the
  right eBay condition code for the section (e.g. 7000 New/Sealed for
  boxes 261035, 4000 Ungraded + 40001 card-condition for sets 183052)
- **SKU / Custom Label** (Sam's convention — use it if known)
- **Free-form description text** — features, defects, notable cards, set
  size, year, manufacturer

If Sam pastes raw "Sell One Like This" text, treat it as the description
and extract the rest.

### 5. Generate the HTML

Delegate to the `ebay-html-builder` skill. Pass it:
- The product description text
- The image URLs from step 3
- The save target — see the path table below

The save path mirrors the folder convention:

| Section | Save under |
|---|---|
| `boxes/<franchise>/<slug>/`    | `ebay_descriptions/ns-cards/boxes/<franchise>/<slug>.html` |
| `sets/<franchise>/<slug>/`     | `ebay_descriptions/ns-cards/sets/<franchise>/<slug>.html` |
| `packs/<franchise>/<slug>/`    | `ebay_descriptions/ns-cards/packs/<franchise>/<slug>.html` |
| `wrappers/<franchise>/<slug>/` | `ebay_descriptions/ns-cards/wrappers/<franchise>/<slug>.html` |
| `singles/<franchise>/<slug>/`  | `ebay_descriptions/ns-cards/singles/<franchise>/<slug>.html` |
| `binders/<franchise>/<slug>/`  | `ebay_descriptions/ns-cards/binders/<franchise>/<slug>.html` |

Embed the photos by adding `<img src="<url>" />` tags in a gallery
section. The first image is the hero / primary photo; the rest follow in
upload order.

### 6. Show the result

Output to the user:
- Path of the saved HTML
- The image URL list (so they can paste into eBay's image-host field if
  they're not using direct upload)
- A reminder of the eBay title, condition code, category ID, and SKU

Per Sam's preferences:
- **80-char title cap** — verify before finishing.
- **eBay non-sport category IDs:**
  - 261035 = Sealed Boxes
  - 183052 = Sets · 183050 = Singles · 183053 = Packs
  - 183054 = Wrappers · 183051 = Lots · 183059 = Binders
- For sets/singles (183050, 183052), use condition 4000 + descriptor
  40001 with one of: 400010 (Near Mint+), 400011 (Excellent), 400012
  (Very Good), 400013 (Poor). Set Graded=No, Professional Grader=N/A.
- For boxes (261035), use condition 7000 (New/Factory Sealed).

## Things to watch for

- **Pre-1990 sets** are loose cards in 9-pocket sleeves — different
  shipping, different description. See `feedback_pre1990_sets.md`.
- **Ground Advantage** is the default shipping for all boxes (per
  `feedback_shipping.md`).
- **Star variants** in card sets (1-star, 2-star, mixed) must be called
  out clearly in the listing.
- **Authentication markers** — for posters this is NSS/77/21/GAU codes;
  for cards it's UPC, set code, copyright line. Mention them when present.

## What this skill does NOT do

- Generate prices or do market research — use `ebay-collectibles-automation`
  for that.
- Create eBay drafts via API — this just produces the HTML and image URLs.
  Sam pastes the result into eBay Seller Hub manually (or feeds it into
  the bulk-upload CSV pipeline in `ebay-collectibles-automation`).
- Resize, watermark, or otherwise transform images — they go up as-is.
  Add a Pillow step in `code/upload_folder.py` if that becomes desired.
