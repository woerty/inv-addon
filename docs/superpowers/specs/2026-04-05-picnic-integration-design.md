# Picnic Integration — Design

**Date:** 2026-04-05
**Status:** Draft
**Scope:** Addon backend (FastAPI) + React frontend

## Goal

Integrate the Picnic grocery delivery service (DE) into the Recipe Assistant addon to support two user flows:

1. **Re-order (cart-sync):** user builds an in-app shopping list from inventory and pushes it into the real Picnic cart with one button press. User still finalizes the order in the Picnic app (delivery slot, payment).
2. **Auto-import from deliveries:** on demand (manual button), fetch recently delivered Picnic orders and walk through a review flow that assigns each line item to an existing inventory entry or creates a new one, with storage location, expiration date, and optional barcode scan.

The hard problem is that **Picnic exposes no EANs/GTINs** in its API. Products are identified by proprietary IDs (e.g. `s1234567`). A bridge between EANs (our inventory world) and Picnic IDs must be built up gradually via user-confirmed matches and opportunistic barcode scans during the put-away workflow.

## Non-Goals

- Placing actual orders via the API. The final step (slot + payment) stays in the Picnic app.
- Background polling. All Picnic operations are triggered explicitly by the user, because every import requires storage-location decisions anyway.
- Supporting multiple grocery services. The design is Picnic-only. If more services are added later, the schema can migrate to a `Product` entity with N identifiers, but that is out of scope here.
- Price tracking / budget features. The catalog cache stores a `last_price_cents` for display, not history.
- Fully-automatic shopping list generation based on inventory thresholds. User curates the list manually.

## Use Cases

### UC1: Re-order via shopping list
1. User opens the Inventory page and taps a "+ add to shopping list" icon on an item that is running low.
2. Item appears on the new Shopping List page with its Picnic mapping status (green: mapped, yellow: needs resolution, red: no Picnic product).
3. For yellow items, user clicks "Search Picnic…" and picks a matching product; the choice is cached in `ean_picnic_map`.
4. When the list is ready, user clicks "Push to Picnic cart". The backend iterates mapped items and calls Picnic's cart API per item (the Picnic API has no batch endpoint); the backend endpoint returns a single aggregated response with per-item success/failure.
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
│   └── picnic.py               # PicnicProduct, EanPicnicMap,
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

- `PICNIC_EMAIL` (required to enable Picnic features)
- `PICNIC_PASSWORD`
- `PICNIC_COUNTRY_CODE` (default: `DE`)

The client authenticates lazily on first use, caches the resulting `x-picnic-auth` token in `/data/picnic_token.json`, and re-logins transparently on 401. Feature is considered "enabled" iff `PICNIC_EMAIL` and `PICNIC_PASSWORD` are both present; otherwise `/api/picnic/status` reports disabled and the frontend hides Picnic UI elements.

### Dependencies

- Backend new: `python-picnic-api2`, `rapidfuzz`
- Frontend new: none

## Data Model

All new tables live in a single Alembic migration (`add_picnic_tables`). No existing tables are modified.

