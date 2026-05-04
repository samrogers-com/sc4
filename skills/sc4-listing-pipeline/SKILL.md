---
name: sc4-listing-pipeline
description: >
  Form-driven end-to-end pipeline for listing a non-sport trading card box, set, pack, wrappers, singles, or binder for Sam's Collectibles. Walks through a checklist of yes/no/short-text questions to gather sealed status, inventory quantity, NSlist URL, condition notes, and price; then uploads photos from `~/Pictures/SC4-Upload/trading-cards/<section>/<franchise>/<slug>/` to Cloudflare R2 (mirroring the folder path 1:1), generates the branded HTML eBay description, saves it under `ebay_descriptions/ns-cards/<section>/<franchise>/`, and pushes the description + price + quantity into the production `NonSportsCardsBoxes` (or sibling) Django model so the listing appears with copy on samscollectibles.net. Use this skill whenever Sam says "list X-Men 93 Skybox box", "build a listing for marvel-92", "list the wrappers for star-trek-tng", "create the eBay listing for these photos", or any phrasing that combines a card-set product with the goal of getting it onto eBay AND the website. Do NOT use for posters or comic books — those have their own folder conventions and the `ebay-html-builder` skill handles them directly.
---

# SC4 Listing Pipeline — form-driven photos→eBay+website flow

You are taking a folder of product photos and turning it into a complete
listing on **two surfaces in one shot**:

1. **eBay** — branded HTML description saved to disk + paste-ready Seller
   Hub fields (title, category, condition, item specifics)
2. **samscollectibles.net** — Django DB record created/updated so the
   product page shows description + price + inventory quantity

The flow is **driven by `AskUserQuestion`**, not free-text prose. Sam
clicks buttons; you do the work. Chain forms across multiple rounds; do
not try to gather everything in one round (the tool caps at 4 questions
per round).

---

## When to trigger

Strong triggers:

- "List X-Men 93 Skybox box"
- "List the marvel-92 set"
- "Create the eBay listing for the wrappers in marvel/x-men-93-skybox-s2"
- "Build a listing from these photos and put it on the site"
- "I have a sealed box of <set>, list it"

Refuse / redirect:

- Posters or comic books → use `ebay-html-builder` directly (different
  folder convention).
- Generating brand guidelines, voice docs, etc. → unrelated.
- "Just upload these photos" without a listing intent → use
  `tools/upload_to_r2.py` directly via Bash.

---

## The folder convention (DO NOT deviate — this is locked-in by Sam)

```
~/Pictures/SC4-Upload/trading-cards/<section>/<franchise>/<slug>/
```

**Note the `trading-cards/` segment** — it's not optional. There are
parallel `posters/` and `comic-books/` trees alongside it that this
skill ignores.

| Section    | Product type                  | eBay category | Default condition |
|------------|-------------------------------|---------------|-------------------|
| `boxes/`   | Sealed wax boxes & empty boxes| 261035        | 7000 (Sealed) for sealed; 4000 for empty |
| `sets/`    | Complete card sets            | 183052        | 4000 + descriptor 40001 |
| `packs/`   | Sealed packs                  | 183053        | 7000 |
| `wrappers/`| Wrappers (paper)              | 183054        | 4000 |
| `singles/` | Individual cards              | 183050        | 4000 + descriptor 40001 |
| `binders/` | Binders                       | 183059        | depends |

`<franchise>` is `marvel`, `dc-comics`, `star-trek`, `movies`, `tv`,
`pop-culture`, `sci-fi`, etc.

`<slug>` is the lowercase hyphenated set identifier:
`x-men-93-skybox-s2`, `marvel-91-impel`, `avengers-the-1`, etc.

The same `<franchise>/<slug>/` lives in parallel under all six sections so
a single product set has parallel folders for box / set / wrappers /
singles / packs / binders photos.

---

## Workflow — strict order

### Step 1 — Detect what's in the folder(s)

Given a product slug (e.g. `x-men-93-skybox-s2`) and franchise (e.g.
`marvel`), check **all six sections** under
`~/Pictures/SC4-Upload/trading-cards/<section>/marvel/x-men-93-skybox-s2/`
and report which contain images.

