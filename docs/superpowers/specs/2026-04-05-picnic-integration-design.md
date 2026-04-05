# Picnic Integration — Design

**Date:** 2026-04-05 (revised after empirical API probe)
**Status:** Draft — v2
**Scope:** Addon backend (FastAPI) + React frontend

## Goal

Integrate the Picnic grocery delivery service (DE) into the Recipe Assistant addon to support two user flows:

1. **Re-order (cart-sync):** user builds an in-app shopping list from inventory and pushes it into the real Picnic cart with one button press. User still finalizes the order in the Picnic app (delivery slot, payment).
2. **Auto-import from deliveries:** on demand (manual button), fetch recently delivered Picnic orders and walk through a review flow that assigns each line item to an existing inventory entry or creates a new one, with storage location, expiration date, and optional barcode scan.

## Key Finding: EAN → Picnic lookup is deterministic (v2 update)

Initial design assumed Picnic exposed no EAN data and the integration would need a gradually-built fuzzy-match bridge table. An empirical probe against this user's 173-item inventory revealed:

- **Forward lookup works.** `PicnicAPI.get_article_by_gtin(ean)` returns `{name, picnic_id}` directly. Against the real inventory, **73.4% (127/173)** of EANs resolved to a Picnic product on the first try, with 100% correctness (verified by manual name-overlap check). The 46 misses are legitimately unavailable at Picnic (house brands from dm/Rossmann, niche items) — fuzzy matching could not recover them because no Picnic equivalent exists.
- **Reverse lookup does not work.** Delivery line items from `get_delivery()` contain `picnic_id`, `name`, `unit_quantity`, `image_ids`, `decorators[].quantity` — but **no `gtin` or `ean` field**. `get_article(picnic_id)` also returns only `{name, id}`. There is no API path from a Picnic ID to its EAN.
- **2FA is required** for this account (Picnic DE). Library supports the flow via `generate_2fa_code` / `verify_2fa_code`; auth token must be persisted across addon restarts in `/data/picnic_token.json`.

**Consequence for the design:** the "bridge table built from fuzzy matches + user confirmations" is no longer the main mechanism. For Use-Case A (cart sync), we hit `get_article_by_gtin` directly and cache the result. For Use-Case C (import), we still need fallback fuzzy matching because deliveries lack GTINs, but the cache built up by cart-sync provides a primary fast path (reverse lookup from cached `picnic_id → ean` pairs). The `EanPicnicMap` bridge table collapses into a nullable `ean` column on `picnic_products`.

## Non-Goals

- Placing actual orders via the API. The final step (slot + payment) stays in the Picnic app.
- Background polling. All Picnic operations are triggered explicitly by the user, because every import requires storage-location decisions anyway.
- Supporting multiple grocery services. The design is Picnic-only. If more services are added later, the schema can migrate to a `Product` entity with N identifiers, but that is out of scope here.
- Price tracking / budget features. The catalog cache stores a `last_price_cents` for display, not history.
- Fully-automatic shopping list generation based on inventory thresholds. User curates the list manually.

## Use Cases

### UC1: Re-order via shopping list
1. User opens the Inventory page and taps a "+ add to shopping list" icon on an item that is running low.
2. Item appears on the new Shopping List page. Backend resolves Picnic availability on page load: cache hit in `picnic_products` first; if miss, live `get_article_by_gtin(ean)` call; cache the result.
3. Item is shown as either **green (mapped)** with the matched Picnic product name, or **red (unavailable)** meaning Picnic doesn't sell this EAN. Red items stay on the list but are excluded from cart sync. A small optional "manuell suchen" link opens a free-text Picnic search dialog as a last-resort fallback (rarely needed — misses are usually products Picnic doesn't stock at all).
4. When the list is ready, user clicks "Push to Picnic cart". The backend iterates mapped items and calls Picnic's cart API per item (no batch endpoint); returns an aggregated per-item success/failure response.
5. User opens Picnic app, picks a delivery slot, completes order outside of this addon.

