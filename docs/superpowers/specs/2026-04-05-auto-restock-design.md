# Auto-Restock via Threshold — Design

**Date:** 2026-04-05
**Status:** Draft
**Scope:** Addon backend (FastAPI) + React frontend
**Depends on:** `2026-04-05-picnic-integration-design.md`

## Goal

Allow the user to define a per-product reorder rule ("minimum quantity" + "target quantity"). When consumption via scanner, web UI, or manual quantity edit drops an inventory item below its minimum, the product is automatically added to the in-app shopping list (sized to refill back to the target). The user still pushes the shopping list into the real Picnic cart manually, as in the existing integration.

This feature fills the gap called out as explicit non-goal in the Picnic integration design ("Fully-automatic shopping list generation based on inventory thresholds. User curates the list manually.") — the user curation model is retained, but the list is seeded automatically.

## Non-Goals

- **No auto-push into the real Picnic cart.** Writes to Picnic stay gated behind the existing `POST /api/picnic/shopping-list/sync` button. No background process writes to Picnic.
- **No background polling.** The threshold check is synchronous, inline in the write path of each decrement endpoint. This matches the existing Picnic integration's architectural rule.
- **No recipe-cooking integration.** When a future recipe-cooking flow decrements ingredients, it will need to call the same service function. That is out of scope here.
- **No auto-cleanup of the shopping list on scan-in.** When the user scans a restocked product back in, the shopping list is not auto-shrunk. The user removes items manually after verifying delivery.
- **No notification / toast / push when the trigger fires.** The scanner flow is headless; feedback is delivered by the next app open.
- **No handling of items not available at Picnic.** Thresholds can only be created for products that resolve to a Picnic SKU at setup time. Products Picnic does not sell cannot be tracked.
- **No bulk CRUD.** Single-item endpoints only.

## Use Cases

### UC1: Set up a reorder rule

1. User opens the "Nachbestellungen" sidebar page or taps the quick-action icon on an existing inventory row.
2. Form shows barcode input (with scan button), `min_quantity`, `target_quantity`.
3. On barcode input, frontend calls `POST /api/tracked-products/resolve-preview` (debounced). Backend does cache-first then live `get_article_by_gtin(ean)` lookup.
4. If Picnic resolves the product: form shows the Picnic name + image, Save button enabled. If not: form shows "nicht bei Picnic verfügbar", Save disabled.
5. User submits. Backend creates a `TrackedProduct` row and immediately runs the threshold check against the current inventory quantity. If already below threshold, the shopping list is seeded in the same response.

### UC2: Consumption triggers reorder

1. User scans out a tracked product via the physical scanner (`/api/inventory/scan-out`), or reduces quantity via the web UI (`/api/inventory/remove`), or manually edits the quantity field.
2. Backend decrements `InventoryItem.quantity` as usual. If a `TrackedProduct` exists for this barcode and the new quantity is below `min_quantity`, the service layer upserts a `ShoppingListItem` sized to `target_quantity - new_quantity`.
3. If a shopping list entry already exists for the barcode, the existing entry's `quantity` is raised to the new required value (never reduced — user-configured quantities are respected).
4. If the new quantity is zero and the product is tracked, the `InventoryItem` row stays (as a "zombie" row with `quantity=0`) instead of being deleted. The row remains editable and keeps its storage location and history.
5. The user eventually opens the Shopping-List page and pushes items into the real Picnic cart via the existing sync button.

### UC3: Review and edit tracked products

1. User opens the "Nachbestellungen" page.
2. Page lists all `TrackedProduct`s joined with current inventory quantity, sorted by `below_threshold` descending.
3. User edits `min_quantity` / `target_quantity` via inline modal, or deletes a rule.
4. Edits trigger a follow-up check: if the new `target_quantity` changes the needed amount for a currently-below-threshold product, the corresponding shopping list entry is resized accordingly.

## Architecture

### Backend module layout

```
backend/app/
├── services/
│   └── restock.py                  # new: check_and_enqueue()
├── models/
│   └── tracked_product.py          # new: TrackedProduct
├── routers/
│   ├── tracked_products.py         # new: /api/tracked-products/*
│   └── inventory.py                # modified: _apply_decrement helper
└── schemas/
    └── tracked_product.py          # new: Pydantic request/response
```

