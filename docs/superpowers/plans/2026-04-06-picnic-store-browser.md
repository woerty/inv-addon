# Picnic Store Browser & Synthetic Barcode Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users browse the Picnic catalog, add items to the shopping list, and subscribe to auto-restock rules — even for products not yet in inventory — using synthetic barcodes that can later be promoted to real EANs.

**Architecture:** Backend gains a synthetic barcode convention (`picnic:<id>`), an updated `POST /tracked-products` that accepts barcode-less subscriptions, and a new `POST /tracked-products/{barcode}/promote-barcode` endpoint. Frontend adds a new Picnic Store page with search + result cards, a subscribe dialog, and a promote-barcode dialog wired into both the Nachbestellungen and PicnicImport pages.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async), Alembic, React 19, MUI 6, TypeScript 5.7, Vite 6

**Spec:** `docs/superpowers/specs/2026-04-06-picnic-store-browser-design.md`

---

## File Map

### Backend — New files
- `app/services/tracked_products.py` — synthetic barcode helpers (`is_synthetic_barcode`, `make_synthetic_barcode`, `SYNTHETIC_BARCODE_PREFIX`)
- `alembic/versions/005_add_picnic_id_index.py` — index on `tracked_products.picnic_id`
- `tests/test_promote_barcode.py` — tests for promote endpoint

### Backend — Modified files
- `app/schemas/tracked_product.py` — make `barcode` optional, add `picnic_id`/`name` fields, new `PromoteBarcodeRequest`/`PromoteBarcodeResponse` schemas
- `app/routers/tracked_products.py` — update `create_tracked` for synth path, add `promote_barcode` endpoint
- `tests/test_tracked_products_router.py` — add tests for synth-barcode creation

### Frontend — New files
- `src/pages/PicnicStorePage.tsx` — search + result grid + subscribe flow
- `src/components/picnic/SubscribeDialog.tsx` — min/target form for store-browser subscribe
- `src/components/picnic/StoreResultCard.tsx` — single search result card
- `src/components/picnic/PromoteBarcodeDialog.tsx` — barcode scanner input for promotion

### Frontend — Modified files
- `src/types/index.ts` — `TrackedProductCreate` gains optional fields, new `PromoteBarcodeResponse` type
- `src/api/client.ts` — new `promoteTrackedProductBarcode` function
- `src/hooks/useTrackedProducts.ts` — add `promote` method
- `src/components/Navbar.tsx` — add "Picnic Store" entry
- `src/App.tsx` — add `/picnic-store` route
- `src/pages/TrackedProductsPage.tsx` — synth chip + promote button
- `src/components/tracked/TrackedProductCard.tsx` — synth indicator + promote action
- `src/pages/PicnicImportPage.tsx` — per-line enrichment badge + button

---

## Task 1: Synthetic Barcode Helpers + Unit Tests

**Files:**
- Create: `recipe-assistant/backend/app/services/tracked_products.py`
- Create: `recipe-assistant/backend/tests/services/test_tracked_product_helpers.py`

- [ ] **Step 1: Write the failing tests**

Create `recipe-assistant/backend/tests/services/__init__.py` if it doesn't exist (empty file).

Create `recipe-assistant/backend/tests/services/test_tracked_product_helpers.py`:
```python
from app.services.tracked_products import (
    SYNTHETIC_BARCODE_PREFIX,
    is_synthetic_barcode,
    make_synthetic_barcode,
)


def test_make_synthetic_barcode():
    assert make_synthetic_barcode("s100") == "picnic:s100"


def test_is_synthetic_true():
    assert is_synthetic_barcode("picnic:s100") is True


def test_is_synthetic_false_real_ean():
    assert is_synthetic_barcode("4014400900057") is False


def test_is_synthetic_false_empty():
    assert is_synthetic_barcode("") is False


def test_prefix_constant():
    assert SYNTHETIC_BARCODE_PREFIX == "picnic:"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/test_tracked_product_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.tracked_products'`

- [ ] **Step 3: Write implementation**

Create `recipe-assistant/backend/app/services/tracked_products.py`:
```python
"""Synthetic barcode convention for Picnic-only tracked products.

Products subscribed from the Picnic Store Browser have no real EAN yet.
They use the format ``picnic:<picnic_id>`` as a placeholder primary key
until the user promotes them to a real barcode.
"""

from __future__ import annotations

SYNTHETIC_BARCODE_PREFIX = "picnic:"


def is_synthetic_barcode(barcode: str) -> bool:
    """Return True if *barcode* follows the synthetic ``picnic:<id>`` convention."""
    return barcode.startswith(SYNTHETIC_BARCODE_PREFIX)


def make_synthetic_barcode(picnic_id: str) -> str:
    """Build a synthetic barcode for a Picnic product ID."""
    return f"{SYNTHETIC_BARCODE_PREFIX}{picnic_id}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/test_tracked_product_helpers.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/tracked_products.py \
       recipe-assistant/backend/tests/services/__init__.py \
       recipe-assistant/backend/tests/services/test_tracked_product_helpers.py
git commit -m "feat(restock): add synthetic barcode helpers"
```

---

## Task 2: Alembic Migration — Index on `picnic_id`

**Files:**
- Create: `recipe-assistant/backend/alembic/versions/005_add_picnic_id_index.py`

- [ ] **Step 1: Write migration**