### UC2: Import delivered Picnic order
1. Picnic order arrives; user opens the addon, taps "Import Picnic delivery".
2. Backend fetches `delivered` orders not yet recorded in `picnic_delivery_imports`, matches each line item against existing inventory using fuzzy name matching + unit-quantity comparison, and returns a list of review candidates.
3. User walks through the review list:
   - High-confidence matches (score ≥ 92) are pre-selected. User confirms with Enter.
   - Uncertain matches expand to show top-5 candidates.
   - User can alternatively scan the physical barcode on the package to short-circuit matching with 100% confidence (source="scan").
   - Items with no match or user's choice create new inventory entries; user picks storage location inline.
4. Commit button writes everything in one transaction: inventory quantities, new items, mappings, delivery marker.

## Architecture

### Backend module layout

```
backend/app/
├── services/
│   ├── barcode.py              (unchanged)
│   └── picnic/
│       ├── __init__.py
│       ├── client.py           # thin wrapper around python-picnic-api2
│       ├── catalog.py          # picnic_products cache: upsert, get, search
│       ├── matching.py         # fuzzy matcher: picnic line item ↔ inventory
│       ├── import_flow.py      # orchestration: fetch → diff → review → commit
│       └── cart.py             # re-order: push shopping list into Picnic cart (per-item)
├── models/
│   └── picnic.py               # PicnicProduct (with embedded ean),
│                               # PicnicDeliveryImport, ShoppingListItem
├── routers/
│   └── picnic.py               # /api/picnic/*
└── schemas/
    └── picnic.py               # Pydantic request/response models
```

Picnic is isolated as a sub-package because it will grow to 5+ files. `barcode.py` stays untouched — Picnic is not a barcode provider (it has no EANs), so it does not belong in the lookup chain.

### Frontend layout

```
frontend/src/
├── pages/
│   ├── PicnicImportPage.tsx
│   └── ShoppingListPage.tsx
├── components/
│   └── picnic/
│       ├── ReviewCard.tsx
│       ├── MatchCandidateList.tsx
│       └── CartSyncButton.tsx
└── hooks/
    └── usePicnic.ts
```

### Configuration

Config flows through Home Assistant addon `config.json` → environment variables:

- `PICNIC_MAIL` (required to enable Picnic features; the Settings class also accepts `PICNIC_EMAIL` as an alias)
- `PICNIC_PASSWORD`
- `PICNIC_COUNTRY_CODE` (default: `DE`)

**Authentication state** is persisted at `/data/picnic_token.json`, which stores the `x-picnic-auth` bearer token returned by Picnic after a successful login. On addon startup the client reads the cached token and reuses it, avoiding repeated logins. On a 401 response the client re-attempts login once with the stored credentials.

**2FA bootstrap:** The Picnic DE account tested requires SMS-based 2FA on new logins. Because HA addons run headless, the initial 2FA flow cannot be done through the normal HTTP API path — it needs an out-of-band trigger. The addon ships a small CLI helper (`python -m app.services.picnic.setup`) that the user runs once (inside the addon container or locally pointing at `/data/picnic_token.json`): it prompts for an OTP channel, sends the SMS, polls `/data/picnic_otp.txt` for the user-supplied code, verifies, and writes the resulting token to `/data/picnic_token.json`. After that, normal operation uses the cached token without ever touching the login endpoint. If the stored token expires and re-login demands 2FA again, `/api/picnic/status` returns HTTP 503 with `{"error": "picnic_reauth_required"}`, and the frontend shows a banner instructing the user to rerun the setup CLI.

Feature is considered "enabled" iff `PICNIC_MAIL` (or `PICNIC_EMAIL`) and `PICNIC_PASSWORD` are both present *and* a valid auth token is available in `/data/picnic_token.json`. Otherwise `/api/picnic/status` reports disabled and the frontend hides Picnic UI elements.

### Dependencies

- Backend new: `python-picnic-api2`, `rapidfuzz`
- Frontend new: none

## Data Model (v2 — simplified)

All new tables live in a single Alembic migration (`add_picnic_tables`). No existing tables are modified. The v1 `EanPicnicMap` bridge table is gone; its role is absorbed into a nullable `ean` column on `picnic_products`.