### Frontend layout

```
frontend/src/
├── pages/
│   └── TrackedProductsPage.tsx     # sidebar entry "Nachbestellungen"
├── components/
│   └── tracked/
│       ├── TrackedProductCard.tsx
│       ├── TrackedProductForm.tsx
│       └── InventoryRestockButton.tsx
└── hooks/
    └── useTrackedProducts.ts
```

### Feature gate

All `/api/tracked-products/*` endpoints require the Picnic feature to be enabled (same config check as `routers/picnic.py`). If Picnic is disabled, endpoints return HTTP 503 `{"error": "picnic_not_configured"}`. Rationale: the feature is inherently Picnic-bound — thresholds can only be created for Picnic-resolvable products.

Note: if Picnic is disabled after tracked products already exist, the `restock.check_and_enqueue` service keeps firing on decrements (it only reads local DB state and writes to `shopping_list`, which is not Picnic-gated). The tracked rules remain dormant until the user re-enables Picnic. Shopping list entries created during dormant periods remain valid — they get pushed the next time the Picnic feature is active and the sync button is pressed.

## Data Model

A single new table. One behavioral change to the existing inventory deletion rule. Additive Alembic migration.

### New table: `tracked_products`

```python
class TrackedProduct(Base):
    """Auto-reorder rule for a product, keyed by EAN/barcode.

    Exists independently from InventoryItem — the rule persists even
    when the product is currently out of stock (quantity=0) or has
    never been in inventory. At creation time, the product MUST
    resolve to a Picnic SKU via get_article_by_gtin; only resolvable
    products can be tracked.
    """
    __tablename__ = "tracked_products"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    picnic_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    target_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("min_quantity >= 0", name="ck_tracked_min_nonneg"),
        CheckConstraint("target_quantity > min_quantity", name="ck_tracked_target_gt_min"),
    )
```

- **`barcode` as primary key**: unique, matches `InventoryItem.barcode`, no need for a separate FK. No `ON DELETE CASCADE` — tracked products are deliberately independent of inventory lifetime.
- **`picnic_id` NOT NULL**: enforces "only Picnic-resolvable products can be tracked" at the DB level.
- **`name` as snapshot**: stored locally instead of joined from Picnic or Inventory, so the Nachbestellungen page can always render even when the inventory row is deleted or Picnic catalog shifts.
- **Check constraints**: `target > min` is enforced at both Pydantic (API layer) and DB level.

### Behavioral change: inventory deletion at `quantity=0`

Currently, `/api/inventory/scan-out` and `/api/inventory/remove` delete the `InventoryItem` row when the quantity reaches zero (`routers/inventory.py:242`, `:160-165`). New rule:

```
If an InventoryItem.barcode exists in tracked_products:
  → set quantity to 0, DO NOT delete the row.
Otherwise (unchanged):
  → delete the row.
```

Response shapes stay compatible: `deleted: true/false` simply reflects the new rule. Scanner clients reading `deleted` continue to work.

Rationale: tracked products need to keep their storage location, history, and UI presence as "out, reorder queued". Non-tracked products remain tidied up.

### No new column on `ShoppingListItem`

The existing `inventory_barcode` column is sufficient as the dedup key. Whether a shopping list entry originated from a manual add or an auto-trigger does not matter — the shopping list is an unordered set of "want to buy". The service layer uses `WHERE inventory_barcode = ?` to find and upsert.

**Known edge case:** if the user manually adds the same product via the existing "Picnic direkt durchsuchen" flow (which leaves `inventory_barcode=NULL`) AND an auto-trigger fires later, two entries will coexist — the service query matches only on `inventory_barcode`. This is accepted as a rare case, easy to resolve manually in the shopping list UI. Making the dedup smarter (matching by `picnic_id`) is a non-goal because one EAN maps to multiple Picnic SKUs (different pack sizes).

## Service Layer: `restock.check_and_enqueue`

New file `backend/app/services/restock.py` with a single public function.