```bash
for s in boxes sets packs wrappers singles binders; do
  d=~/Pictures/SC4-Upload/trading-cards/$s/marvel/x-men-93-skybox-s2
  n=$(ls "$d" 2>/dev/null | wc -l | tr -d ' ')
  echo "$s: $n images"
done
```

Outcomes:

- **Folder doesn't exist** → create it across all six sections (`mkdir -p`),
  tell Sam to drop images in the section he wants to list, then stop.
  Do not proceed without images.
- **One section has images** → that's the section you'll list. Skip the
  "which section?" question.
- **Multiple sections have images** → ask Sam which to list (one form
  question with the populated sections as options).

### Step 2 — Form Round 1: basics

Use `AskUserQuestion` to ask up to four questions in one round:

1. **Sealed status?** (only relevant if section ∈ {boxes, packs})
   - Fully sealed - shrink intact (Recommended)
   - Sealed - shrink imperfect (some tears/scuffs but contents intact)
   - Opened / unsealed
2. **Pricing approach?**
   - Research sold comps first (Recommended) → I'll try
     `ebay-collectibles-automation` or web search; flag bot blocks
   - I'll set the price → use Other for the dollar amount
3. **Reference URL?**
   - Yes — paste in Other (Recommended) → I'll fetch set facts
   - No — research the set yourself
4. **Anything special about this specific item?** (multiSelect)
   - No, standard clean condition
   - Has shelf wear / minor scuffs
   - Has price sticker or writing
   - Has dings / dents / corner crush

If section is `sets` or `singles` etc., adapt question 1 to be relevant
(e.g. "Card condition?" with NM/EX/VG/Poor options matching eBay's
40001 descriptor values from `feedback_preferences` memory).

### Step 3 — Form Round 2: inventory, price, shipping config

After Round 1 + any research:

1. **How many do you have in inventory?** — almost always 1, but
   sometimes Sam buys multi-packs or has duplicates.
   - 1 (Recommended)
   - 2
   - 3
   - More — type the number in Other
2. **Final asking price?** — show your suggestion as the recommended
   option, plus higher and lower variants, plus Other for an exact
   number.
3. **Raw product weight?** — the box (or set, etc.) on its own,
   without packaging. The pipeline auto-adds packaging overhead per
   `feedback_packaging.md` (5oz for sealed wax boxes, 2oz for raw
   stacked, 7-8oz for 9-pocket).
   - 1 lb (typical sealed wax box) (Recommended)
   - 8 oz
   - 2 lbs (large or multi-set)
   - Other — type weight in oz or lb (e.g. "12oz" or "1.5lb")
4. **Box dimensions for shipping?** — pick the closest match; the
   pipeline uses these for eBay's calculated shipping. Custom dims
   override the `PACKAGING_SPECS` defaults (see `EbayListing` model).
   - 9 x 6 x 4 in (default for sealed wax box) (Recommended)
   - 7 x 5 x 4 in (compact box)
   - 11 x 8 x 4 in (oversize / display box)
   - Other — type as `LxWxH` inches

### Step 4 — Fetch reference data (if URL provided)

`WebFetch` the URL with a prompt that extracts:

- Year, manufacturer, base set count
- Pack/box configuration (cards per pack, packs per box)
- Insert/chase set names with odds and counts
- Key chase cards (Wolverine, Storm, etc.)
- Hologram / autograph / redemption variants
- Subset categories

Save the structured output mentally — you'll fold it into the HTML.

### Step 5 — Upload photos to R2

```bash
python3 ~/Claude/sc4/skills/sc4-listing-pipeline/code/upload_folder.py \
    ~/Pictures/SC4-Upload/trading-cards/<section>/<franchise>/<slug>/ \
    --json
```

Capture the `urls` array from the JSON output. The R2 keys mirror the
local folder path 1:1 (relative to `~/Pictures/SC4-Upload/`) so the
prefix becomes `trading-cards/<section>/<franchise>/<slug>/` and CDN
URLs are `https://media.samscollectibles.net/<that-prefix>/<filename>`.

Credentials come from 1Password via `tools/_r2_creds.py`. One Touch ID
prompt per upload run.

### Step 6 — Pricing research (optional, often blocked)

If Sam picked "Research sold comps":