```python
class PicnicProduct(Base):
    """Cache of Picnic catalog entries + learned EAN pairing.

    - picnic_id is the primary key (stable Picnic SKU identifier).
    - ean is nullable, indexed. Populated whenever we successfully resolve a
      Picnic product via get_article_by_gtin(ean), or whenever a user manually
      links a delivery line item to an EAN via scan or confirmation during
      import review.
    - A single EAN may map to multiple Picnic SKUs (different pack sizes) -
      ean is NOT unique. When resolving EAN -> picnic_id for cart sync, pick
      the most recently seen match (ORDER BY last_seen DESC).
    """
    __tablename__ = "picnic_products"

    picnic_id: Mapped[str] = mapped_column(String, primary_key=True)
    ean: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit_quantity: Mapped[str | None] = mapped_column(String, nullable=True)
    image_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PicnicDeliveryImport(Base):
    """Dedup record: which Picnic deliveries have already been imported."""
    __tablename__ = "picnic_delivery_imports"

    delivery_id: Mapped[str] = mapped_column(String, primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ShoppingListItem(Base):
    """In-app shopping list, flushed to Picnic cart on demand."""
    __tablename__ = "shopping_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inventory_barcode: Mapped[str | None] = mapped_column(String, nullable=True)
    picnic_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

The v1 `brand` column is dropped — `get_article_by_gtin` returns the brand embedded in the product name (e.g. `"Bamboo Garden Kokosmilch"`); splitting it would require parsing heuristics we don't need.

### Handling Picnic-only items (no real EAN)

Fresh produce, bakery items, or items where the user skips the barcode scan during import have no real EAN. They are stored in `InventoryItem` with a **synthetic barcode** of the form `picnic:s1234567`. The existing unique constraint on `InventoryItem.barcode` remains valid because `picnic:<id>` is unique by construction.

Promotion from synthetic to real EAN happens in exactly one place: during the **import review flow**, when the user scans a barcode on a card whose current match target is a synthetic-barcode inventory item. The scan handler:

1. Looks up the scanned EAN in inventory.
2. If found → flags the synthetic inventory row for deletion at commit time and redirects the decision to `match_existing` with `target_barcode = scanned_ean`. Quantities will be merged in the commit transaction.
3. If not found → queues a promotion UPDATE (`InventoryItem.barcode = scanned_ean`) for commit, plus an update to `picnic_products.ean` for the corresponding Picnic ID so future lookups are cached.

There is no separate "promote this synthetic barcode" endpoint. Promotion only happens as a side effect of scanning during import review. Synthetic-barcode items behave like regular inventory items in all other views (shown on the Inventory page, editable, deletable), and the UI displays them with a small "Picnic" badge so the user knows they lack a real EAN.

## Backend API

All endpoints live under `/api/picnic/*`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/picnic/status` | Returns `{enabled: bool, account: {...} \| null}`. |
| `POST` | `/api/picnic/import/fetch` | Returns delivery candidates with match suggestions (see Matching section). |
| `POST` | `/api/picnic/import/commit` | Commits user decisions transactionally. |
| `GET` | `/api/picnic/search?q=...` | Live Picnic catalog search; caches results in `picnic_products`. |
| `GET` | `/api/picnic/shopping-list` | Returns current shopping list with Picnic resolution status. |
| `POST` | `/api/picnic/shopping-list` | Add item. |
| `PATCH` | `/api/picnic/shopping-list/{id}` | Update quantity or mapping. |
| `DELETE` | `/api/picnic/shopping-list/{id}` | Remove item. |
| `POST` | `/api/picnic/shopping-list/sync` | Push mapped items into the real Picnic cart. Returns per-item status. |
| `GET` | `/api/picnic/cache` | List cached `picnic_products` rows (admin/debug: shows ean ↔ picnic_id pairings). |
| `DELETE` | `/api/picnic/cache/{picnic_id}` | Clear a cached entry (e.g. to force re-lookup). |

### Write-safety guarantee

The only endpoint that mutates state on the Picnic side is `/api/picnic/shopping-list/sync`. All other endpoints are read-only from Picnic's perspective. Import/review flows read deliveries but never modify them.

### Request/response schemas (key shapes)

```python
# POST /api/picnic/import/fetch response
class ImportDelivery(BaseModel):
    delivery_id: str
    delivered_at: datetime
    items: list[ImportCandidate]

class ImportCandidate(BaseModel):
    picnic_id: str
    picnic_name: str
    picnic_image_id: str | None
    picnic_unit_quantity: str | None
    ordered_quantity: int
    match_suggestions: list[MatchSuggestion]  # empty if no candidates
    best_confidence: float  # highest score in suggestions, or 0.0 (scale 0–100)

class MatchSuggestion(BaseModel):
    inventory_barcode: str
    inventory_name: str
    score: float  # scale 0–100, matches rapidfuzz output + unit bonus
    reason: str  # short human-readable: "name match + unit match"

# POST /api/picnic/import/commit request
class ImportDecision(BaseModel):
    picnic_id: str
    action: Literal["match_existing", "create_new", "skip"]
    target_barcode: str | None  # for match_existing
    scanned_ean: str | None  # if user scanned during review
    storage_location: str | None  # for create_new
    expiration_date: date | None  # for create_new

class ImportCommitRequest(BaseModel):
    delivery_id: str
    decisions: list[ImportDecision]

# POST /api/picnic/shopping-list/sync response
class CartSyncItemResult(BaseModel):
    shopping_list_id: int
    picnic_id: str | None
    status: Literal["added", "skipped_unmapped", "failed"]
    failure_reason: str | None  # e.g. "product_unavailable", "quantity_limit", "http_error"

class CartSyncResponse(BaseModel):
    results: list[CartSyncItemResult]
    added_count: int
    failed_count: int
    skipped_count: int
```

## Resolution Strategy (v2)

There are two distinct resolution directions, handled asymmetrically:

### Direction 1: inventory EAN → Picnic product (cart sync)

**Used for:** Use-Case A (shopping list → cart sync), inventory-page "find at Picnic" lookups.

**Deterministic path, in order:**
1. **Cache hit.** `SELECT * FROM picnic_products WHERE ean = ? ORDER BY last_seen DESC LIMIT 1`. If found, use the cached `picnic_id`. Done.
2. **API lookup.** Call `picnic_api.get_article_by_gtin(ean)`. Returns `{"name": "...", "id": "s..."}` on hit, or raises/returns empty on miss.
3. **Cache result.** On hit: upsert into `picnic_products` with `picnic_id`, `ean`, `name`. Subsequent lookups short-circuit at step 1.
4. **On miss:** mark the inventory item as "unavailable at Picnic" in the response. User can manually search via `/api/picnic/search?q=...` as an optional fallback (rare — our empirical data shows most misses are products Picnic genuinely doesn't sell, not near-matches).

Fuzzy matching is **not used** in this direction. Forward GTIN lookup is the source of truth.

**Measured performance:** on a 173-item real-world inventory, 73.4% of items resolve to a Picnic product via this path with 100% correctness. The remaining 26.6% are legitimately unavailable (dm/Rossmann house brands, niche items).

### Direction 2: Picnic delivery line item → existing inventory item (import)

**Used for:** Use-Case C (import from delivered Picnic orders).

Picnic deliveries expose `{picnic_id, name, unit_quantity, decorators[].quantity}` per line item — **no EAN**. So we cannot do a deterministic lookup in this direction. The algorithm is:

**Step 1 — Cache hit via picnic_products.ean.** `SELECT ean FROM picnic_products WHERE picnic_id = ? AND ean IS NOT NULL`. If the Picnic ID is in our cache with a known EAN (which happens whenever cart-sync or a prior scan populated it), look up the inventory item by that EAN. If found, return it as a single suggestion with confidence 100 and `reason="known mapping"`. Done.

**Step 2 — Fuzzy name match (fallback).** For every inventory item:
1. Normalize both names: lowercase; strip manufacturer/brand annotations in parentheses; strip unit strings (`500 g`, `1 l`, `6 x 200ml`); collapse whitespace; remove punctuation; transliterate umlauts.
2. Compute `rapidfuzz.fuzz.token_set_ratio(normalized_picnic, normalized_inv)` → 0–100.
3. Unit-quantity bonus: if both unit strings parse to a comparable quantity (gram, ml, count) and match within 10% tolerance, add +10 to the score (capped at 100).
4. Return the top 5 candidates with score ≥ 60.

**Step 3 — Confidence tiers:**

| Score range | Tier | UI behavior |
|-------------|------|-------------|
| = 100 (known mapping) | known | Pre-selected, shown with "gemappt" badge |
| ≥ 92 | confident | Pre-selected, one-tap confirm |
| 75–91 | uncertain | Expandable list, no pre-selection |
| 60–74 | weak | Shown but dimmed |
| < 60 | none | No suggestions; user picks manually, scans, or creates new |

**Step 4 — Learning.** When a user confirms a delivery line item → existing inventory item during import review, update the corresponding `picnic_products` row with the inventory item's EAN. Future imports of the same Picnic SKU become deterministic (step 1 catches them). Scanned EANs during review take precedence over any prior fuzzy-based pairing (simple overwrite of the `ean` column).

**N:M handling:** in practice, one EAN → many Picnic SKUs (different pack sizes of the same product) is the common case. We don't enforce uniqueness on `picnic_products.ean`; during cart-sync resolution we pick the most recently seen entry. One Picnic SKU → many EANs is extremely rare and treated as "last write wins".

## UI Flows

### Flow 1: Import Picnic delivery

1. On the Inventory page, a "Picnic-Bestellung importieren" button is visible iff the Picnic feature is enabled.
2. Click → `POST /api/picnic/import/fetch` → loading spinner.
3. Response renders as a list of delivery sections. Each section contains review cards, one per Picnic line item.
4. Each review card displays:
   - Product image (via `image_id` + Picnic CDN URL), name, unit_quantity, ordered quantity
   - Match suggestion area (pre-selected if confidence ≥ 92; expandable list otherwise)
   - Actions: **Confirm** · **Scan barcode** · **Create new** · **Skip**
   - "Create new" reveals inline fields: storage location dropdown, optional expiration date, optional scan-now button
5. A floating "Import all confirmed" button at the bottom submits `POST /api/picnic/import/commit`.
6. On success, a toast summarizes counts: "X imported, Y skipped, Z created".

### Flow 2: Shopping list → Picnic cart

1. New sidebar navigation entry "Einkaufsliste".
2. Shopping list page lists all `ShoppingListItem`s with their Picnic resolution status (determined by calling `get_article_by_gtin` or cache lookup on demand when the page loads, or lazily when the user toggles an item):
   - **Green** — Picnic product resolved (either from cache or a just-completed live GTIN lookup). Picnic name + unit quantity displayed under the row.
   - **Red "nicht bei Picnic verfügbar"** — forward lookup returned no hit. Item stays on the list but is excluded from cart sync. A small "manuell suchen" link opens the free-text search dialog as an optional fallback.
3. Inventory page items gain a quick-action "+ shopping list" icon.
4. Shopping list page also has an "Add item" button with two modes: "From inventory" (resolved via EAN → GTIN lookup) and "Search Picnic directly" (bypasses the inventory, picks a Picnic SKU directly).
5. "Push to Picnic cart" button syncs all green items. Response displays per-item success/failure inline.
6. Successfully-synced items are **not** automatically removed from the shopping list — user removes them manually after verifying in the Picnic app (safety against double-adds).

Compared to v1, this is a much simpler UX: ~73% of items are green on first sight, and the yellow "needs manual resolution" state is gone.

### Flow 3: Barcode scan during review

Reuses the existing scanner component from the Inventory page. On scan result:
- Known EAN (already in inventory) → auto-select as match target, show confidence 1.0 tag, queue an update to `picnic_products.ean` for commit (links the Picnic SKU in this card to the scanned EAN).
- Unknown EAN → trigger OpenFoodFacts lookup (existing `barcode.py` chain), pre-fill name/category for the "Create new" fields of this card. On commit, the new inventory item is created and the corresponding `picnic_products.ean` is updated.
- Scan fails / no barcode readable → overlay shows error, user can retry or close.

## Error Handling

- **Auth failure (401) on cached token:** Client clears `/data/picnic_token.json` and attempts one silent re-login with config credentials. If 2FA is triggered again (new device, expired session, etc.), `/api/picnic/*` returns HTTP 503 with `{"error": "picnic_reauth_required"}`. Frontend shows a persistent banner prompting the user to rerun the setup CLI. If the re-login succeeds without 2FA, the request is retried transparently.
- **Rate limit (429):** Exponential backoff (1s, 2s, 4s), max 3 retries per request, then give up with HTTP 503.
- **Timeout (> 10s):** Abort request, return HTTP 504. Import flow is idempotent via `picnic_delivery_imports` dedup; user can re-trigger safely.
- **Partial import:** The commit endpoint runs all writes (inventory, mappings, delivery marker) in a single database transaction. Either everything lands or nothing does.
- **Cart sync partial failure:** Per-item tracking; successful items remain in the Picnic cart, failed items are reported with a reason. No rollback of already-written cart entries.
- **Picnic product unavailable during sync:** Item is returned as `failed: product_unavailable`, stays in the shopping list, user can manually replace with a different Picnic product.
- **Feature disabled** (missing config): all `/api/picnic/*` endpoints except `/status` return HTTP 503 `{"error": "picnic_not_configured"}`. `/status` always succeeds and returns `{enabled: false, account: null}` so the frontend can detect the state and hide Picnic UI without catching exceptions.

## Logging

- All Picnic API calls logged to stdout: request path and response status only. Never log request/response bodies (contains account data).
- Match decisions (score, chosen candidate, source) logged to existing `InventoryLog` with `action="picnic_import"` and a details string.
- Cart sync operations logged to `InventoryLog` with `action="picnic_cart_sync"`.

## Testing Strategy

### Unit tests (`tests/services/picnic/`)

- **`test_matching.py`** — table-driven tests over the normalizer and scorer with realistic German product names. Covers: unit-string stripping, brand removal, token_set_ratio behavior, unit-quantity bonus, threshold classification. Fuzzy matching is fallback-only, so the bar for coverage here is "works on realistic examples" not "covers every edge case".
- **`test_catalog.py`** — upsert logic for `picnic_products` (with and without `ean`), last_seen updating, EAN-based lookup, picnic_id-based lookup.
- **`test_import_flow.py`** — dedup via `picnic_delivery_imports`, idempotent re-runs, cache-first then fuzzy-fallback resolution, partial-commit rollback on error, promotion of synthetic barcodes to real EANs.
- **`test_cart.py`** — cart sync with GTIN lookup hits and misses, handling of items with no resolvable Picnic product, per-item failure tracking.

### Integration tests (`tests/routers/test_picnic.py`)

- Fake Picnic client fixture (`FakePicnicClient`) loaded from saved JSON fixtures in `tests/fixtures/picnic/`.
- Full import flow: fetch → review → commit → verify DB state (inventory quantities, new items, mappings, delivery marker).
- Cart sync flow with mixed results.
- Auth error paths: 401 → re-login → success; 401 → re-login → fail.
- Feature-disabled path: missing config → all endpoints return 503.

### Test fixtures

- `tests/fixtures/picnic/deliveries.json` — sanitized Picnic delivery response.
- `tests/fixtures/picnic/search_*.json` — sample search responses for matching tests.
- `tests/fixtures/picnic/cart.json` — sample cart state.

### Out of scope for automated tests

No live Picnic API calls in CI (flaky, requires credentials). The spec includes a manual smoke-test checklist.

### Manual smoke-test checklist

1. Run the 2FA setup CLI once to obtain `/data/picnic_token.json`.
2. Configure addon with valid Picnic DE credentials.
3. Open `/api/picnic/status` → should report `enabled: true` with account info.
4. Add 5 inventory items to the shopping list. Expect ~70% to resolve green immediately via GTIN lookup, rest shown as "nicht bei Picnic verfügbar".
5. Push shopping list to Picnic cart → open Picnic app, verify items appear.
6. Trigger import fetch → should list any delivered-but-not-imported orders.
7. Walk through review flow: expect line items whose SKU was already in the cache (from step 4) to show confidence-100 "known mapping" instantly. New SKUs fall back to fuzzy matching.
8. Commit → verify inventory quantities updated.
9. Trigger a second import of the same delivery → should be a no-op (dedup check).

## Open Questions

None at design time. Any new questions discovered during implementation should be flagged in the implementation plan or raised with the user before resolution.

## Rollout Plan

Single PR, single merge. The feature is gated by presence of `PICNIC_MAIL` (or `PICNIC_EMAIL` alias) + `PICNIC_PASSWORD` + a valid cached token in `/data/picnic_token.json`, so users without Picnic see no behavioral change. Alembic migration is additive (new tables only) and safe to run on existing deployments.

The 2FA setup CLI is shipped as `python -m app.services.picnic.setup`, run once per installation by the user (interactively, inside the addon container or a local environment pointing at the same `/data` volume).
