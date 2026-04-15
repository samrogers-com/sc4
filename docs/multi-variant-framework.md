# Multi-Variant Listing Framework

## Overview
Framework for creating eBay multi-variant listings where each copy/box of a product has its own photos, price, and condition. Used primarily for pre-1990 trading card boxes where condition varies between copies.

**Example:** Space 1999 Wax Box — 4 copies (Box 1-4), each photographed separately, different prices based on condition.

## Status: Steps 1-5 Complete, Steps 5-6 Remaining

### What's Built
1. ✅ **Model fields:** `group_key`, `is_variant`, `variant_name`, `parent_r2_prefix` on EbayListing
2. ✅ **Publish service:** `save_variant_drafts()` + `_save_variant_records()` for DB persistence
3. ✅ **Create form:** Multi-variant create with draft/publish buttons, per-variant price + card condition
4. ✅ **Gap report:** Checks `parent_r2_prefix` to skip R2 folders already in variant groups
5. ✅ **Add to group:** `add_variant_to_group()` for adding new boxes to existing groups

### What's Remaining
- **Variant group detail view** — show all variants in a group with photos, prices, edit capability
- **Nightly sync variant handling** — recognize variant listings by `group_key` during sync
- **Testing with Space 1999** — 4 boxes, different prices, save as drafts first

## Design Decisions

### Pricing
- Different price per variant — condition varies, price varies
- Each variant gets its own price field in the create form

### Photo Workflow
1. Sam photographs each box copy separately on iPhone
2. AirDrop to Mac
3. Manually place in correct subfolder (e.g. `space-1999/box-5/`)
4. R2 watcher uploads photos maintaining folder structure
5. Gap report detects new subfolder → offers "Add to Multi-Variant"

### R2 Folder Structure
```
trading-cards/boxes/space-1999/
    box-1/   ← Variant 1 (5 photos)
    box-2/   ← Variant 2 (6 photos)
    box-3/   ← Variant 3 (5 photos)
    box-4/   ← Variant 4 (6 photos)
```

### eBay API Flow
1. **Create inventory items** — one per variant with unique SKU
   - `PUT /sell/inventory/v1/inventory_item/{sku}`
   - Each gets its own photos, aspects (including `Box: "Box 1"`)
2. **Create inventory item group** — ties variants together
   - `PUT /sell/inventory/v1/inventory_item_group/{group_key}`
   - Defines variation aspect: `Box` with values `["Box 1", "Box 2", ...]`
3. **Create offers** — one per variant with individual pricing
   - `POST /sell/inventory/v1/offer`
4. **Publish group** — makes it a live listing
   - `POST /sell/inventory/v1/inventory_item_group/{group_key}/publish`
   - Buyer sees one listing with dropdown to select which box

### Database Schema
```
EbayListing:
    group_key = "GRP-1976SPACE1999"    # ties all variants together
    is_variant = True                   # marks as part of a group
    variant_name = "Box 1"              # display name for this variant
    parent_r2_prefix = "trading-cards/boxes/space-1999"  # for gap report matching
    sku = "1976SPACE1999-BOX-1"         # unique per variant
    price = 139.95                      # individual price
    image_urls = [...]                  # variant-specific photos
    ebay_item_id = "327..."             # shared listing ID
```

### SKU Convention
- Group key: `GRP-{TITLESLUG}` (e.g. `GRP-1976SPACE1999`)
- Variant SKU: `{SLUG}-{VARIANT_NAME}` (e.g. `1976SPACE1999-BOX-1`)

## Key Files
| File | Purpose |
|------|---------|
| `src/ebay_manager/models.py` | EbayListing variant fields |
| `src/ebay_manager/services/multi_variant.py` | Full publish + draft + add-to-group |
| `src/ebay_manager/views.py` | `multi_variant_create` view |
| `src/ebay_manager/templates/ebay_manager/multi_variant_create.html` | Create form |
| `src/ebay_manager/services/gap_report.py` | `variant_prefixes` check |

## Adding a New Variant to an Existing Group
```python
from ebay_manager.services.multi_variant import add_variant_to_group

result = add_variant_to_group(
    group_key='GRP-1976SPACE1999',
    variant={'name': 'box-5', 'display': 'Box 5', 'images': ['https://...']},
    price=129.95,
    r2_prefix='trading-cards/boxes/space-1999',
)
```

## eBay Category IDs (Non-Sport Cards)
| ID | Category |
|----|----------|
| 261035 | Sealed Trading Card Boxes |
| 183052 | Trading Card Sets |
| 183050 | Trading Card Singles |
| 183053 | Sealed Trading Card Packs |
| 183054 | Wrappers & Empty Card Boxes |
| 183059 | Card Albums, Binders & Pages |
| 183051 | Trading Card Lots |

## eBay Shipping Policies
| Policy ID | Name | Use For |
|-----------|------|---------|
| 119108501015 | NS Boxes Calculated: USPS Ground Adv | Sealed boxes |
| 282295444015 | Calculated – Trading Cards Boxes & 9 pocket sheets | Sets (raw or 9-pocket) |

## Condition Handling for Sets/Singles
Categories 183050 and 183052 require:
- Condition: 4000 (Ungraded) — maps to `USED_VERY_GOOD` enum
- Condition Descriptor 40001 (Card Condition): 400010=Near Mint+, 400011=Excellent, 400012=Very Good, 400013=Poor
- Aspects: Graded=No, Professional Grader=N/A