1. `WebSearch` for `"<set name>" <year> <manufacturer> sealed sold ebay`
2. `WebFetch` the pricecharting.com page if it appears in results
3. `WebFetch` 1-2 active eBay listings for asking-price reference

**Fair warning**: pricecharting often returns 403; eBay product pages
often time out (60s); VCP requires login. Note this in your output and
fall back to a knowledge-based estimate. Don't burn 3+ tool calls trying
to break through bot protection.

### Step 6.5 — Build eBay item specifics via the Taxonomy API

This step is what makes a listing show up in faceted search. eBay
returns ~20-30 "aspects" per category; populating as many as possible
boosts visibility meaningfully.

Use `ebay_manager.services.taxonomy.get_item_aspects(category_id)` to
fetch the schema for the category. The function caches to disk for 7
days (cache lives at `tools/ebay_aspect_cache/category_<id>.json`), so
the API call only happens on first use per category per week.

```python
from ebay_manager.services.taxonomy import get_item_aspects, auto_fill_known
aspects = get_item_aspects("261035")            # Sealed Trading Card Boxes
required, optional = split_required_optional(aspects)
```

Auto-fill what's already known from earlier steps:

```python
known = {
    # Required (3) — fail to publish without these
    "Manufacturer":      "SkyBox",                 # from <slug> + memory
    "Franchise":         "X-Men",                  # the IP, not "Marvel"
    "Set":               "Series 2",               # JUST the series — Franchise carries "X-Men" already
    # Strongly recommended for search
    "Year Manufactured": "1993",                   # from <slug> + NSlist
    "Number of Cards":   "216",                    # 36 × 6
    "Number of Boxes":   "1",                      # from Round 2 inventory
    "Configuration":     "Sealed Wax Box",         # from sealed-status answer
    "Type":              "Trading Cards",
    "Card Size":         "Standard",               # 2.5" x 3.5"
    "Country of Origin": "United States",          # default for Sam's stock
    "Vintage":           "Yes" if year < 2000 else "No",
    "Language":          "English",
    "Material":          "Cardboard",
    # Negative aspects (explicit "No" helps filter buyers)
    "Autographed":       "No",
    "Signed By":         "Not Signed",
}
filled, unfilled = auto_fill_known(aspects, known)
```

For aspects not in `known` that came back as required or that the
pipeline thinks are high-value (Character, TV Show, Movie, Features,
Genre, Vintage), prompt Sam in **Round 3** with one form question per
unknown aspect, max 4 per round, sample values pre-populated from the
aspect's `sample_values`. Iterate rounds if more than 4 are needed.

Notes on the Franchise vs Marvel distinction: eBay's "Franchise" aspect
refers to the IP/property (X-Men, Star Wars, Star Trek). "Marvel" is
the publisher; for X-Men cards the franchise is **X-Men**, not Marvel.
Use the IP name. If you need to also surface the publisher, use
"Genre" = "Superhero" + "Manufacturer" = "SkyBox".

Aspect quirks:

- **`mode = "FREE_TEXT"`** — any string accepted (most aspects).
- **`mode = "SELECTION_ONLY"`** — value must come from `all_values`.
  Trying to send a custom value will reject the listing.
- **Multi-value aspects** (`cardinality = "MULTI"`) accept a list, not
  a comma-string. Pass `["Hologram", "Gold Foil", "Sealed"]`, not
  `"Hologram, Gold Foil, Sealed"` — the publish layer wraps single
  strings into a list automatically, but only for known multi aspects.

The final `item_specifics` dict goes onto `EbayListing.item_specifics`
in Step 9 and propagates through `create_or_update_offer` to the live
eBay listing.

### Step 7 — Generate the eBay HTML

Read the most-similar existing listing in `ebay_descriptions/ns-cards/<section>/<franchise>/`
to match Sam's branding. Key style elements:

- Outer wrapper:
  ```html
  <table align="center" style="border-spacing:0px; width:100%; max-width:100%;">
  <tbody><tr><td>
    <table background="https://media.samscollectibles.net/assets/demim_sc.jpg"
           bgcolor="#1c1c1c" border="2" cellpadding="16" cellspacing="8"
           style="width:100%; max-width:100%;">
  ```
  **Background URL must be `media.samscollectibles.net/assets/demim_sc.jpg`** —
  NOT the old `samscollectibles.s3.amazonaws.com/...` URL that appears in
  legacy files.