```python
async def check_and_enqueue(
    db: AsyncSession,
    barcode: str,
    new_quantity: int,
) -> RestockResult | None:
    """Check if a decrement crossed the threshold and upsert shopping list.

    Called by the caller AFTER decrementing inventory, BEFORE db.commit().
    Runs in the caller's transaction — either both writes land or neither.

    Returns None if no tracked rule exists or if new_quantity >= min_quantity.
    Returns RestockResult(added_quantity, shopping_list_item_id) if the
    shopping list was upserted.
    """
```

### Algorithm

1. Load `TrackedProduct` by barcode. If not found → `return None`.
2. If `new_quantity >= tracked.min_quantity` → `return None`.
3. Compute `needed = tracked.target_quantity - new_quantity`.
4. Look up existing `ShoppingListItem` via `WHERE inventory_barcode = ? ORDER BY id DESC LIMIT 1`.
   - **Hit**: `existing.quantity = max(existing.quantity, needed)`. Never reduce — if the user manually increased the quantity, respect that.
   - **Miss**: insert new `ShoppingListItem` with `inventory_barcode=barcode`, `picnic_id=tracked.picnic_id`, `name=tracked.name`, `quantity=needed`.
5. Do NOT call `db.commit()`. The caller owns the transaction. A `db.flush()` makes the upsert visible within the session if later reads are needed.
6. Write an `InventoryLog` entry with `action="restock_auto"` and details `f"qty {old}→{new}, list qty={needed}"`.
7. Return `RestockResult(barcode, added_quantity=needed, shopping_list_item_id=...)`.

### Call sites

All three live in `routers/inventory.py`. They are refactored through a shared helper `_apply_decrement(db, item, new_qty)` that encapsulates both:
- The new "delete iff not tracked" rule from the data model section.
- The threshold check via `restock.check_and_enqueue`.

Call sites:
1. **`scan_out`** — after computing the new quantity.
2. **`remove`** (the existing `/api/inventory/remove` endpoint used by the web UI).
3. **Manual quantity edit** — whichever PATCH/PUT endpoint handles direct quantity editing from the web UI. If the new value is less than the old value, call the helper. Increases skip the helper.

### Add-only semantics

`check_and_enqueue` only **adds** or **raises** shopping list quantities. It never removes entries and never reduces them:

- If the user manually deleted a shopping list entry, the next decrement below threshold re-creates it.
- If a `PATCH` to a tracked rule moves a product from "below" to "above" threshold (e.g. user lowered `min_quantity`), the existing shopping list entry is NOT removed. The user keeps what was already queued.
- If `new_quantity >= min_quantity`, the function is a pure no-op regardless of shopping list state.

Rationale: automatic removal is dangerous (the user may have already depended on seeing the item in the list). The shopping list is the user's curation surface; the auto-restock feature only seeds it.

### Non-goals of this service function

- **No Picnic API call.** `tracked_products.picnic_id` was set at rule-creation time; the service only reads it. No network I/O in the scanner write path.
- **No re-resolution.** If the cached `picnic_id` no longer exists at Picnic, that is caught later by the existing cart-sync error path (`status="failed", failure_reason="product_unavailable"`).
- **No batching.** One call per product. Callers that decrement multiple items (future recipe-cooking flow) call the function in a loop.

## Backend API

New router `backend/app/routers/tracked_products.py`, mounted at `/api/tracked-products/*`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/tracked-products` | List all tracked products with current inventory quantity (joined by barcode). |
| `POST` | `/api/tracked-products` | Create a new rule. Resolves Picnic synchronously; fails if no match. |
| `PATCH` | `/api/tracked-products/{barcode}` | Update `min_quantity` / `target_quantity`. `picnic_id` is not editable — delete and recreate if needed. |
| `DELETE` | `/api/tracked-products/{barcode}` | Remove the rule. Zombie `InventoryItem` rows (quantity=0) are NOT cleaned up automatically — user removes them manually. |
| `POST` | `/api/tracked-products/resolve-preview` | Picnic lookup for a barcode without creating a rule. Used by the form UI for live feedback before save. |

### Schemas

```python
class TrackedProductCreate(BaseModel):
    barcode: str
    min_quantity: int = Field(ge=0)
    target_quantity: int = Field(gt=0)

    @model_validator(mode="after")
    def _target_gt_min(self):
        if self.target_quantity <= self.min_quantity:
            raise ValueError("target_quantity must be greater than min_quantity")
        return self