```python
class PicnicProduct(Base):
    """Cache of Picnic catalog entries, refreshed opportunistically."""
    __tablename__ = "picnic_products"

    picnic_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_quantity: Mapped[str | None] = mapped_column(String, nullable=True)
    image_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class EanPicnicMap(Base):
    """Bridge between EANs (inventory) and Picnic product IDs.
    
    Built up gradually via scans and user confirmations.
    N:M relationship: one EAN may map to multiple Picnic SKUs (e.g. different pack
    sizes) and one Picnic SKU may map to multiple EANs. Uniqueness is on the pair.
    """
    __tablename__ = "ean_picnic_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ean: Mapped[str] = mapped_column(String, nullable=False, index=True)
    picnic_id: Mapped[str] = mapped_column(
        String, ForeignKey("picnic_products.picnic_id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)  # "scan" | "user_confirmed" | "auto"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("ean", "picnic_id", name="uq_ean_picnic"),)


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

### Handling Picnic-only items (no real EAN)

Fresh produce, bakery items, or items where the user skips the barcode scan during import have no real EAN. They are stored in `InventoryItem` with a **synthetic barcode** of the form `picnic:s1234567`. The existing unique constraint on `InventoryItem.barcode` remains valid because `picnic:<id>` is unique by construction.

Promotion from synthetic to real EAN happens in exactly one place: during the **import review flow**, when the user scans a barcode on a card whose current match target is a synthetic-barcode inventory item. The scan handler:

1. Looks up the scanned EAN in inventory.
2. If found → flags the synthetic inventory row for deletion at commit time and redirects the decision to `match_existing` with `target_barcode = scanned_ean`. Quantities will be merged in the commit transaction.
3. If not found → queues a promotion UPDATE (`InventoryItem.barcode = scanned_ean`) for commit, plus an `ean_picnic_map` row with `source="scan"`.

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
| `GET` | `/api/picnic/mappings` | List all EAN ↔ Picnic mappings (admin/debug). |
| `DELETE` | `/api/picnic/mappings/{id}` | Delete an incorrect mapping. |

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

## Matching Algorithm

Given a Picnic line item (picnic_id, name, unit_quantity), produce a ranked candidate list of existing `InventoryItem`s.

**Step 1 — Exact match via mapping table.**
```
SELECT ean FROM ean_picnic_map WHERE picnic_id = ?
```
If a row exists, return that single inventory item with confidence 1.0 and `reason="known mapping"`. Done.

**Step 2 — Fuzzy name match.** For every inventory item:

1. Normalize both names: lowercase; strip manufacturer/brand annotations in parentheses; strip unit strings (`500 g`, `1 l`, `6 x 200ml`); collapse whitespace; remove punctuation.
2. Compute `rapidfuzz.fuzz.token_set_ratio(normalized_picnic, normalized_inv)` → 0–100.
3. Unit-quantity bonus: if both unit strings parse to a comparable quantity (gram, ml, count) and match within 10% tolerance, add +10 to the score (capped at 100).
4. Return the top 5 candidates with score ≥ 60.

**Step 3 — Confidence tiers:**

| Score range | Tier | UI behavior |
|-------------|------|-------------|
| ≥ 92 | confident | Pre-selected, vor-gehakt, one-tap confirm |
| 75–91 | uncertain | Expandable list, no pre-selection |
| 60–74 | weak | Shown but dimmed |
| < 60 | none | No suggestions; user picks manually or creates new |

**Step 4 — Learning:**

Every user decision writes into `ean_picnic_map`:
- Confirmed match → `source="user_confirmed"`
- Scanned barcode during review → `source="scan"` (replaces any existing `user_confirmed` entry on conflict)
- Auto-accepted high-confidence match (≥ 92, not overridden by user) → `source="auto"`

`source` is a trust hint for future conflict resolution: `scan > user_confirmed > auto`.

**Step 5 — N:M relationships:**

A single EAN may have multiple Picnic SKUs (e.g. 500 g and 1 kg packs of the same product), and vice versa. The unique constraint is on the `(ean, picnic_id)` pair, not on either column individually. When resolving a shopping-list EAN to a Picnic ID for cart sync, prefer the most recent mapping (`ORDER BY created_at DESC`) and let the user override via a dropdown in the shopping list UI.

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
2. Shopping list page lists all `ShoppingListItem`s with their Picnic resolution status:
   - Green: `picnic_id` resolved (via mapping or manual pick)
   - Yellow: no mapping, "Picnic-Produkt suchen…" button opens a search dialog
   - Red: search returned nothing and user has not picked; cannot be synced
3. Inventory page items gain a quick-action "+ shopping list" icon.
4. Shopping list page also has an "Add item" button with two tabs: "From inventory" and "Search Picnic directly".
5. "Push to Picnic cart" button syncs all green items. Response displays per-item success/failure inline.
6. Successfully-synced items are **not** automatically removed from the shopping list — user removes them manually after verifying in the Picnic app (safety against double-adds).

### Flow 3: Barcode scan during review

Reuses the existing scanner component from the Inventory page. On scan result:
- Known EAN (already in inventory) → auto-select as match target, show confidence 1.0 tag, queue a `source="scan"` mapping write for commit.
- Unknown EAN → trigger OpenFoodFacts lookup (existing `barcode.py` chain), pre-fill name/category for the "Create new" fields of this card.
- Scan fails / no barcode readable → overlay shows error, user can retry or close.

## Error Handling

- **Auth failure (401):** Client attempts one silent re-login with config credentials. If that fails, `/api/picnic/*` returns HTTP 503 with `{"error": "picnic_auth_failed", "detail": ...}`. Frontend shows a persistent banner prompting to check addon config.
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

- **`test_matching.py`** — table-driven tests over the normalizer and scorer with realistic German product names. Covers: unit-string stripping, brand removal, token_set_ratio behavior, unit-quantity bonus, threshold classification, N:M resolution.
- **`test_catalog.py`** — upsert logic, last_seen updating, stale-entry queries.
- **`test_import_flow.py`** — dedup via `picnic_delivery_imports`, idempotent re-runs, partial-commit rollback on error, promotion of synthetic barcodes to real EANs.
- **`test_cart.py`** — batch cart sync with mixed success/failure responses, resolution of unmapped items.

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

1. Configure addon with valid Picnic DE credentials.
2. Open `/api/picnic/status` → should report `enabled: true` with account info.
3. Trigger import fetch → should list any delivered-but-not-imported orders.
4. Walk through review flow, confirm all, commit → verify inventory quantities in Inventory page.
5. Add 2–3 inventory items to shopping list; verify one resolves automatically (via just-created mapping) and one requires manual search.
6. Push shopping list to Picnic cart → open Picnic app, verify items appear.
7. Trigger a second import of the same delivery → should be a no-op (dedup check).

## Open Questions

None at design time. Any new questions discovered during implementation should be flagged in the implementation plan or raised with the user before resolution.

## Rollout Plan

Single PR, single merge. The feature is gated by presence of `PICNIC_EMAIL` in addon config, so users without Picnic see no behavioral change. Alembic migration is additive (new tables only) and safe to run on existing deployments.