- Color palette: title `#87ceeb` (skyblue), subtitle `#ff9363` (orange),
  subdetails `#66e0d0` (teal), body `linen`, section headers `yellow`.

- Section structure (in order): title block → DESCRIPTION → CONDITION /
  GRADE → SHIPPING → FEEDBACK.

- Embed set facts from Step 4 in the DESCRIPTION section, with a
  bullet list of "What you get".

- Disclose every condition flag from Round 1's special-notes question
  in the CONDITION section. Be specific: don't just say "minor wear" —
  say "shrink wrap shows minor tears and the box exterior has light
  shelf wear consistent with 30+ years of careful storage" (mirroring
  the way Sam writes existing listings).

- SHIPPING section must mention USPS Ground Advantage as default (per
  `feedback_shipping.md` memory) and combined-shipping availability.

- FEEDBACK section is Sam's standard collector-shop pitch.

Do NOT embed `<img>` tags in the description. eBay handles images via
its own gallery uploaded separately. The R2 URLs are for (a) Sam to
paste into eBay's image-host field if he uses bulk-upload, and (b) the
website which auto-discovers images via the R2 path.

### Step 8 — Save HTML to disk

```
~/Claude/sc4/ebay_descriptions/ns-cards/<section>/<franchise>/<filename>.html
```

Filename convention (from existing files):
- Boxes: `<year>-<manufacturer>-<set-name>-sealed-box.html` or
  `<year>-<manufacturer>-<set-name>-empty-box.html`
- Sets: `<year>-<manufacturer>-<set-name>-set.html`
- Packs: `<year>-<manufacturer>-<set-name>-pack.html`
- Wrappers: `<year>-<manufacturer>-<set-name>-wrappers.html`

All lowercase, hyphens for spaces, no special characters.

### Step 9 — Push description + inventory to production Django

This is the step that makes the listing show up on samscollectibles.net.
Without it, the website sees only the images via R2 and renders an empty
description.

The model is `non_sports_cards.models.NonSportsCardsBoxes` for boxes
(other section types: `NonSportsCardsBaseSets`, `NonSportsCardsSpecialSets`,
`NonSportsCardsSingles`). Use `update_or_create` keyed on `title`
(unique field):

```python
from non_sports_cards.models import NonSportsCardsBoxes
b, created = NonSportsCardsBoxes.objects.update_or_create(
    title="X-Men Series 2",                # unique title (no duplicates)
    defaults=dict(
        category="Marvel",                 # franchise, capitalized
        sub_category="box",                # "box" / "base" / "chase" / "sticker"
        image_type="boxes",                # "boxes" / "sets" / "packs" / etc.
        manufacturer="SkyBox",             # from MANUFACTURERS choices
        date_manufactured="1993",          # 4-char year string
        number_of_packs_per_box=36,
        number_of_cards_per_pack=6,
        number_of_cards_in_a_set=100,
        condition="7000",                  # "7000" sealed, "4000" ungraded
        set_configuration="sealed_box",    # see SET_CONFIGURATIONS choices
        inventory_status="in_stock",
        quantity_owned=1,                  # FROM ROUND 2 FORM ANSWER
        suggested_price="119.95",          # FROM ROUND 2 FORM ANSWER
        description=description_html,      # FULL HTML from Step 7
        validation_status="enriched",
        app="ns-cards",
    ),
)
```

Push it inside the production container:

```bash
HTML_JSON=$(python3 -c "import json; print(json.dumps(open('<local-html-path>').read()))")
ssh sams-collectibles "sudo docker exec -i src-web-1 python manage.py shell" <<EOF
from non_sports_cards.models import NonSportsCardsBoxes
html = $HTML_JSON
b, created = NonSportsCardsBoxes.objects.update_or_create(
    title="X-Men Series 2",
    defaults=dict(...),
)
b.description = html
b.save(update_fields=["description"])
print(f"{'created' if created else 'updated'} id={b.id} desc_len={len(html)}")
EOF
```

