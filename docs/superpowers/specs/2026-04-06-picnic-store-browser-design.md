# Picnic Store Browser & Synthetic Barcode Enrichment — Design

**Date:** 2026-04-06
**Status:** Approved
**Depends on:** 2026-04-05-auto-restock-design.md (tracked_products table, `check_and_enqueue` service)

## Problem

Auto-Restock (shipped) lets users subscribe a product to automatic reordering, but the subscribe entry point is the inventory row — which requires the product to already exist in inventory, which requires a previous physical scan. This creates a chicken-and-egg gap for products the user *wants* to auto-reorder but has never scanned yet (e.g., a new staple they plan to stock).

The user wants a Picnic store browser: search the Picnic catalog, add items to the shopping list or subscribe for auto-reorder, all without needing a physical product in hand.

## Core Constraint: No Reliable Picnic→EAN Reverse Lookup

Investigation of `python-picnic-api2` confirmed:

- `get_article_by_gtin(ean)` exists — it abuses the consumer QR deep-link `https://picnic.app/{country}/qr/gtin/{ean}` and follows redirects to extract an article_id. One direction only.
- `get_article(article_id)` returns only `{name, producer, id}` — no `gtin`/`ean` field.
- `search(term)` results also contain no EAN field.
- Grep across the entire library: `"gtin"` appears exactly once (in the above method). No reverse mechanism exists.

Forward OpenFoodFacts lookups are risky (fuzzy name matching, silent wrong matches).

**Conclusion:** When subscribing from the store browser, we cannot obtain the real EAN. We need a placeholder.

## Solution Overview

