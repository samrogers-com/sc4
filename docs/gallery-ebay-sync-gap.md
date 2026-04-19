# Gallery pages showing empty despite active eBay listings

**Reported 2026-04-19 while working on Phase-3 Marketing dashboard.**

## Symptom

https://samscollectibles.net/non_sports_cards/gallery/boxes/star-wars/sw-vehicles/
shows "No items found in this category yet" but two matching eBay listings are
live and active:

- `326525596571` — 1997 Topps Star Wars Vehicles Factory Sealed Wax Box ($149.98)
- `326957386402` — 1997 Topps Star Wars Vehicles Complete Base Card Set ($34.95)

## Diagnosis

The gallery view is data-driven from the `non_sports_cards.NonSportsCards` model,
not from `ebay_manager.EbayListing`. Prod query confirms:

```
NonSportsCards.objects.filter(category__icontains='vehicle').count() == 0
```

No records match "vehicle" in any subcategory. Both SW Vehicles listings exist
on eBay and in `EbayListing` (with no SKU), but nothing connects them to the
gallery.

## Top-level NonSportsCards categories (and their row counts)

```
TV Shows: 70, Star Wars: 52, Movies: 50, Fantasy Art: 27, Star Trek: 22,
Pop Culture: 21, Historical & Military: 19, DC Comics: 19, Marvel: 19,
Sci-Fi: 12, Disney: 12, Comics: 1
```

The URL path `/gallery/boxes/star-wars/sw-vehicles/` implies a structure
(Product Type → Franchise → Title-slug) that NonSportsCards doesn't fully
support — the model has a flat `category` field and no concept of a product
sub-type (box vs. set vs. pack) or item-level slug.

## Options for fix

### Option A — Point the gallery at `EbayListing`, not `NonSportsCards`
Swap the data source so gallery pages enumerate active eBay listings filtered
by title/category fields. Simplest, but eBay titles are noisy and would need a
consistent slugging rule.

### Option B — Backfill `NonSportsCards` from active eBay listings
Add a management command that, for each active `EbayListing` without a matching
`NonSportsCards` row, creates one with inferred category/subcategory. Sam curates
labels after the fact. Preserves the existing gallery view.

### Option C — Add a test that fails when an active EbayListing has no gallery
A CI or nightly check: for every `EbayListing(status='active', ebay_item_id__isnull=False)`,
assert there's a corresponding NonSportsCards row (or other product-type model)
findable from a gallery URL. Fails loudly when the gap exists; Sam then creates
the record manually or via Option B.

## Recommendation

**C first, B second.** Sam has 65 active listings — a visibility check (Option C)
surfaces the exact list of "on eBay but not on samscollectibles.net" items. From
there, a batch backfill (Option B) populates NonSportsCards entries with inferred
categories; Sam reviews and corrects labels.

Option A is a bigger refactor and should wait until the catalog's information
architecture is rethought (likely tied into Phase-3 "Product Type" nav work).

## Not in this PR

This doc is a follow-up pointer. Today's PR ships the Marketing dashboard;
the gallery fix is a separate PR once Sam picks an option.