class TrackedProductUpdate(BaseModel):
    min_quantity: int | None = Field(default=None, ge=0)
    target_quantity: int | None = Field(default=None, gt=0)
    # target_gt_min is re-checked after merging with the existing row

class TrackedProductRead(BaseModel):
    barcode: str
    picnic_id: str
    picnic_name: str
    picnic_image_id: str | None
    picnic_unit_quantity: str | None
    min_quantity: int
    target_quantity: int
    current_quantity: int        # from InventoryItem, 0 if not present
    below_threshold: bool        # derived: current_quantity < min_quantity
    created_at: datetime
    updated_at: datetime

class ResolvePreviewRequest(BaseModel):
    barcode: str

class ResolvePreviewResponse(BaseModel):
    resolved: bool
    picnic_id: str | None
    picnic_name: str | None
    picnic_image_id: str | None
    picnic_unit_quantity: str | None
    reason: str | None           # "cache_hit", "live_lookup", "not_in_picnic_catalog"
```

### POST flow in detail

1. Validate request via Pydantic (`target > min`).
2. Picnic resolve: cache lookup in `picnic_products` by `ean=barcode`. On miss, live `get_article_by_gtin(barcode)` call. On hit, cache the result via the existing Picnic catalog service.
3. No Picnic match → HTTP 422 `{"error": "picnic_product_not_found", "barcode": ...}`.
4. Inventory name preference: if an `InventoryItem` with this barcode exists, use its name as `tracked_products.name`. Otherwise use the Picnic name. Preserves user-customized names where available.
5. Insert into `tracked_products`. Existing barcode → HTTP 409 Conflict (user should PATCH explicitly instead of overwriting).
6. Immediately run `restock.check_and_enqueue(barcode, current_inventory_qty_or_zero)`. If already below threshold, the shopping list is seeded in the same transaction.
7. Response: `TrackedProductRead` with accurate `below_threshold` and the shopping list visible to subsequent reads.

### PATCH flow

1. Load existing row; 404 if missing.
2. Merge update fields, re-validate `target > min`.
3. Persist.
4. Re-run `restock.check_and_enqueue` with the current inventory quantity. This handles the case where the user raised `target_quantity` or raised `min_quantity` and the existing shopping list entry needs to be raised to match. Per add-only semantics (see service layer), lowered thresholds never shrink or remove shopping list entries.

### Picnic feature gate

All endpoints under `/api/tracked-products/*` return HTTP 503 `{"error": "picnic_not_configured"}` when the Picnic feature is disabled (mirrors the check in `routers/picnic.py`). The `GET` endpoint returning 503 is how the frontend hides the sidebar entry.

### Write-safety

No endpoint in this feature writes to the Picnic API. `resolve-preview` and `POST` read via `get_article_by_gtin` and cache results, but do not modify the Picnic cart or anything user-visible in the Picnic account.

## Frontend

Two touchpoints: a dedicated "Nachbestellungen" page and a quick-action on the inventory row.

### Nachbestellungen page (`TrackedProductsPage.tsx`)

- New sidebar entry "Nachbestellungen", visible iff the Picnic feature is enabled.
- Lists all `TrackedProductRead`s, sorted by `below_threshold` descending (below-threshold items first, so action items are immediately visible).
- Each row displays:
  - Picnic image via `picnic_image_id`
  - Name + `unit_quantity`
  - Badge showing `current_quantity / min_quantity` — red if `below_threshold`, green otherwise
  - `target_quantity` as secondary text ("Auffüllen auf X")
  - Edit button → opens `TrackedProductForm` prefilled
  - Delete button → confirmation dialog
- "+ Neu" button → opens empty `TrackedProductForm` with scanner option.

### Form modal (`TrackedProductForm.tsx`)

Fields:
1. **Barcode input** with scan button (reuses the existing barcode scanner component, to be verified during implementation).
2. **Live Picnic preview**: debounced 500ms on barcode change, `POST /api/tracked-products/resolve-preview`. Shows:
   - Loading spinner during the call
   - Green: Picnic name + image, Save enabled
   - Red: "nicht bei Picnic verfügbar", Save disabled
3. **`min_quantity`** number input.
4. **`target_quantity`** number input. Client-side validation: must be `> min_quantity`, else Save disabled.
5. **Save** → `POST` (create) or `PATCH` (edit). Error 409 → inline "bereits vorhanden, bitte bearbeiten". Error 422 → inline validation message.

Edit mode: barcode and Picnic preview are read-only (picnic_id is not editable per the API design). Only `min_quantity` and `target_quantity` are editable.

### Inventory page integration (`InventoryRestockButton.tsx`)

The existing inventory list gets a small badge/icon per row:

- **No threshold set**: grey "+Nachbestellung" icon → click opens `TrackedProductForm` with prefilled barcode.
- **Threshold set, above threshold**: green "↻ N/M" badge → click opens edit form.
- **Threshold set, below threshold**: red "↻ N/M" badge, visually emphasized → click opens edit form.

The join between inventory rows and tracked product status happens **client-side**: the inventory page fetches the tracked-products list via `useTrackedProducts` in parallel and merges by barcode in a `useMemo` map. No new backend endpoint, no change to `GET /api/inventory`. Inventory size is ~200 items max, so client-side join is trivial.

### Zombie row display

`InventoryItem`s with `quantity=0` (only possible for tracked products under the new delete rule) are shown in the inventory list with a distinct "leer, nachbestellt" visual. The row is not hidden; it gets a different visual treatment so the user can see that the rule is active and the item is waiting for delivery.

### Feedback model

When a trigger fires and upserts a shopping list entry, the user does not see a toast or notification. Rationale: the scanner is a headless wall-mounted device; there is no user looking at the frontend to receive a toast. Feedback is delivered the next time the user opens the app and sees the populated shopping list. Scanner response shapes remain unchanged.

## Error Handling

### Service layer (`restock.check_and_enqueue`)
- DB error on shopping list upsert → exception propagates, caller rolls back entire transaction. Scan-out fails with HTTP 500; scanner client can retry. Consistent state preferred over partial success.
- No tracked product → silent `return None`. No log noise for the common case.
- Corrupted `tracked_products` row (e.g. `target <= min` via direct DB manipulation despite check constraint) → `ValueError` with barcode in message. Loud fail.

### API layer (`/api/tracked-products/*`)
- `POST` with barcode not found at Picnic → HTTP 422 `{"error": "picnic_product_not_found", "barcode": ...}`.
- `POST` with existing barcode → HTTP 409 Conflict.
- `POST` / `PATCH` with `target_quantity <= min_quantity` → HTTP 422 (Pydantic validator). Defense in depth alongside the DB check constraint.
- `PATCH` / `DELETE` on nonexistent barcode → HTTP 404.
- Picnic feature disabled → HTTP 503 `{"error": "picnic_not_configured"}`.
- Picnic auth error (401 / 2FA required) during `resolve-preview` or `POST` → HTTP 503 `{"error": "picnic_reauth_required"}`. Frontend shows the existing "setup CLI rerun" banner.

### Decrement paths
- The "do not delete when tracked" rule is additive. Response shapes stay compatible: `deleted: bool` simply reflects the new rule. No client-breaking changes.

### Frontend
- `resolve-preview` failure (network, 503) → form shows "Picnic nicht erreichbar", Save disabled, retry button.
- `POST` 422 `picnic_product_not_found` → inline message under barcode field.
- `POST` 409 Conflict → inline "already tracked, edit instead".
- `GET /api/tracked-products` returns 503 (Picnic disabled) → hide sidebar entry, consistent with the existing Picnic feature gate.

## Testing Strategy

### Unit tests: `tests/services/test_restock.py`
- `check_and_enqueue` with no tracked rule → returns None, no DB writes.
- `check_and_enqueue` with `new_qty >= min` → returns None, no DB writes.
- `check_and_enqueue` with `new_qty < min`, empty shopping list → new `ShoppingListItem` with `quantity = target - new_qty`, correct `picnic_id`, `InventoryLog` written.
- `check_and_enqueue` with existing shopping list item, smaller quantity → quantity raised.
- `check_and_enqueue` with existing shopping list item, larger quantity → unchanged (never reduce).
- `check_and_enqueue` with `new_qty == 0` → full target quantity added to list.
- Transaction rollback: DB error on shopping list upsert → exception, caller rollback verified.

### Integration tests: `tests/routers/test_inventory_restock.py`
- Scan-out of a tracked product from `qty=3` to `qty=1` (below `min=2`) → shopping list has new entry, inventory row persists with `quantity=1`.
- Scan-out of a tracked product to `qty=0` → inventory row remains (zombie), shopping list has entry.
- Scan-out of a non-tracked product to `qty=0` → inventory row deleted (old rule), no shopping list change.
- `/api/inventory/remove` and manual quantity PATCH: same scenarios, same expectations.
- Scan-in of a zombie (`qty=0` tracked) to `qty=1` → inventory row becomes live again, shopping list NOT automatically pruned.
- Repeated scan-out under threshold → shopping list quantity raised to the new required value, no duplicate entries.

### Integration tests: `tests/routers/test_tracked_products.py`
- `POST` with Picnic hit (via `FakePicnicClient` fixture) → 201, row created.
- `POST` with Picnic miss → 422 `picnic_product_not_found`.
- `POST` with `target <= min` → 422 Pydantic error.
- `POST` with existing barcode → 409.
- `POST` triggers the immediate check: product is already below threshold → response shows `below_threshold: true` and shopping list has a fresh entry.
- `PATCH` changes `target_quantity` from 10 to 6, current quantity=2 (below `min=3`) → shopping list entry quantity is raised if `needed` is larger than existing; never reduced.
- `PATCH` lowers `min_quantity` so the product is no longer below threshold → shopping list entry is NOT removed (add-only semantics).
- Manually deleted shopping list entry + subsequent decrement below threshold → entry re-created.
- `DELETE` removes the tracked rule; inventory zombie with `qty=0` persists (no auto-cleanup — deliberate non-goal).
- `resolve-preview` with Picnic hit → 200 with `resolved: true`.
- `resolve-preview` with Picnic miss → 200 with `resolved: false, reason: "not_in_picnic_catalog"`.
- All endpoints with Picnic disabled → 503.

### No live Picnic calls in CI
Reuses the existing `FakePicnicClient` fixture from the Picnic integration's test infrastructure.

### Manual smoke test

1. Create a tracked product for milk via the UI: `min=1`, `target=4`. Verify Picnic preview resolves, row appears in the Nachbestellungen page with a green badge.
2. Scan out milk once → shopping list contains milk with `quantity = 4 - (current-1)`. Verify in the shopping list page.
3. Scan out again → shopping list entry is raised to the new required value, no duplicate.
4. Scan out until `qty=0` → inventory row persists as a zombie with a "leer, nachbestellt" visual; shopping list has `quantity=4`.
5. Push the shopping list to the Picnic cart → milk appears in the real Picnic account.
6. Scan milk back in twice → inventory row comes back to life with `qty=2`. Shopping list unchanged (user removes manually after verifying).
7. Delete the tracked rule → row is removed, inventory item persists untouched.

## Rollout

Single PR. Alembic migration is additive (new table, no existing table changes). The feature is gated behind the existing Picnic config check, so users without Picnic see:
- No new sidebar entry
- No badge on inventory rows (the inventory page's `useTrackedProducts` query 503s and resolves to an empty map)
- No behavioral change to scan-out / remove / quantity edit (the helper checks `tracked_products` first and is a no-op when the table is empty)

The behavioral change to the "delete at quantity=0" rule is gated on the presence of a matching `tracked_products` row, so non-Picnic users see exactly the old behavior.

## Open Questions

None at design time. Questions discovered during implementation should be flagged in the implementation plan or raised before resolution.