(Use `json.dumps` to safely escape the HTML for the heredoc; never
embed raw HTML directly in shell commands.)

### Step 10 — Publish to eBay via the API

The pipeline does NOT paste into Seller Hub anymore — it pushes directly
through eBay's Inventory API via `ebay_manager.services.publish`.

Before publishing, create the `EbayListing` record with the full payload:

```python
from ebay_manager.models import EbayListing
from django.contrib.contenttypes.models import ContentType
from non_sports_cards.models import NonSportsCardsBoxes

box = NonSportsCardsBoxes.objects.get(slug="x-men-93-skybox-s2")  # or by title
listing, created = EbayListing.objects.update_or_create(
    title="<≤80-char title>",
    defaults=dict(
        price="<price>",
        quantity=<qty from Round 2>,
        category_id="261035",                       # or the right code per section
        condition_id="7000",                        # or 4000/etc per Round 1
        sku=None,                                   # auto-gen unless pre-1990 or unwrapped
        description_html=box.description,           # already pushed to box in Step 9
        image_urls=[<R2 URLs from Step 5>],
        item_specifics=<dict from Step 6.5>,        # 15-20 keys typically
        packaging_config="sealed_box",              # or 'raw_stacked' / '9_pocket_*'
        package_length=<from Round 2>,
        package_width=<from Round 2>,
        package_height=<from Round 2>,
        weight_lbs=<derived from Round 2 raw + overhead from feedback_packaging>,
        weight_oz=<oz remainder>,
        shipping_service="USPSGroundAdvantage",
        returns_accepted=True,
        status="draft",                             # publish_to_ebay flips to 'active'
        content_type=ContentType.objects.get_for_model(NonSportsCardsBoxes),
        object_id=box.id,
    ),
)
```

Then push:

```python
from ebay_manager.services.publish import publish_to_ebay, send_to_ebay_drafts

# Pick one based on the form's "Publish mode" answer:
result = publish_to_ebay(listing)        # goes live immediately
# OR
result = send_to_ebay_drafts(listing)    # appears in Seller Hub > Drafts
```

`publish_to_ebay` does three steps under the hood:
1. `create_inventory_item(listing)` — pushes product info, images, weight (keyed by SKU)
2. `create_or_update_offer(listing, sku)` — sets price, policies, category, item_specifics
3. `publish_offer(offer_id)` — flips to active, returns the eBay listing ID

It also updates the `EbayListing` row with `status='active'`, `ebay_item_id`, `ebay_listing_url`, and `listed_at`. The shipping policy is selected automatically from `packaging_config` per `feedback_packaging.md`.

#### Auction listings

For auction-format (instead of Buy It Now), set the format/duration/start
price on the `EbayListing` row before calling `publish_to_ebay`:

```python
from datetime import datetime
from decimal import Decimal
import pytz
from django.utils import timezone

listing.listing_format = 'AUCTION'
listing.listing_duration = 'DAYS_7'                 # DAYS_1 / 3 / 5 / 7 / 10
listing.auction_start_price = Decimal('14.95')      # falls back to .price if unset
# Optional: reserve price
# listing.auction_reserve_price = Decimal('40.00')
# Optional: scheduled start (eBay charges $0.10 to schedule)
listing.scheduled_start_time = timezone.make_aware(
    datetime(2026, 5, 3, 18, 5, 0), pytz.timezone('US/Pacific'),
)
listing.save()

publish_to_ebay(listing)
```

`availableQuantity` is forced to 1 for auctions. `listing_format` defaults
to `FIXED_PRICE` and `listing_duration` defaults to `GTC`, so existing
Buy-It-Now flows are unchanged.

After publish, **backfill the eBay URL onto the inventory record** so the
website can link out:

```python
box.ebay_listing_url = result["ebay_url"]
box.ebay_item_id = result["listing_id"]
box.inventory_status = "listed"
box.save(update_fields=["ebay_listing_url", "ebay_item_id", "inventory_status"])
```

### Step 11 — Final summary table

Output to Sam:

| Field | Value |
|---|---|
| **eBay listing URL** | `https://www.ebay.com/itm/<listing_id>` |
| **eBay item ID** | `<listing_id>` |
| **eBay offer ID** | `<offer_id>` |
| **SKU** | `SC-<pk>` (auto) or Sam's value |
| **Title** (count it) | The exact ≤80-char title |
| **Price** | `$<price>` |
| **Item specifics** | Count + a few highlights (Franchise, Manufacturer, Year, Features) |
| **Status** | `active` (live) or `pending` (drafts) |
| **DB IDs** | `EbayListing(pk=...)` GFK→ `NonSportsCardsBoxes(id=...)` |

Tell Sam to click the URL and verify everything looks right (title,
photos, description, item specifics, shipping cost). If anything's off,
he can revise via Seller Hub or by updating the EbayListing row and
calling `create_or_update_offer(listing, listing.sku)` again — the
helper handles updates as well as creates.

---

## Memory references this skill relies on

- `feedback_preferences.md` — folder convention, eBay category IDs and
  condition codes, 80-char title cap, vi editor preference
- `feedback_shipping.md` — USPS Ground Advantage default
- `feedback_listing_text.md` — approved shipping and feedback section wording
- `feedback_packaging.md` — box vs raw stacked vs 9-pocket packaging configs
- `reference_deployment.md` — how to reach the production VPS, Docker
  setup (`src-web-1` container), Ansible vault for env changes
- `feedback_pre1990_sets.md` — pre-1990 sets are loose cards in
  9-pocket sleeves; different shipping; different description language

When in doubt, consult these. Don't make up category IDs or condition
codes.

---

## Common gotchas

- **eBay 80-char title cap** is HARD — listings with 81+ chars fail to
  publish with `DataError`. Always count characters before declaring
  the title final.
- **Pre-1990 sets** are NOT sealed. They're loose cards in 9-pocket
  sleeves. Different SHIPPING section (lighter packaging, may use raw
  stacked or pages instead of box). Use condition `4000` + descriptor
  `40001`. See `feedback_pre1990_sets.md` for full conventions.
- **Star variants** (1-star, 2-star, mixed, sticker) are a separate
  axis from base/chase/insert. Topps 1977-83 Star Wars sets need them
  noted in titles and descriptions. The model has `star_variant` field
  for this.
- **Title uniqueness**: the `title` field has `unique=True`. If you
  create a second listing with the same title (e.g. multiple variants
  of "X-Men Series 2"), you'll get an IntegrityError. Disambiguate
  with `parent_set` + `series_number` + `series_color` + `star_variant`.
- **Description HTML render**: production Django renders `description`
  via `|safe` (HTML), not escaped text. Verify this assumption holds
  if you ever change template behavior.
- **Image discovery**: the website auto-finds images via R2 path
  matching, NOT via `NonSportsCardImage` records (which would be the
  obvious way). Just upload to R2 with the canonical key prefix and
  the page will render them.

## What this skill does NOT do

- **Image transformation** (resize, watermark, EXIF strip). Photos go
  up as-is. Add a Pillow step in `code/upload_folder.py` if desired.
- **Decrement inventory on sale**. The nightly `ebay_sync` command pulls
  orders into `EbayListing`/orders tables, but doesn't currently
  decrement `NonSportsCards.quantity_owned` — see
  `reference_deployment.md` for the open investigation.
- **Pricing research that always works**. pricecharting/eBay/VCP all
  have aggressive bot protection. Try once; if blocked, fall back to
  knowledge-based estimate and let Sam adjust.
- **Render the description on samscollectibles.net**. The
  `_render_gallery_detail` view in `non_sports_cards/views.py` doesn't
  query the matching `NonSportsCards` record, so descriptions sit in
  the DB but the website doesn't show them. Plan A fix (slug field +
  view + template) is queued.

## Open improvements

- Add a `--quantity` flag to `code/upload_folder.py` so it can stamp
  the inventory count somewhere (currently the skill walks the user
  through it via form).
- Capture an `--ebay-listing-url` follow-up: after Sam publishes the
  listing on eBay, run this skill again with the URL and it'll update
  the `ebay_listing_url` and `ebay_item_id` fields on the Django
  record so the website can link out.
- Move the production-push step into a Django management command
  (`python manage.py upsert_listing --slug x-men-93-skybox-s2 --json data.json`)
  so we don't depend on heredoc-shell-in-shell escaping which has bitten
  us before.