1. **New "Picnic Store" page** — search Picnic, results render as cards with image/name/unit/price, per-card actions: *Add to shopping list* and *Subscribe*.
2. **Synthetic barcode convention** — subscribing from the store creates a `tracked_products` row with `barcode = "picnic:<picnic_id>"`. The rule lies dormant until enriched.
3. **Enrichment on delivery import** — when a Picnic delivery arrives, `PicnicImportPage` shows a *"Barcode nachpflegen"* button next to line items that match a synth-tracked rule. One scan promotes the row's PK from synth to real EAN.
4. **Enrichment fallback on Nachbestellungen page** — synth rules also surface a *"Barcode scannen"* button on `TrackedProductsPage` for out-of-band enrichment (user never orders the product but does scan one).
5. **PK collision on promotion** — if the promoted real EAN already exists as a `tracked_products` PK, merge with "promoted synth wins" semantics (delete the existing real row, the synth row's min/target survive).

**No schema changes.** `tracked_products` stays as-is from auto-restock (`barcode` PK, `picnic_id` NOT NULL).

## Architecture

### Components

**Frontend:**
- `PicnicStorePage` (new route `/picnic-store`) — search + result grid
- `SubscribeDialog` (new component) — min/target form, wraps existing `TrackedProductForm` validation
- `PicnicImportPage` (modified) — per-item enrichment buttons
- `TrackedProductsPage` (modified) — synth-row enrichment buttons + visual indicator

**Backend:**
- `POST /api/tracked-products` (modified) — accepts `barcode: null` and generates `f"picnic:{picnic_id}"` server-side
- `POST /api/tracked-products/{barcode}/promote-barcode` (new) — promotes synth PK to real EAN, handles merge
- `app/services/tracked_products.py` (new, small) — `is_synthetic_barcode()` helper + promote logic

### Data Flow: Subscribe from Store

```
User enters "milch" in PicnicStorePage
  → GET /api/picnic/search?q=milch
  → render cards (existing PicnicSearchResult schema: picnic_id, name, unit_quantity, image_id, price_cents)
  → user clicks "Abonnieren" on card
  → SubscribeDialog opens, user enters min=1, target=3
  → POST /api/tracked-products { picnic_id: "s100", name: "Ja! Vollmilch 1 L", min_quantity: 1, target_quantity: 3, barcode: null }
  → backend: effective_barcode = "picnic:s100", INSERT
  → row exists, rule dormant (no inventory scan-out path hits it)
```

### Data Flow: Enrichment on Delivery Import

```
Picnic delivers, user opens PicnicImportPage
  → import fetch returns line items, each with picnic_id
  → frontend: load tracked_products list, build Map<picnic_id, TrackedProduct>
  → for each line item: if tracked[item.picnic_id] exists AND isSynthetic(tracked.barcode)
      → render badge "Abonniert · Barcode fehlt" + button "Barcode nachpflegen"
  → user clicks → dialog with focused scanner input → user scans physical package
  → POST /api/tracked-products/picnic:s100/promote-barcode { new_barcode: "4014400900057" }
  → backend:
      - load synth row (404 if missing, 400 if not synthetic)
      - check if "4014400900057" already exists in tracked_products
        - NO  → UPDATE row SET barcode = '4014400900057'
        - YES → DELETE existing '4014400900057' row, UPDATE synth row SET barcode = '4014400900057'
      - commit, return promoted row
  → toast, refetch tracked list
  → from now on, scan-out of 4014400900057 triggers check_and_enqueue normally
```

### Data Flow: Enrichment Fallback (TrackedProductsPage)

Identical to above but entry point is the Nachbestellungen page — same endpoint, same dialog. Covers the case where a subscribed product is never ordered via Picnic (e.g., user buys it at a physical store).

## Data Model

**No DDL changes.** Auto-restock's `tracked_products` table is sufficient.

**Convention (Python code, not DB):**
```python
# app/services/tracked_products.py
SYNTHETIC_BARCODE_PREFIX = "picnic:"

def is_synthetic_barcode(barcode: str) -> bool:
    return barcode.startswith(SYNTHETIC_BARCODE_PREFIX)

def make_synthetic_barcode(picnic_id: str) -> str:
    return f"{SYNTHETIC_BARCODE_PREFIX}{picnic_id}"
```

**Index verification:** The promote operation and the frontend enrichment lookup both need `WHERE picnic_id = ?`. If auto-restock migration did not add an index on `picnic_id`, add it in a new migration. (To verify during implementation.)

## API

### Modified: `POST /api/tracked-products`

**Request:** `TrackedProductCreate`
```json
{
  "barcode": null | "string",     // now optional
  "picnic_id": "string",          // NOT NULL in DB, so required
  "name": "string",
  "min_quantity": 1,
  "target_quantity": 3
}
```

**Behavior:**
- If `barcode is None`: server sets `effective_barcode = make_synthetic_barcode(picnic_id)`
- If `barcode` provided: used as-is (existing behavior from auto-restock)
- Insert row with `effective_barcode` as PK

**Response:** `TrackedProductRead` (unchanged), `effective_barcode` visible as `barcode`

**Errors:**
- 409 on PK collision (synth OR real) — user already subscribed this picnic_id or this EAN
- 422 on missing `picnic_id` when `barcode` is null (enforced by NOT NULL)
- 422 on `target_quantity <= min_quantity` (existing validation)

### New: `POST /api/tracked-products/{barcode}/promote-barcode`

**Path params:** `barcode` — the current (synth) PK, e.g. `picnic:s100`. URL-encode the colon.

**Request:**
```json
{ "new_barcode": "4014400900057" }
```

**Behavior:**
1. Load row by PK `barcode`. 404 if missing.
2. If `not is_synthetic_barcode(row.barcode)` → 400 `"row is already a real barcode"`
3. If `is_synthetic_barcode(new_barcode)` → 400 `"new_barcode must be a real EAN"`
4. Check if `new_barcode` already exists in `tracked_products`:
   - **Collision:** DELETE the existing real row. UPDATE synth row `barcode = new_barcode`. The synth row's `min_quantity`, `target_quantity`, `name`, `picnic_id` survive.
   - **No collision:** UPDATE synth row `barcode = new_barcode`.
5. Commit. Return `{ "tracked": TrackedProductRead, "merged": bool }` — `merged: true` iff the no-collision path was NOT taken.

**Rationale for "promoted wins" merge:** The user's most recent intent (the subscribe action that created the synth row) should take precedence. The existing real row is assumed to be stale — if it had the user's current min/target, they wouldn't have created a new synth row.

**Errors:**
- 404 — synth row not found
- 400 — row is not synthetic, or `new_barcode` is synthetic, or `new_barcode` is empty/invalid format
- 409 — defensive for unexpected integrity errors

### Unchanged: `GET /api/picnic/search`

Already returns `PicnicSearchResult[]` with `picnic_id, name, unit_quantity, image_id, price_cents`. No changes.

### Unchanged: `POST /api/picnic/shopping-list`

Used by the "In Einkaufsliste" card action. No changes.

## Frontend

### New: `src/pages/PicnicStorePage.tsx`

```
- Gate on usePicnicStatus() — redirect to /picnic-login if needs_login, show disabled state if !enabled
- usePicnicSearch() — existing hook, returns { results, loading, search }
- useTrackedProducts() — existing hook from auto-restock, for "already subscribed" badge on cards
- Local state: selectedForSubscribe: PicnicSearchResult | null
- Layout:
    <Stack>
      <TextField onChange={debounced search} placeholder="Picnic durchsuchen..." />
      <Grid container>
        {results.map(r => <StoreResultCard result={r} onSubscribe={setSelectedForSubscribe} />)}
      </Grid>
    </Stack>
- <SubscribeDialog product={selectedForSubscribe} onClose={...} onSubmitted={refetch tracked} />
```

### New: `src/components/StoreResultCard.tsx`

- Props: `result: PicnicSearchResult`, `alreadySubscribed: boolean`, `onSubscribe: (result) => void`
- MUI Card with:
  - CardMedia: image via existing `buildPicnicImageUrl(image_id)` helper
  - CardContent: name, unit_quantity (subtitle), formatted price
  - CardActions:
    - Button "In Einkaufsliste" → calls `addShoppingListItem({picnic_id, name, quantity: 1})`, success toast
    - Button "Abonnieren" → `onSubscribe(result)`; disabled with "Abonniert" label if `alreadySubscribed`

### New: `src/components/SubscribeDialog.tsx`

- Props: `product: {picnic_id, name} | null`, `onClose: () => void`, `onSubmitted: () => void`
- Dialog opens when `product !== null`
- Form: two TextFields (`min_quantity`, `target_quantity`), client-side validation `target > min >= 1`
- Submit: `createTrackedProduct({ picnic_id: product.picnic_id, name: product.name, min_quantity, target_quantity, barcode: null })`
- On success: toast, `onSubmitted()`, `onClose()`
- Handles 409 gracefully (toast "Bereits abonniert")

### Modified: `src/pages/PicnicImportPage.tsx`

Add per-line-item enrichment UI:
- `const trackedByPicnicId = useMemo(() => Object.fromEntries(tracked.map(t => [t.picnic_id, t])), [tracked])`
- For each line item, check `const matched = trackedByPicnicId[item.picnic_id]`
- If `matched && isSynthetic(matched.barcode)` → render:
  - Chip "Abonniert · Barcode fehlt" (warning color)
  - Button "Barcode nachpflegen" → opens `<PromoteBarcodeDialog tracked={matched} />`

### Modified: `src/pages/TrackedProductsPage.tsx`

For rows where `isSynthetic(row.barcode)`:
- Add Chip "Picnic-only" (info color) to visually differentiate
- Add secondary action button "Barcode scannen" → opens `<PromoteBarcodeDialog tracked={row} />`

### New: `src/components/PromoteBarcodeDialog.tsx`

- Props: `tracked: TrackedProduct | null`, `onClose`, `onSubmitted`
- Simple dialog with auto-focused text input (scanners submit on Enter)
- Client-side: reject empty, reject `picnic:*` format
- Submit: `promoteTrackedProductBarcode(tracked.barcode, newBarcode)`
- On success: toast ("Barcode übernommen" or "Barcode übernommen · bestehende Regel ersetzt" depending on whether merge occurred — backend response can include a flag), refetch

### Navigation

New Navbar entry "Picnic Store" (gated on `picnicStatus.enabled`). Position: near existing Picnic-related entries (after "Nachbestellungen" or grouped with "Einkaufsliste"/"Picnic Import").

### API Client Changes (`src/api/client.ts`)

- `createTrackedProduct` signature: `barcode` becomes `string | null | undefined`
- New: `promoteTrackedProductBarcode(synthBarcode: string, newBarcode: string): Promise<{ tracked: TrackedProduct, merged: boolean }>`

## Error Handling

| Scenario | Backend Response | Frontend Handling |
|---|---|---|
| Picnic unreachable during search | 503 from `/picnic/search` | Toast "Picnic nicht erreichbar", empty state |
| Subscribe duplicate (same picnic_id twice) | 409 on INSERT (synth PK collision) | Toast "Bereits abonniert", close dialog |
| Subscribe while not logged in | 401/403 from `_require_enabled` | Redirect to `/picnic-login` |
| Promote: synth row deleted between load and submit | 404 | Toast, refetch tracked list |
| Promote: EAN already tracked (merge case) | 200 with `merged: true` | Toast "Barcode übernommen · bestehende Regel ersetzt" |
| Promote: user enters synthetic format as new_barcode | 400 | Inline validation catches it first |
| Promote: user enters empty string | 400 | Inline validation catches it first |
| User physically scans `picnic:s100` as a real barcode in scan-out | Guard in scan-out router: 400 | Rare; defensive |
| Add-to-shopping-list from store while shopping list sync broken | 500 from existing endpoint | Existing error handling |

## Testing

### Backend

**`tests/test_tracked_products.py` (extend):**
- `POST /tracked-products` with `barcode=null` and `picnic_id="s100"` → created row has `barcode == "picnic:s100"`
- `POST /tracked-products` twice with same picnic_id and `barcode=null` → second returns 409
- `POST /tracked-products` with `barcode=null` missing picnic_id → 422
- `POST /tracked-products` with explicit real `barcode` (unchanged path) → still works
- `POST /tracked-products` with `target_quantity <= min_quantity` (unchanged) → 422

**`tests/test_promote_barcode.py` (new):**
- Happy path: subscribe synth `picnic:s100`, promote to `4014400900057` with no collision → row PK updated, response echoes new barcode
- Merge path: create real row `4014400900057` with some min/target, then create synth `picnic:s100` with different min/target, promote synth → real row deleted, synth row's min/target survive under new PK
- 400 on promoting non-synthetic row
- 400 on new_barcode that is synthetic format
- 400 on empty new_barcode
- 404 on promoting nonexistent synth barcode
- Post-promote integration: scan-out of the promoted barcode triggers `check_and_enqueue` (verifies the rule is now active)

**Existing auto-restock tests (`test_restock_service.py`, etc.):** must still pass unchanged.

### Frontend

**`PicnicStorePage.test.tsx` (new):**
- Search renders cards with image, name, price
- "Abonniert" badge shown for picnic_ids already in tracked list
- "In Einkaufsliste" click calls `addShoppingListItem`, shows success toast
- "Abonnieren" click opens SubscribeDialog
- SubscribeDialog submit calls `createTrackedProduct` with `barcode: null`
- Empty search shows empty state
- Error state when search fails

**`SubscribeDialog.test.tsx` (new):**
- Validation: target must be > min
- Submit calls API with correct payload
- 409 response shows "Bereits abonniert" toast

**`PromoteBarcodeDialog.test.tsx` (new):**
- Submit calls `promoteTrackedProductBarcode(synthBarcode, input)`
- Inline validation rejects `picnic:*` input
- Inline validation rejects empty input
- Merge response shows merge-specific toast

**`PicnicImportPage.test.tsx` (extend):**
- Line item with matching synth-tracked rule shows enrichment button
- Line item with matching real-tracked rule does NOT show enrichment button
- Line item without matching rule shows nothing special

**`TrackedProductsPage.test.tsx` (extend):**
- Synth row shows "Picnic-only" chip and "Barcode scannen" button
- Real row does not

### Not Tested (Deliberate)

- Visual regression of store result cards
- Debounce timing on search input (rely on library)
- Picnic API rate limits (outside our control)
- Scanner hardware integration (input is just a text field)

## Open Questions

None — all decisions locked in during brainstorming:

- ✅ No schema change (synthetic barcode convention instead)
- ✅ Server generates synth format (client sends `barcode: null`)
- ✅ Promote endpoint on `tracked_products` router (not inventory)
- ✅ Merge on PK collision: "promoted synth wins"
- ✅ Enrichment UI on both PicnicImportPage and TrackedProductsPage
- ✅ No OpenFoodFacts reverse lookup (too risky)
- ✅ No schema change for non-Picnic tracked products (status quo from auto-restock: real barcode rows stay as-is)

## Known Trade-offs

1. **Dormant rules never enrich** — If a user subscribes a product and never orders it via Picnic and never scans a physical package, the rule stays synth forever and never fires. Mitigation: the Nachbestellungen enrichment button lets the user fix this out of band. Acceptable: the rule is still harmless dormant.

2. **Merge loses the existing real row's min/target values** — Intentional; documented above. If a user wants to preserve the old values, they can edit the promoted row after the fact.

3. **Synth PK format is a string convention** — Not enforced at the DB level. A bug that writes `picnic:` without a suffix, or `PICNIC:s100`, would break lookup. Mitigated by the `make_synthetic_barcode` helper being the only writer and `is_synthetic_barcode` being the only reader.

4. **No backfill for existing users** — Users who already have tracked_products rows keep them untouched. The synth mechanism is purely additive.