Create `recipe-assistant/backend/alembic/versions/005_add_picnic_id_index.py`:
```python
"""add index on tracked_products.picnic_id

Revision ID: 005
Revises: 004
Create Date: 2026-04-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_tracked_products_picnic_id", "tracked_products", ["picnic_id"])


def downgrade() -> None:
    op.drop_index("ix_tracked_products_picnic_id", table_name="tracked_products")
```

- [ ] **Step 2: Run existing tests to make sure nothing breaks**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_tracked_products_router.py -v`
Expected: All existing tests pass (tests use `create_all` from metadata, not Alembic, so the migration doesn't affect them, but confirms no import errors).

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/alembic/versions/005_add_picnic_id_index.py
git commit -m "feat(restock): add index on tracked_products.picnic_id"
```

---

## Task 3: Backend Schema + Router — Synth-Barcode Creation

**Files:**
- Modify: `recipe-assistant/backend/app/schemas/tracked_product.py`
- Modify: `recipe-assistant/backend/app/routers/tracked_products.py`
- Modify: `recipe-assistant/backend/tests/test_tracked_products_router.py`

This task modifies `POST /api/tracked-products` to accept `barcode: null` with `picnic_id` + `name` provided, generating a synthetic barcode server-side.

- [ ] **Step 1: Write the failing tests**

Add these tests to the end of `recipe-assistant/backend/tests/test_tracked_products_router.py`:

```python
@pytest.mark.asyncio
async def test_create_synth_barcode_from_picnic_id(client: AsyncClient):
    """Subscribe from store browser: no barcode, just picnic_id + name."""
    response = await client.post(
        "/api/tracked-products",
        json={
            "picnic_id": "s100",
            "name": "Ja! Vollmilch 1 L",
            "min_quantity": 1,
            "target_quantity": 4,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["barcode"] == "picnic:s100"
    assert data["picnic_id"] == "s100"
    assert data["name"] == "Ja! Vollmilch 1 L"
    assert data["min_quantity"] == 1
    assert data["target_quantity"] == 4


@pytest.mark.asyncio
async def test_create_synth_duplicate_returns_409(client: AsyncClient):
    payload = {
        "picnic_id": "s100",
        "name": "Ja! Vollmilch 1 L",
        "min_quantity": 1,
        "target_quantity": 4,
    }
    await client.post("/api/tracked-products", json=payload)
    response = await client.post("/api/tracked-products", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_synth_missing_picnic_id_returns_422(client: AsyncClient):
    """barcode=null without picnic_id should fail validation."""
    response = await client.post(
        "/api/tracked-products",
        json={"min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_with_real_barcode_still_works(client: AsyncClient):
    """Existing creation path (barcode + Picnic GTIN lookup) must remain unchanged."""
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["barcode"] == "4014400900057"
    assert data["picnic_id"] == "s100"
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_tracked_products_router.py::test_create_synth_barcode_from_picnic_id -v`
Expected: FAIL — 422 (barcode is currently required)

- [ ] **Step 3: Update the Pydantic schema**

Edit `recipe-assistant/backend/app/schemas/tracked_product.py`. Replace the `TrackedProductCreate` class:

```python
class TrackedProductCreate(BaseModel):
    barcode: str | None = Field(default=None, min_length=1)
    picnic_id: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    min_quantity: int = Field(ge=0)
    target_quantity: int = Field(gt=0)

    @model_validator(mode="after")
    def _target_gt_min(self) -> "TrackedProductCreate":
        if self.target_quantity <= self.min_quantity:
            raise ValueError("target_quantity must be greater than min_quantity")
        return self

    @model_validator(mode="after")
    def _barcode_or_picnic_id(self) -> "TrackedProductCreate":
        if not self.barcode and not self.picnic_id:
            raise ValueError("either barcode or picnic_id must be provided")
        return self
```

Also add new schemas to the bottom of the file:

```python
class PromoteBarcodeRequest(BaseModel):
    new_barcode: str = Field(min_length=1)


class PromoteBarcodeResponse(BaseModel):
    model_config = {"from_attributes": True}

    tracked: TrackedProductRead
    merged: bool
```

- [ ] **Step 4: Update the create_tracked router**

Edit `recipe-assistant/backend/app/routers/tracked_products.py`.

Add import at the top:
```python
from app.services.tracked_products import is_synthetic_barcode, make_synthetic_barcode
```

Replace the `create_tracked` function body with code that handles both paths:

```python
@router.post("", response_model=TrackedProductRead, status_code=201)
async def create_tracked(
    req: TrackedProductCreate,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()

    # Determine the effective barcode: real (user-supplied) or synthetic.
    if req.barcode is not None:
        effective_barcode = req.barcode
    else:
        # Store-browser path: barcode=null, picnic_id required (validated by schema).
        effective_barcode = make_synthetic_barcode(req.picnic_id)

    # Reject duplicate up front before hitting Picnic API.
    existing = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == effective_barcode)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "already_tracked", "barcode": effective_barcode},
        )

    if req.barcode is not None:
        # Classic path: resolve Picnic mapping from barcode via get_article_by_gtin.
        try:
            picnic_row, _reason = await _resolve_picnic(db, client, req.barcode)
        except PicnicNotConfigured:
            raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
        except PicnicReauthRequired:
            raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})

        if picnic_row is None:
            raise HTTPException(
                status_code=422,
                detail={"error": "picnic_product_not_found", "barcode": req.barcode},
            )

        # Prefer the inventory row's name (user-custom) over Picnic's, if present.
        inventory_row = (
            await db.execute(
                select(InventoryItem).where(InventoryItem.barcode == req.barcode)
            )
        ).scalar_one_or_none()
        display_name = inventory_row.name if inventory_row is not None else picnic_row.name
        picnic_id = picnic_row.picnic_id
        current_qty = inventory_row.quantity if inventory_row is not None else 0
    else:
        # Synth path: picnic_id and name come directly from the request.
        # The PicnicProduct cache row should already exist from the search
        # endpoint, but we don't require it — the tracked_products row stores
        # the name directly.
        display_name = req.name or req.picnic_id
        picnic_id = req.picnic_id
        current_qty = 0  # No inventory item for synth-subscribed products.

    tp = TrackedProduct(
        barcode=effective_barcode,
        picnic_id=picnic_id,
        name=display_name,
        min_quantity=req.min_quantity,
        target_quantity=req.target_quantity,
    )
    db.add(tp)
    await db.flush()

    # Immediate check: if the inventory quantity is already below the new
    # threshold, seed the shopping list in the same transaction.
    await check_and_enqueue(db, barcode=effective_barcode, new_quantity=current_qty)

    result = await _build_read_model(db, tp, current_quantity=current_qty)
    await db.commit()
    return result
```

- [ ] **Step 5: Run all tracked-product tests**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_tracked_products_router.py -v`
Expected: All tests pass (both old and new)

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/app/schemas/tracked_product.py \
       recipe-assistant/backend/app/routers/tracked_products.py \
       recipe-assistant/backend/tests/test_tracked_products_router.py
git commit -m "feat(restock): accept barcode=null for store-browser subscribe"
```

---

## Task 4: Backend — Promote Barcode Endpoint

**Files:**
- Modify: `recipe-assistant/backend/app/routers/tracked_products.py`
- Create: `recipe-assistant/backend/tests/test_promote_barcode.py`

- [ ] **Step 1: Write the failing tests**

Create `recipe-assistant/backend/tests/test_promote_barcode.py`:

```python
"""Tests for POST /api/tracked-products/{barcode}/promote-barcode."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.tracked_product import TrackedProduct
from app.services.picnic.client import get_picnic_client
from tests.conftest import TestingSessionLocal
from tests.fixtures.picnic.fake_client import FakePicnicClient


@pytest.fixture(autouse=True)
def override_picnic_client(monkeypatch):
    fake = FakePicnicClient()
    app.dependency_overrides[get_picnic_client] = lambda: fake
    monkeypatch.setenv("PICNIC_MAIL", "test@example.com")
    monkeypatch.setenv("PICNIC_PASSWORD", "secret")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_picnic_client, None)
        get_settings.cache_clear()


async def _create_synth(client: AsyncClient, picnic_id: str = "s100") -> dict:
    """Helper: create a synth-barcode tracked product."""
    resp = await client.post(
        "/api/tracked-products",
        json={
            "picnic_id": picnic_id,
            "name": "Test Product",
            "min_quantity": 1,
            "target_quantity": 4,
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_real(client: AsyncClient, barcode: str = "4014400900057") -> dict:
    """Helper: create a real-barcode tracked product via classic path."""
    resp = await client.post(
        "/api/tracked-products",
        json={"barcode": barcode, "min_quantity": 2, "target_quantity": 5},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_promote_happy_path(client: AsyncClient):
    await _create_synth(client)
    response = await client.post(
        "/api/tracked-products/picnic%3As100/promote-barcode",
        json={"new_barcode": "4014400900057"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tracked"]["barcode"] == "4014400900057"
    assert data["tracked"]["picnic_id"] == "s100"
    assert data["tracked"]["min_quantity"] == 1
    assert data["tracked"]["target_quantity"] == 4
    assert data["merged"] is False

    # Old synth PK should be gone.
    async with TestingSessionLocal() as session:
        old = (
            await session.execute(
                select(TrackedProduct).where(TrackedProduct.barcode == "picnic:s100")
            )
        ).scalar_one_or_none()
        assert old is None
        new = (
            await session.execute(
                select(TrackedProduct).where(TrackedProduct.barcode == "4014400900057")
            )
        ).scalar_one_or_none()
        assert new is not None
        assert new.picnic_id == "s100"


@pytest.mark.asyncio
async def test_promote_merge_collision(client: AsyncClient):
    """When the target EAN already has a tracked rule, merge: synth wins."""
    await _create_real(client)  # barcode=4014400900057, min=2, target=5
    await _create_synth(client)  # barcode=picnic:s100, min=1, target=4

    response = await client.post(
        "/api/tracked-products/picnic%3As100/promote-barcode",
        json={"new_barcode": "4014400900057"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tracked"]["barcode"] == "4014400900057"
    assert data["merged"] is True
    # Synth row's values win:
    assert data["tracked"]["min_quantity"] == 1
    assert data["tracked"]["target_quantity"] == 4

    # Only one row should remain.
    async with TestingSessionLocal() as session:
        rows = (await session.execute(select(TrackedProduct))).scalars().all()
        assert len(rows) == 1
        assert rows[0].barcode == "4014400900057"


@pytest.mark.asyncio
async def test_promote_not_found_404(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products/picnic%3Anonexistent/promote-barcode",
        json={"new_barcode": "4014400900057"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_promote_already_real_400(client: AsyncClient):
    """Cannot promote a row that already has a real barcode."""
    await _create_real(client)
    response = await client.post(
        "/api/tracked-products/4014400900057/promote-barcode",
        json={"new_barcode": "9999999999999"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "already_real_barcode"


@pytest.mark.asyncio
async def test_promote_synth_new_barcode_400(client: AsyncClient):
    """new_barcode must be a real EAN, not another synth."""
    await _create_synth(client)
    response = await client.post(
        "/api/tracked-products/picnic%3As100/promote-barcode",
        json={"new_barcode": "picnic:s200"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_new_barcode"


@pytest.mark.asyncio
async def test_promote_empty_new_barcode_422(client: AsyncClient):
    """Empty new_barcode should fail Pydantic validation."""
    await _create_synth(client)
    response = await client.post(
        "/api/tracked-products/picnic%3As100/promote-barcode",
        json={"new_barcode": ""},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_promote_barcode.py::test_promote_happy_path -v`
Expected: FAIL — 404/405 (endpoint doesn't exist yet)

- [ ] **Step 3: Implement the promote endpoint**

Edit `recipe-assistant/backend/app/routers/tracked_products.py`.

Add imports at the top (merge with existing):
```python
from app.schemas.tracked_product import (
    PromoteBarcodeRequest,
    PromoteBarcodeResponse,
    ResolvePreviewRequest,
    ResolvePreviewResponse,
    TrackedProductCreate,
    TrackedProductRead,
    TrackedProductUpdate,
)
```

Add imports for catalog service (merge with existing):
```python
from app.services.picnic.catalog import (
    PicnicProductData,
    get_product,
    get_product_by_ean,
    upsert_product,
)
```

Add the endpoint at the bottom of the file, before nothing (it's the last endpoint):

```python
@router.post(
    "/{barcode}/promote-barcode",
    response_model=PromoteBarcodeResponse,
)
async def promote_barcode(
    barcode: str,
    req: PromoteBarcodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Promote a synthetic barcode to a real EAN.

    If ``new_barcode`` already exists as a tracked-product PK, the existing
    real row is deleted and the synth row absorbs its position ("promoted
    synth wins" merge semantics).
    """
    _require_enabled()

    synth_row = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()
    if synth_row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})

    if not is_synthetic_barcode(synth_row.barcode):
        raise HTTPException(
            status_code=400,
            detail={"error": "already_real_barcode"},
        )

    new_barcode = req.new_barcode.strip()
    if is_synthetic_barcode(new_barcode):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_new_barcode"},
        )

    # Check for PK collision with an existing real-barcode row.
    existing_real = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == new_barcode)
        )
    ).scalar_one_or_none()
    merged = existing_real is not None
    if merged:
        await db.delete(existing_real)
        await db.flush()

    # PK change via delete + insert (SQLAlchemy PK mutations are fragile).
    preserved = {
        "picnic_id": synth_row.picnic_id,
        "name": synth_row.name,
        "min_quantity": synth_row.min_quantity,
        "target_quantity": synth_row.target_quantity,
        "created_at": synth_row.created_at,
    }
    await db.delete(synth_row)
    await db.flush()

    promoted = TrackedProduct(barcode=new_barcode, **preserved)
    db.add(promoted)
    await db.flush()

    # Also update the PicnicProduct cache row with the newly-learned EAN.
    picnic_product = await get_product(db, preserved["picnic_id"])
    if picnic_product is not None and picnic_product.ean is None:
        picnic_product.ean = new_barcode

    read_model = await _build_read_model(db, promoted)
    await db.commit()
    return PromoteBarcodeResponse(tracked=read_model, merged=merged)
```

- [ ] **Step 4: Run all promote tests**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_promote_barcode.py -v`
Expected: All 6 tests pass

- [ ] **Step 5: Run full backend test suite**

Run: `cd recipe-assistant/backend && python -m pytest -v`
Expected: All tests pass (old + new)

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/app/routers/tracked_products.py \
       recipe-assistant/backend/app/schemas/tracked_product.py \
       recipe-assistant/backend/tests/test_promote_barcode.py
git commit -m "feat(restock): add POST promote-barcode endpoint with merge"
```

---

## Task 5: Frontend Types + API Client

**Files:**
- Modify: `recipe-assistant/frontend/src/types/index.ts`
- Modify: `recipe-assistant/frontend/src/api/client.ts`
- Modify: `recipe-assistant/frontend/src/hooks/useTrackedProducts.ts`

- [ ] **Step 1: Update TypeScript types**

Edit `recipe-assistant/frontend/src/types/index.ts`.

Replace `TrackedProductCreate`:
```typescript
export interface TrackedProductCreate {
  barcode?: string | null;
  picnic_id?: string;
  name?: string;
  min_quantity: number;
  target_quantity: number;
}
```

Add after `ResolvePreview`:
```typescript
export interface PromoteBarcodeResponse {
  tracked: TrackedProduct;
  merged: boolean;
}
```

- [ ] **Step 2: Add API client functions**

Edit `recipe-assistant/frontend/src/api/client.ts`.

Add to imports from `../types`:
```typescript
  PromoteBarcodeResponse,
```

Add at the bottom of the file:
```typescript
export const promoteTrackedProductBarcode = (
  synthBarcode: string,
  newBarcode: string
) =>
  request<PromoteBarcodeResponse>(
    `/tracked-products/${encodeURIComponent(synthBarcode)}/promote-barcode`,
    {
      method: "POST",
      body: JSON.stringify({ new_barcode: newBarcode }),
    }
  );
```

- [ ] **Step 3: Add promote to useTrackedProducts hook**

Edit `recipe-assistant/frontend/src/hooks/useTrackedProducts.ts`.

Add import:
```typescript
import {
  listTrackedProducts,
  createTrackedProduct,
  updateTrackedProduct,
  deleteTrackedProduct,
  resolveTrackedProductPreview,
  promoteTrackedProductBarcode,
} from "../api/client";
import type {
  TrackedProduct,
  TrackedProductCreate,
  TrackedProductUpdate,
  ResolvePreview,
  PromoteBarcodeResponse,
} from "../types";
```

Add `promote` method inside `useTrackedProducts()` (after `remove`):
```typescript
  const promote = async (synthBarcode: string, newBarcode: string): Promise<PromoteBarcodeResponse> => {
    const result = await promoteTrackedProductBarcode(synthBarcode, newBarcode);
    await refetch();
    return result;
  };
```

Update the return to include `promote`:
```typescript
  return { items, loading, error, refetch, create, update, remove, promote };
```

- [ ] **Step 4: Verify frontend compiles**

Run: `cd recipe-assistant/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/types/index.ts \
       recipe-assistant/frontend/src/api/client.ts \
       recipe-assistant/frontend/src/hooks/useTrackedProducts.ts
git commit -m "feat(store): add promote-barcode types, API client, and hook"
```

---

## Task 6: SubscribeDialog + StoreResultCard Components

**Files:**
- Create: `recipe-assistant/frontend/src/components/picnic/SubscribeDialog.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/StoreResultCard.tsx`

- [ ] **Step 1: Create SubscribeDialog**

Create `recipe-assistant/frontend/src/components/picnic/SubscribeDialog.tsx`:
```tsx
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from "@mui/material";
import type { PicnicSearchResult, TrackedProductCreate } from "../../types";

type Props = {
  product: PicnicSearchResult | null;
  onClose: () => void;
  onSubmit: (data: TrackedProductCreate) => Promise<void>;
};

const SubscribeDialog = ({ product, onClose, onSubmit }: Props) => {
  const [minQty, setMinQty] = useState(1);
  const [targetQty, setTargetQty] = useState(4);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (product) {
      setMinQty(1);
      setTargetQty(4);
      setError(null);
    }
  }, [product]);

  const targetInvalid = targetQty <= minQty;
  const canSubmit = useMemo(
    () => !submitting && minQty >= 0 && targetQty > 0 && !targetInvalid,
    [submitting, minQty, targetQty, targetInvalid]
  );

  const handleSubmit = async () => {
    if (!product || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        picnic_id: product.picnic_id,
        name: product.name,
        min_quantity: minQty,
        target_quantity: targetQty,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={product !== null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Abonnieren: {product?.name}</DialogTitle>
      <DialogContent>
        <Box display="flex" flexDirection="column" gap={2} mt={1}>
          <TextField
            label="Mindestmenge"
            type="number"
            value={minQty}
            onChange={(e) => setMinQty(parseInt(e.target.value, 10) || 0)}
            inputProps={{ min: 0 }}
            fullWidth
          />
          <TextField
            label="Ziel-Menge"
            type="number"
            value={targetQty}
            onChange={(e) => setTargetQty(parseInt(e.target.value, 10) || 0)}
            inputProps={{ min: 1 }}
            helperText={
              targetInvalid
                ? "Ziel-Menge muss größer als die Mindestmenge sein"
                : "Auf diese Menge wird bei Unterschreitung aufgefüllt"
            }
            error={targetInvalid}
            fullWidth
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Abbrechen</Button>
        <Button variant="contained" disabled={!canSubmit} onClick={handleSubmit}>
          Abonnieren
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default SubscribeDialog;
```

- [ ] **Step 2: Create StoreResultCard**

Create `recipe-assistant/frontend/src/components/picnic/StoreResultCard.tsx`:
```tsx
import {
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Typography,
} from "@mui/material";
import type { PicnicSearchResult } from "../../types";

const PICNIC_IMAGE_BASE =
  "https://storefront-prod.de.picnicinternational.com/static/images";

type Props = {
  result: PicnicSearchResult;
  alreadySubscribed: boolean;
  onAddToList: (result: PicnicSearchResult) => void;
  onSubscribe: (result: PicnicSearchResult) => void;
};

const StoreResultCard = ({
  result,
  alreadySubscribed,
  onAddToList,
  onSubscribe,
}: Props) => {
  const priceFormatted =
    result.price_cents != null
      ? (result.price_cents / 100).toFixed(2).replace(".", ",") + " \u20ac"
      : null;

  return (
    <Card sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {result.image_id && (
        <Box
          component="img"
          src={`${PICNIC_IMAGE_BASE}/${result.image_id}/medium.png`}
          alt=""
          sx={{ width: "100%", height: 140, objectFit: "contain", mt: 1 }}
        />
      )}
      <CardContent sx={{ flex: 1 }}>
        <Typography variant="subtitle2" gutterBottom>
          {result.name}
        </Typography>
        {result.unit_quantity && (
          <Typography variant="body2" color="text.secondary">
            {result.unit_quantity}
          </Typography>
        )}
        {priceFormatted && (
          <Typography variant="body2" fontWeight="bold" sx={{ mt: 0.5 }}>
            {priceFormatted}
          </Typography>
        )}
      </CardContent>
      <CardActions sx={{ flexDirection: "column", alignItems: "stretch", gap: 0.5, p: 1 }}>
        <Button size="small" onClick={() => onAddToList(result)}>
          In Einkaufsliste
        </Button>
        {alreadySubscribed ? (
          <Chip label="Abonniert" size="small" color="success" />
        ) : (
          <Button size="small" variant="outlined" onClick={() => onSubscribe(result)}>
            Abonnieren
          </Button>
        )}
      </CardActions>
    </Card>
  );
};

export default StoreResultCard;
```

- [ ] **Step 3: Verify frontend compiles**

Run: `cd recipe-assistant/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/frontend/src/components/picnic/SubscribeDialog.tsx \
       recipe-assistant/frontend/src/components/picnic/StoreResultCard.tsx
git commit -m "feat(store): add SubscribeDialog and StoreResultCard components"
```

---

## Task 7: PicnicStorePage + Routing + Navbar

**Files:**
- Create: `recipe-assistant/frontend/src/pages/PicnicStorePage.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`
- Modify: `recipe-assistant/frontend/src/components/Navbar.tsx`

- [ ] **Step 1: Create PicnicStorePage**

Create `recipe-assistant/frontend/src/pages/PicnicStorePage.tsx`:
```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  CircularProgress,
  Container,
  Grid,
  TextField,
  Typography,
} from "@mui/material";
import { usePicnicSearch, usePicnicStatus } from "../hooks/usePicnic";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import { useNotification } from "../components/NotificationProvider";
import { addShoppingListItem } from "../api/client";
import StoreResultCard from "../components/picnic/StoreResultCard";
import SubscribeDialog from "../components/picnic/SubscribeDialog";
import type { PicnicSearchResult, TrackedProductCreate } from "../types";

const DEBOUNCE_MS = 400;

const PicnicStorePage = () => {
  const { status, loading: statusLoading } = usePicnicStatus();
  const { results, loading: searchLoading, search } = usePicnicSearch();
  const { items: tracked, create, refetch: refetchTracked } = useTrackedProducts();
  const { notify } = useNotification();

  const [query, setQuery] = useState("");
  const [subscribeTarget, setSubscribeTarget] = useState<PicnicSearchResult | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const subscribedPicnicIds = useMemo(
    () => new Set(tracked.map((t) => t.picnic_id)),
    [tracked]
  );

  const handleQueryChange = useCallback(
    (value: string) => {
      setQuery(value);
      clearTimeout(timerRef.current);
      if (value.trim().length < 2) return;
      timerRef.current = setTimeout(() => search(value.trim()), DEBOUNCE_MS);
    },
    [search]
  );

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const handleAddToList = async (r: PicnicSearchResult) => {
    try {
      await addShoppingListItem({
        picnic_id: r.picnic_id,
        name: r.name,
        quantity: 1,
      });
      notify("Zur Einkaufsliste hinzugefügt", "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  const handleSubscribe = async (data: TrackedProductCreate) => {
    await create(data);
    await refetchTracked();
    notify("Abonniert", "success");
  };

  if (statusLoading) return null;
  if (!status?.enabled) {
    return (
      <Container sx={{ mt: 4 }}>
        <Alert severity="info">
          Picnic Store benötigt die Picnic-Integration. Bitte zuerst Picnic
          einrichten.
        </Alert>
      </Container>
    );
  }

  return (
    <Container sx={{ mt: 4 }}>
      <Typography variant="h4" gutterBottom>
        Picnic Store
      </Typography>
      <TextField
        fullWidth
        placeholder="Picnic durchsuchen..."
        value={query}
        onChange={(e) => handleQueryChange(e.target.value)}
        sx={{ mb: 3 }}
      />

      {searchLoading && (
        <Box display="flex" justifyContent="center" my={4}>
          <CircularProgress />
        </Box>
      )}

      {!searchLoading && results.length === 0 && query.trim().length >= 2 && (
        <Typography color="text.secondary">Keine Ergebnisse.</Typography>
      )}

      <Grid container spacing={2}>
        {results.map((r) => (
          <Grid size={{ xs: 6, sm: 4, md: 3 }} key={r.picnic_id}>
            <StoreResultCard
              result={r}
              alreadySubscribed={subscribedPicnicIds.has(r.picnic_id)}
              onAddToList={handleAddToList}
              onSubscribe={setSubscribeTarget}
            />
          </Grid>
        ))}
      </Grid>

      <SubscribeDialog
        product={subscribeTarget}
        onClose={() => setSubscribeTarget(null)}
        onSubmit={handleSubscribe}
      />
    </Container>
  );
};

export default PicnicStorePage;
```

- [ ] **Step 2: Add route to App.tsx**

Edit `recipe-assistant/frontend/src/App.tsx`.

Add import:
```typescript
import PicnicStorePage from "./pages/PicnicStorePage";
```

Add route inside `<Routes>` (after `/tracked-products`):
```tsx
<Route path="/picnic-store" element={<PicnicStorePage />} />
```

- [ ] **Step 3: Add Navbar entry**

Edit `recipe-assistant/frontend/src/components/Navbar.tsx`.

Add import:
```typescript
import StorefrontIcon from "@mui/icons-material/Storefront";
```

In the `navItems` array, add the "Picnic Store" entry inside the `status?.enabled` conditional array, after the `tracked-products` entry:
```typescript
{ path: "/picnic-store", label: "Picnic Store", icon: <StorefrontIcon /> },
```

So the Picnic-enabled items become:
```typescript
...(status?.enabled
  ? [
      { path: "/picnic-import", label: "Picnic-Import", icon: <LocalGroceryStoreIcon /> },
      { path: "/shopping-list", label: "Einkaufsliste", icon: <ShoppingCartIcon /> },
      { path: "/tracked-products", label: "Nachbestellungen", icon: <AddAlertIcon /> },
      { path: "/picnic-store", label: "Picnic Store", icon: <StorefrontIcon /> },
    ]
```

- [ ] **Step 4: Verify frontend compiles**

Run: `cd recipe-assistant/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/pages/PicnicStorePage.tsx \
       recipe-assistant/frontend/src/App.tsx \
       recipe-assistant/frontend/src/components/Navbar.tsx
git commit -m "feat(store): add PicnicStorePage with search, cards, and subscribe"
```

---

## Task 8: PromoteBarcodeDialog Component

**Files:**
- Create: `recipe-assistant/frontend/src/components/picnic/PromoteBarcodeDialog.tsx`

- [ ] **Step 1: Create PromoteBarcodeDialog**

Create `recipe-assistant/frontend/src/components/picnic/PromoteBarcodeDialog.tsx`:
```tsx
import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from "@mui/material";
import type { TrackedProduct } from "../../types";

type Props = {
  tracked: TrackedProduct | null;
  onClose: () => void;
  onPromote: (synthBarcode: string, newBarcode: string) => Promise<{ merged: boolean }>;
};

const PromoteBarcodeDialog = ({ tracked, onClose, onPromote }: Props) => {
  const [barcode, setBarcode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSynth = barcode.startsWith("picnic:");
  const canSubmit = barcode.trim().length > 0 && !isSynth && !submitting;

  const handleSubmit = async () => {
    if (!tracked || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await onPromote(tracked.barcode, barcode.trim());
      onClose();
      setBarcode("");
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler");
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    setBarcode("");
    setError(null);
    onClose();
  };

  return (
    <Dialog open={tracked !== null} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Barcode nachpflegen: {tracked?.name}</DialogTitle>
      <DialogContent>
        <Box display="flex" flexDirection="column" gap={2} mt={1}>
          <TextField
            label="Barcode scannen oder eingeben"
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSubmit) handleSubmit();
            }}
            autoFocus
            fullWidth
            error={isSynth}
            helperText={isSynth ? "Bitte einen echten Barcode eingeben" : undefined}
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Abbrechen</Button>
        <Button variant="contained" disabled={!canSubmit} onClick={handleSubmit}>
          Barcode zuweisen
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default PromoteBarcodeDialog;
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd recipe-assistant/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/frontend/src/components/picnic/PromoteBarcodeDialog.tsx
git commit -m "feat(store): add PromoteBarcodeDialog component"
```

---

## Task 9: Wire Promote into TrackedProductsPage

**Files:**
- Modify: `recipe-assistant/frontend/src/pages/TrackedProductsPage.tsx`
- Modify: `recipe-assistant/frontend/src/components/tracked/TrackedProductCard.tsx`

- [ ] **Step 1: Add synth indicator + promote action to TrackedProductCard**

Edit `recipe-assistant/frontend/src/components/tracked/TrackedProductCard.tsx`.

Add imports:
```typescript
import QrCodeScannerIcon from "@mui/icons-material/QrCodeScanner";
import { Button } from "@mui/material";
```

Update Props type to include onPromote:
```typescript
type Props = {
  item: TrackedProduct;
  onEdit: (item: TrackedProduct) => void;
  onDelete: (item: TrackedProduct) => void;
  onPromote?: (item: TrackedProduct) => void;
};
```

Update function signature:
```typescript
const TrackedProductCard = ({ item, onEdit, onDelete, onPromote }: Props) => {
```

Add a helper inside the component:
```typescript
  const isSynthetic = item.barcode.startsWith("picnic:");
```

After the `Chip` component (the one showing `current_quantity / min_quantity`) and before the edit IconButton, add:
```tsx
        {isSynthetic && (
          <Chip label="Picnic-only" size="small" color="info" />
        )}
        {isSynthetic && onPromote && (
          <Button
            size="small"
            startIcon={<QrCodeScannerIcon />}
            onClick={() => onPromote(item)}
          >
            Barcode scannen
          </Button>
        )}
```

- [ ] **Step 2: Wire promote dialog into TrackedProductsPage**

Edit `recipe-assistant/frontend/src/pages/TrackedProductsPage.tsx`.

Add imports:
```typescript
import PromoteBarcodeDialog from "../components/picnic/PromoteBarcodeDialog";
```

Add state inside the component:
```typescript
  const [promoteTarget, setPromoteTarget] = useState<TrackedProduct | null>(null);
```

Destructure `promote` from the hook — change line:
```typescript
  const { items, loading, error, create, update, remove, promote } = useTrackedProducts();
```

Add promote handler:
```typescript
  const handlePromote = async (synthBarcode: string, newBarcode: string) => {
    const result = await promote(synthBarcode, newBarcode);
    notify(
      result.merged
        ? "Barcode übernommen (bestehende Regel ersetzt)"
        : "Barcode übernommen",
      "success"
    );
    return result;
  };
```

Add `onPromote` prop to TrackedProductCard in the render:
```tsx
        <TrackedProductCard
          key={item.barcode}
          item={item}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onPromote={setPromoteTarget}
        />
```

Add PromoteBarcodeDialog at the bottom (after TrackedProductForm, before the closing `</Container>`):
```tsx
      <PromoteBarcodeDialog
        tracked={promoteTarget}
        onClose={() => setPromoteTarget(null)}
        onPromote={handlePromote}
      />
```

- [ ] **Step 3: Verify frontend compiles**

Run: `cd recipe-assistant/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/frontend/src/pages/TrackedProductsPage.tsx \
       recipe-assistant/frontend/src/components/tracked/TrackedProductCard.tsx
git commit -m "feat(store): show synth indicator and promote button on Nachbestellungen"
```

---

## Task 10: Wire Promote into PicnicImportPage

**Files:**
- Modify: `recipe-assistant/frontend/src/pages/PicnicImportPage.tsx`
- Modify: `recipe-assistant/frontend/src/components/picnic/ReviewCard.tsx`

- [ ] **Step 1: Add enrichment button to ReviewCard**

Edit `recipe-assistant/frontend/src/components/picnic/ReviewCard.tsx`.

Add imports:
```typescript
import { Chip } from "@mui/material";
import QrCodeScannerIcon from "@mui/icons-material/QrCodeScanner";
import type { TrackedProduct } from "../../types";
```

Update Props:
```typescript
interface Props {
  candidate: ImportCandidate;
  storageLocations: string[];
  onChange: (decision: ImportDecision) => void;
  synthTracked?: TrackedProduct | null;
  onPromote?: (tracked: TrackedProduct) => void;
}
```

Update function signature:
```typescript
export function ReviewCard({ candidate, storageLocations, onChange, synthTracked, onPromote }: Props) {
```

Add enrichment badge right after the product info `<Box>` (after the closing `</Box>` of the product info row, before the action selector `<Box>`):
```tsx
        {synthTracked && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
            <Chip label="Abonniert · Barcode fehlt" size="small" color="warning" />
            {onPromote && (
              <Button
                size="small"
                startIcon={<QrCodeScannerIcon />}
                onClick={() => onPromote(synthTracked)}
              >
                Barcode nachpflegen
              </Button>
            )}
          </Box>
        )}
```

- [ ] **Step 2: Wire into PicnicImportPage**

Edit `recipe-assistant/frontend/src/pages/PicnicImportPage.tsx`.

Add imports:
```typescript
import { useMemo, useState } from "react";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import { useNotification } from "../components/NotificationProvider";
import PromoteBarcodeDialog from "../components/picnic/PromoteBarcodeDialog";
import type { TrackedProduct } from "../types";
```

(Replace the existing `import { useEffect, useState } from "react";` with the combined import.)

Inside the component, after the existing hooks, add:
```typescript
  const { items: tracked, promote, refetch: refetchTracked } = useTrackedProducts();
  const { notify } = useNotification();
  const [promoteTarget, setPromoteTarget] = useState<TrackedProduct | null>(null);

  const trackedByPicnicId = useMemo(
    () =>
      Object.fromEntries(
        tracked
          .filter((t) => t.barcode.startsWith("picnic:"))
          .map((t) => [t.picnic_id, t])
      ),
    [tracked]
  );

  const handlePromote = async (synthBarcode: string, newBarcode: string) => {
    const result = await promote(synthBarcode, newBarcode);
    notify(
      result.merged
        ? "Barcode übernommen (bestehende Regel ersetzt)"
        : "Barcode übernommen",
      "success"
    );
    return result;
  };
```

Update the ReviewCard render to pass synth-tracked info:
```tsx
            <ReviewCard
              key={item.picnic_id}
              candidate={item}
              storageLocations={storageLocations}
              onChange={handleDecision}
              synthTracked={trackedByPicnicId[item.picnic_id] ?? null}
              onPromote={setPromoteTarget}
            />
```

Add PromoteBarcodeDialog at the bottom (before the closing `</Paper>`):
```tsx
      <PromoteBarcodeDialog
        tracked={promoteTarget}
        onClose={() => setPromoteTarget(null)}
        onPromote={handlePromote}
      />
```

- [ ] **Step 3: Verify frontend compiles**

Run: `cd recipe-assistant/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Run full backend test suite (regression check)**

Run: `cd recipe-assistant/backend && python -m pytest -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/pages/PicnicImportPage.tsx \
       recipe-assistant/frontend/src/components/picnic/ReviewCard.tsx
git commit -m "feat(store): add barcode enrichment on PicnicImportPage"
```

---

## Task 11: Frontend Build Verification + Full Test Suite

**Files:** (none modified — verification only)

- [ ] **Step 1: Build frontend**

Run: `cd recipe-assistant/frontend && npx vite build`
Expected: Build succeeds

- [ ] **Step 2: Run full backend test suite**

Run: `cd recipe-assistant/backend && python -m pytest -v`
Expected: All tests pass

- [ ] **Step 3: Verify no untracked files or stale changes**

Run: `git status`
Expected: Clean working tree (only `tsconfig.tsbuildinfo` may differ)
