# Auto-Restock via Threshold — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user define a per-product reorder rule (`min_quantity` + `target_quantity`). When consumption drops an inventory item below its minimum via scanner, web UI, or manual edit, the product is automatically added to the existing in-app shopping list. The user still pushes the list into the real Picnic cart manually.

**Architecture:** New `tracked_products` table (independent of `inventory`, keyed by barcode, requires a resolvable Picnic SKU at creation). A service function `restock.check_and_enqueue` runs inline in the three decrement write paths (scan-out, remove, PUT) inside the caller's transaction. A new `/api/tracked-products/*` router handles CRUD + Picnic resolve preview. Frontend gets a "Nachbestellungen" page and a per-row restock button on the existing inventory page, joined client-side.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, pytest/pytest-asyncio, httpx AsyncClient. React 19 with plain `useState`/`useEffect` hooks (no React Query), MUI 6, react-zxing for barcode scanning.

**Spec:** `docs/superpowers/specs/2026-04-05-auto-restock-design.md`

---

## File Structure

### Backend — new files

- `recipe-assistant/backend/app/models/tracked_product.py` — `TrackedProduct` ORM model
- `recipe-assistant/backend/app/schemas/tracked_product.py` — Pydantic request/response schemas
- `recipe-assistant/backend/app/services/restock.py` — `check_and_enqueue` service function
- `recipe-assistant/backend/app/routers/tracked_products.py` — `/api/tracked-products/*` HTTP router
- `recipe-assistant/backend/alembic/versions/004_add_tracked_products.py` — Alembic migration
- `recipe-assistant/backend/tests/services/test_restock.py` — service unit tests
- `recipe-assistant/backend/tests/test_tracked_products_router.py` — router integration tests
- `recipe-assistant/backend/tests/test_inventory_restock.py` — integration tests for threshold firing through decrement paths

### Backend — modified files

- `recipe-assistant/backend/app/models/__init__.py` — register `TrackedProduct`
- `recipe-assistant/backend/app/main.py` — lifespan auto-create + router mount
- `recipe-assistant/backend/app/routers/inventory.py` — extract `_apply_decrement` helper, wire into `scan_out`, `remove`, `update_item`

### Frontend — new files

- `recipe-assistant/frontend/src/pages/TrackedProductsPage.tsx` — "Nachbestellungen" page
- `recipe-assistant/frontend/src/components/tracked/TrackedProductForm.tsx` — create/edit modal
- `recipe-assistant/frontend/src/components/tracked/TrackedProductCard.tsx` — single row in list
- `recipe-assistant/frontend/src/components/tracked/InventoryRestockButton.tsx` — badge/icon per inventory row
- `recipe-assistant/frontend/src/hooks/useTrackedProducts.ts` — data fetching + mutations

### Frontend — modified files

- `recipe-assistant/frontend/src/types/index.ts` — add `TrackedProduct`, `ResolvePreview` types
- `recipe-assistant/frontend/src/api/client.ts` — add API client functions
- `recipe-assistant/frontend/src/App.tsx` — mount `/tracked-products` route
- `recipe-assistant/frontend/src/components/Navbar.tsx` — sidebar link (Picnic-gated)
- `recipe-assistant/frontend/src/pages/InventoryPage.tsx` — per-row restock button + client-side join + zombie display

---

## Backend Tasks

### Task 1: TrackedProduct model and migration

**Files:**
- Create: `recipe-assistant/backend/app/models/tracked_product.py`
- Modify: `recipe-assistant/backend/app/models/__init__.py`
- Modify: `recipe-assistant/backend/app/main.py:17-26` (lifespan auto-create import list)
- Create: `recipe-assistant/backend/alembic/versions/004_add_tracked_products.py`

- [ ] **Step 1: Create the model file**

Create `recipe-assistant/backend/app/models/tracked_product.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrackedProduct(Base):
    """Auto-reorder rule for a product, keyed by EAN/barcode.

    Exists independently from InventoryItem — the rule persists even when
    the product is currently out of stock (quantity=0) or has never been
    in inventory. At creation time, the product MUST resolve to a Picnic
    SKU via get_article_by_gtin; picnic_id is enforced NOT NULL.
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
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("min_quantity >= 0", name="ck_tracked_min_nonneg"),
        CheckConstraint(
            "target_quantity > min_quantity",
            name="ck_tracked_target_gt_min",
        ),
    )
```

- [ ] **Step 2: Register the model in `__init__.py`**

Modify `recipe-assistant/backend/app/models/__init__.py` to add the import and export. The full new content:

```python
from app.models.inventory import InventoryItem, StorageLocation
from app.models.chat import ChatMessage
from app.models.log import InventoryLog
from app.models.person import Person
from app.models.picnic import (
    PicnicDeliveryImport,
    PicnicProduct,
    ShoppingListItem,
)
from app.models.tracked_product import TrackedProduct

__all__ = [
    "InventoryItem",
    "StorageLocation",
    "ChatMessage",
    "InventoryLog",
    "Person",
    "PicnicProduct",
    "PicnicDeliveryImport",
    "ShoppingListItem",
    "TrackedProduct",
]
```

- [ ] **Step 3: Add to lifespan auto-create list**

Modify `recipe-assistant/backend/app/main.py` lines 17-26. Replace the existing import block inside `lifespan()` with:

```python
        from app.models import (  # noqa: F401
            InventoryItem,
            StorageLocation,
            ChatMessage,
            InventoryLog,
            Person,
            PicnicProduct,
            PicnicDeliveryImport,
            ShoppingListItem,
            TrackedProduct,
        )
```

- [ ] **Step 4: Create the Alembic migration**

Create `recipe-assistant/backend/alembic/versions/004_add_tracked_products.py`:

```python
"""add tracked_products table

Revision ID: 004
Revises: 003
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_products",
        sa.Column("barcode", sa.String(), nullable=False),
        sa.Column("picnic_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("min_quantity", sa.Integer(), nullable=False),
        sa.Column("target_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("min_quantity >= 0", name="ck_tracked_min_nonneg"),
        sa.CheckConstraint(
            "target_quantity > min_quantity",
            name="ck_tracked_target_gt_min",
        ),
        sa.PrimaryKeyConstraint("barcode"),
    )


def downgrade() -> None:
    op.drop_table("tracked_products")
```

- [ ] **Step 5: Run the test suite to confirm nothing is broken**

Run: `cd recipe-assistant/backend && python -m pytest -q`

Expected: all existing tests pass. The new table is created by the `setup_db` autouse fixture via `Base.metadata.create_all`, so no migration command is needed in the test environment.

- [ ] **Step 6: Commit**

```bash
cd recipe-assistant/backend
git add app/models/tracked_product.py app/models/__init__.py app/main.py alembic/versions/004_add_tracked_products.py
git commit -m "$(cat <<'EOF'
feat(restock): add TrackedProduct model and migration

Adds the tracked_products table plus Alembic migration 004. The table
is keyed by barcode, requires a picnic_id (enforced NOT NULL), and
carries min_quantity + target_quantity with DB-level check constraints
that guarantee target > min.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Pydantic schemas for tracked-products API

**Files:**
- Create: `recipe-assistant/backend/app/schemas/tracked_product.py`

- [ ] **Step 1: Create the schemas file**

Create `recipe-assistant/backend/app/schemas/tracked_product.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrackedProductCreate(BaseModel):
    barcode: str = Field(min_length=1)
    min_quantity: int = Field(ge=0)
    target_quantity: int = Field(gt=0)

    @model_validator(mode="after")
    def _target_gt_min(self) -> "TrackedProductCreate":
        if self.target_quantity <= self.min_quantity:
            raise ValueError("target_quantity must be greater than min_quantity")
        return self


class TrackedProductUpdate(BaseModel):
    min_quantity: int | None = Field(default=None, ge=0)
    target_quantity: int | None = Field(default=None, gt=0)


class TrackedProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    barcode: str
    picnic_id: str
    name: str
    picnic_name: str
    picnic_image_id: str | None
    picnic_unit_quantity: str | None
    min_quantity: int
    target_quantity: int
    current_quantity: int
    below_threshold: bool
    created_at: datetime
    updated_at: datetime


class ResolvePreviewRequest(BaseModel):
    barcode: str = Field(min_length=1)


class ResolvePreviewResponse(BaseModel):
    resolved: bool
    picnic_id: str | None
    picnic_name: str | None
    picnic_image_id: str | None
    picnic_unit_quantity: str | None
    reason: str | None  # "cache_hit" | "live_lookup" | "not_in_picnic_catalog"
```

- [ ] **Step 2: Write schema validator tests**

Create `recipe-assistant/backend/tests/test_tracked_product_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.tracked_product import TrackedProductCreate


def test_create_accepts_valid_values():
    body = TrackedProductCreate(barcode="4014400900057", min_quantity=1, target_quantity=4)
    assert body.min_quantity == 1
    assert body.target_quantity == 4


def test_create_rejects_target_equal_to_min():
    with pytest.raises(ValidationError, match="greater than min_quantity"):
        TrackedProductCreate(barcode="123", min_quantity=2, target_quantity=2)


def test_create_rejects_target_less_than_min():
    with pytest.raises(ValidationError, match="greater than min_quantity"):
        TrackedProductCreate(barcode="123", min_quantity=5, target_quantity=3)


def test_create_rejects_negative_min():
    with pytest.raises(ValidationError):
        TrackedProductCreate(barcode="123", min_quantity=-1, target_quantity=3)


def test_create_rejects_zero_target():
    with pytest.raises(ValidationError):
        TrackedProductCreate(barcode="123", min_quantity=0, target_quantity=0)


def test_create_rejects_empty_barcode():
    with pytest.raises(ValidationError):
        TrackedProductCreate(barcode="", min_quantity=1, target_quantity=2)
```

- [ ] **Step 3: Run the schema tests**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_tracked_product_schemas.py -v`

Expected: all 6 tests pass.

- [ ] **Step 4: Commit**

```bash
cd recipe-assistant/backend
git add app/schemas/tracked_product.py tests/test_tracked_product_schemas.py
git commit -m "$(cat <<'EOF'
feat(restock): add Pydantic schemas for tracked-products API

Schemas enforce target_quantity > min_quantity at the API layer
(defense in depth alongside the DB check constraint). Schema tests
cover the validator, boundary cases, and rejection of empty barcodes.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Restock service with unit tests

**Files:**
- Create: `recipe-assistant/backend/app/services/restock.py`
- Create: `recipe-assistant/backend/tests/services/test_restock.py`

- [ ] **Step 1: Write the failing unit tests**

Create `recipe-assistant/backend/tests/services/test_restock.py`:

```python
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import InventoryLog
from app.models.picnic import ShoppingListItem
from app.models.tracked_product import TrackedProduct
from app.services.restock import check_and_enqueue
from tests.conftest import TestingSessionLocal


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


async def _seed_tracked(
    db: AsyncSession,
    *,
    barcode: str,
    picnic_id: str = "s100",
    name: str = "Ja! Vollmilch 1 L",
    min_quantity: int = 2,
    target_quantity: int = 5,
) -> TrackedProduct:
    tp = TrackedProduct(
        barcode=barcode,
        picnic_id=picnic_id,
        name=name,
        min_quantity=min_quantity,
        target_quantity=target_quantity,
    )
    db.add(tp)
    await db.flush()
    return tp


@pytest.mark.asyncio
async def test_no_tracked_rule_returns_none(db: AsyncSession):
    result = await check_and_enqueue(db, barcode="no-such", new_quantity=0)
    assert result is None
    count = (await db.execute(select(ShoppingListItem))).scalars().all()
    assert count == []


@pytest.mark.asyncio
async def test_quantity_at_or_above_min_returns_none(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", min_quantity=2, target_quantity=5)
    result = await check_and_enqueue(db, barcode="b1", new_quantity=2)
    assert result is None
    items = (await db.execute(select(ShoppingListItem))).scalars().all()
    assert items == []


@pytest.mark.asyncio
async def test_below_threshold_creates_shopping_list_entry(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", min_quantity=2, target_quantity=5)

    result = await check_and_enqueue(db, barcode="b1", new_quantity=1)

    assert result is not None
    assert result.added_quantity == 4  # target=5 - current=1
    assert result.shopping_list_item_id is not None
    items = (await db.execute(select(ShoppingListItem))).scalars().all()
    assert len(items) == 1
    assert items[0].inventory_barcode == "b1"
    assert items[0].picnic_id == "s100"
    assert items[0].quantity == 4


@pytest.mark.asyncio
async def test_below_threshold_with_zero_quantity_fills_to_target(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", min_quantity=2, target_quantity=5)

    result = await check_and_enqueue(db, barcode="b1", new_quantity=0)

    assert result is not None
    assert result.added_quantity == 5
    items = (await db.execute(select(ShoppingListItem))).scalars().all()
    assert items[0].quantity == 5


@pytest.mark.asyncio
async def test_existing_shopping_list_entry_quantity_raised(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", min_quantity=2, target_quantity=5)
    # User-created entry already on list, smaller than what threshold needs
    db.add(
        ShoppingListItem(
            inventory_barcode="b1", picnic_id="s100", name="Milch", quantity=1
        )
    )
    await db.flush()

    result = await check_and_enqueue(db, barcode="b1", new_quantity=0)

    assert result is not None
    items = (await db.execute(select(ShoppingListItem))).scalars().all()
    assert len(items) == 1  # no duplicate
    assert items[0].quantity == 5  # raised from 1 to needed=5


@pytest.mark.asyncio
async def test_existing_entry_with_larger_quantity_not_reduced(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", min_quantity=2, target_quantity=5)
    # User bumped the quantity beyond what auto-fill would add
    db.add(
        ShoppingListItem(
            inventory_barcode="b1", picnic_id="s100", name="Milch", quantity=10
        )
    )
    await db.flush()

    result = await check_and_enqueue(db, barcode="b1", new_quantity=0)

    assert result is not None
    items = (await db.execute(select(ShoppingListItem))).scalars().all()
    assert len(items) == 1
    assert items[0].quantity == 10  # unchanged, never reduce


@pytest.mark.asyncio
async def test_restock_writes_inventory_log(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", min_quantity=2, target_quantity=5)

    await check_and_enqueue(db, barcode="b1", new_quantity=1)

    logs = (
        await db.execute(
            select(InventoryLog).where(InventoryLog.barcode == "b1")
        )
    ).scalars().all()
    assert any(log.action == "restock_auto" for log in logs)
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/test_restock.py -v`

Expected: import error — `app.services.restock` does not exist yet.

- [ ] **Step 3: Implement the service**

Create `recipe-assistant/backend/app/services/restock.py`:

```python
"""Auto-restock service: checks inventory decrements against tracked-product
thresholds and seeds the shopping list when consumption drops below `min_quantity`.

Add-only semantics: we only add or raise shopping list quantities, never
remove or reduce. Rationale documented in
docs/superpowers/specs/2026-04-05-auto-restock-design.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import InventoryLog
from app.models.picnic import ShoppingListItem
from app.models.tracked_product import TrackedProduct

log = logging.getLogger("restock")


@dataclass(frozen=True)
class RestockResult:
    barcode: str
    added_quantity: int
    shopping_list_item_id: int


async def check_and_enqueue(
    db: AsyncSession,
    barcode: str,
    new_quantity: int,
) -> RestockResult | None:
    """Check if `new_quantity` crossed the threshold for `barcode` and
    upsert the shopping list accordingly.

    MUST be called by the caller AFTER decrementing inventory, BEFORE
    db.commit(). Runs in the caller's transaction — either both writes
    land or neither. This function does not commit.

    Returns None if no tracked rule exists or if new_quantity >= min_quantity.
    Returns RestockResult(...) if the shopping list was upserted.
    """
    tracked = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()
    if tracked is None:
        return None
    if new_quantity >= tracked.min_quantity:
        return None

    needed = tracked.target_quantity - new_quantity
    # Defensive: target > min > 0 and new_quantity < min, so needed > 0. If
    # something upstream bypassed the check constraints, fail loudly.
    if needed <= 0:
        raise ValueError(
            f"tracked_products row for {barcode} is inconsistent: "
            f"target={tracked.target_quantity} new_qty={new_quantity}"
        )

    # Dedup against any existing shopping list entry for this barcode. Pick
    # the most recent one if multiple somehow exist; raise its quantity if
    # smaller, leave it alone if larger.
    existing = (
        await db.execute(
            select(ShoppingListItem)
            .where(ShoppingListItem.inventory_barcode == barcode)
            .order_by(ShoppingListItem.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.quantity < needed:
            existing.quantity = needed
        item_id = existing.id
    else:
        new_item = ShoppingListItem(
            inventory_barcode=barcode,
            picnic_id=tracked.picnic_id,
            name=tracked.name,
            quantity=needed,
        )
        db.add(new_item)
        await db.flush()
        item_id = new_item.id

    db.add(
        InventoryLog(
            barcode=barcode,
            action="restock_auto",
            details=f"qty→{new_quantity}, list qty={needed}",
        )
    )

    log.info(
        "restock_auto barcode=%s new_qty=%d needed=%d item_id=%s",
        barcode,
        new_quantity,
        needed,
        item_id,
    )
    return RestockResult(
        barcode=barcode,
        added_quantity=needed,
        shopping_list_item_id=item_id,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/test_restock.py -v`

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
cd recipe-assistant/backend
git add app/services/restock.py tests/services/test_restock.py
git commit -m "$(cat <<'EOF'
feat(restock): add check_and_enqueue service

Pure database-only service. Called by inventory decrement endpoints
after mutating InventoryItem but before committing. Adds or raises a
ShoppingListItem entry when the new quantity drops below the tracked
product's min_quantity. Never reduces or removes entries (add-only
semantics per spec).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Decrement helper refactor + wire into inventory router

**Files:**
- Modify: `recipe-assistant/backend/app/routers/inventory.py` (scan_out, remove, update_item paths + new `_apply_decrement` helper)
- Create: `recipe-assistant/backend/tests/test_inventory_restock.py`

This is the riskiest task — it changes existing behavior (inventory deletion at quantity=0 is now conditional) and touches three endpoints. Keep the refactor narrow: only the decrement branches are changed; increment branches are untouched.

- [ ] **Step 1: Write the integration tests first (they will fail)**

Create `recipe-assistant/backend/tests/test_inventory_restock.py`:

```python
"""Integration tests for the restock trigger firing through inventory
decrement paths. Covers scan-out, /remove, and PUT /{barcode} (manual
quantity edit). Each test seeds a TrackedProduct directly in the DB
because the /api/tracked-products/* router is added in a later task.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.inventory import InventoryItem
from app.models.picnic import ShoppingListItem
from app.models.tracked_product import TrackedProduct
from tests.conftest import TestingSessionLocal


async def _seed(*, barcode: str, quantity: int, tracked: bool = True) -> None:
    async with TestingSessionLocal() as session:
        session.add(InventoryItem(barcode=barcode, name="Milch", quantity=quantity))
        if tracked:
            session.add(
                TrackedProduct(
                    barcode=barcode,
                    picnic_id="s100",
                    name="Ja! Vollmilch 1 L",
                    min_quantity=2,
                    target_quantity=5,
                )
            )
        await session.commit()


async def _shopping_list_entries(barcode: str) -> list[ShoppingListItem]:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(ShoppingListItem).where(
                ShoppingListItem.inventory_barcode == barcode
            )
        )
        return list(result.scalars().all())


async def _inventory_row(barcode: str) -> InventoryItem | None:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(InventoryItem).where(InventoryItem.barcode == barcode)
        )
        return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_scan_out_below_threshold_seeds_shopping_list(client: AsyncClient):
    await _seed(barcode="b1", quantity=3)

    response = await client.post("/api/inventory/scan-out", json={"barcode": "b1"})
    assert response.status_code == 200
    assert response.json()["remaining_quantity"] == 2

    # qty=2 == min_quantity; should NOT fire
    assert await _shopping_list_entries("b1") == []

    response = await client.post("/api/inventory/scan-out", json={"barcode": "b1"})
    assert response.json()["remaining_quantity"] == 1
    entries = await _shopping_list_entries("b1")
    assert len(entries) == 1
    assert entries[0].quantity == 4  # target=5 - current=1


@pytest.mark.asyncio
async def test_scan_out_last_item_keeps_zombie_row_when_tracked(client: AsyncClient):
    await _seed(barcode="b1", quantity=1)

    response = await client.post("/api/inventory/scan-out", json={"barcode": "b1"})
    assert response.status_code == 200
    assert response.json()["remaining_quantity"] == 0
    assert response.json()["deleted"] is False  # new rule: tracked → keep row

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 0

    entries = await _shopping_list_entries("b1")
    assert len(entries) == 1
    assert entries[0].quantity == 5  # full target, since new_qty=0


@pytest.mark.asyncio
async def test_scan_out_last_item_still_deletes_when_not_tracked(client: AsyncClient):
    await _seed(barcode="b2", quantity=1, tracked=False)

    response = await client.post("/api/inventory/scan-out", json={"barcode": "b2"})
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    assert await _inventory_row("b2") is None
    assert await _shopping_list_entries("b2") == []


@pytest.mark.asyncio
async def test_repeated_scan_out_raises_quantity_no_duplicates(client: AsyncClient):
    await _seed(barcode="b1", quantity=3)

    await client.post("/api/inventory/scan-out", json={"barcode": "b1"})  # 3→2, no fire
    await client.post("/api/inventory/scan-out", json={"barcode": "b1"})  # 2→1, fires, needed=4
    await client.post("/api/inventory/scan-out", json={"barcode": "b1"})  # 1→0, fires, needed=5

    entries = await _shopping_list_entries("b1")
    assert len(entries) == 1
    assert entries[0].quantity == 5


@pytest.mark.asyncio
async def test_remove_endpoint_fires_trigger(client: AsyncClient):
    await _seed(barcode="b1", quantity=2)  # qty=2 == min, still ok

    response = await client.post("/api/inventory/remove", json={"barcode": "b1"})
    assert response.status_code == 200

    entries = await _shopping_list_entries("b1")
    assert len(entries) == 1
    assert entries[0].quantity == 4  # target=5 - current=1


@pytest.mark.asyncio
async def test_remove_last_item_keeps_zombie_when_tracked(client: AsyncClient):
    await _seed(barcode="b1", quantity=1)

    response = await client.post("/api/inventory/remove", json={"barcode": "b1"})
    assert response.status_code == 200

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 0
    entries = await _shopping_list_entries("b1")
    assert entries[0].quantity == 5


@pytest.mark.asyncio
async def test_put_quantity_edit_below_threshold_fires(client: AsyncClient):
    await _seed(barcode="b1", quantity=5)

    response = await client.put("/api/inventory/b1", json={"quantity": 1})
    assert response.status_code == 200

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 1
    entries = await _shopping_list_entries("b1")
    assert entries[0].quantity == 4


@pytest.mark.asyncio
async def test_put_quantity_to_zero_keeps_zombie_when_tracked(client: AsyncClient):
    await _seed(barcode="b1", quantity=5)

    response = await client.put("/api/inventory/b1", json={"quantity": 0})
    assert response.status_code == 200

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 0
    entries = await _shopping_list_entries("b1")
    assert entries[0].quantity == 5


@pytest.mark.asyncio
async def test_put_quantity_increase_does_not_fire(client: AsyncClient):
    await _seed(barcode="b1", quantity=3)

    response = await client.put("/api/inventory/b1", json={"quantity": 10})
    assert response.status_code == 200

    assert await _shopping_list_entries("b1") == []


@pytest.mark.asyncio
async def test_scan_in_into_zombie_does_not_prune_shopping_list(client: AsyncClient):
    await _seed(barcode="b1", quantity=1)
    # Trigger a zombie
    await client.post("/api/inventory/scan-out", json={"barcode": "b1"})
    entries_before = await _shopping_list_entries("b1")
    assert entries_before[0].quantity == 5

    # Scan back in — inventory row revives, shopping list unchanged
    response = await client.post(
        "/api/inventory/scan-in", json={"barcode": "b1", "storage_location_id": None}
    )
    assert response.status_code == 200

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 1  # zombie revived, not recreated
    entries_after = await _shopping_list_entries("b1")
    assert len(entries_after) == 1
    assert entries_after[0].quantity == 5  # unchanged, add-only semantics
```

- [ ] **Step 2: Run the tests to verify they fail in the expected way**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_inventory_restock.py -v`

Expected: most tests fail — the current router still deletes rows at qty=0 and never calls the restock service. The `test_scan_out_last_item_still_deletes_when_not_tracked` test may pass (existing behavior), and `test_put_quantity_increase_does_not_fire` may pass (no trigger wired yet). The rest should fail with assertion errors about missing shopping list entries or missing zombie rows.

- [ ] **Step 3: Refactor inventory router — add the `_apply_decrement` helper**

Modify `recipe-assistant/backend/app/routers/inventory.py`. Add two imports near the top (around line 25, after the existing `from app.services.barcode import lookup_barcode` line):

```python
from app.services.barcode import lookup_barcode
from app.services.restock import check_and_enqueue
from app.models.tracked_product import TrackedProduct
```

Then add the helper function right after the existing `_resolve_storage_location` helper (around line 45, before the `@router.get("/")` decorator):

```python
async def _apply_decrement(
    db: AsyncSession,
    item: InventoryItem,
    new_quantity: int,
    *,
    action: str,
    log_details: str,
) -> bool:
    """Apply a quantity decrement plus tracking-aware rules.

    - Sets item.quantity = new_quantity.
    - If new_quantity == 0 and the product has a TrackedProduct rule,
      the row is kept (zombie); otherwise it is deleted.
    - Runs restock.check_and_enqueue, which may upsert a ShoppingListItem
      in the same transaction.
    - Writes an InventoryLog entry with the given action and details.

    Returns True if the inventory row was deleted, False if it was kept.
    Caller must still commit the transaction.
    """
    tracked = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == item.barcode)
        )
    ).scalar_one_or_none()

    if new_quantity <= 0 and tracked is None:
        await _log_action(db, item.barcode, action, log_details)
        await db.delete(item)
        return True

    item.quantity = new_quantity
    await _log_action(db, item.barcode, action, log_details)
    await check_and_enqueue(db, barcode=item.barcode, new_quantity=new_quantity)
    return False
```

- [ ] **Step 4: Rewrite `scan_out` to use the helper**

Replace lines 226-250 of `recipe-assistant/backend/app/routers/inventory.py` (the block starting at `name = item.name` and ending at `"deleted": True,\n    }`). The new block:

```python
    name = item.name
    old_qty = item.quantity
    new_qty = old_qty - 1
    deleted = await _apply_decrement(
        db,
        item,
        new_qty,
        action="scan-out",
        log_details=(
            f"quantity: {old_qty} → {new_qty}"
            if new_qty > 0
            else "removed last item"
        ),
    )
    await db.commit()
    return {
        "status": "ok",
        "barcode": req.barcode,
        "name": name,
        "remaining_quantity": max(new_qty, 0),
        "deleted": deleted,
    }
```

- [ ] **Step 5: Rewrite `remove_item_by_barcode` to use the helper**

Replace lines 160-170 of `recipe-assistant/backend/app/routers/inventory.py` (the block from `if item.quantity > 1:` through the final `return` of the function). The new block:

```python
    old_qty = item.quantity
    new_qty = old_qty - 1
    deleted = await _apply_decrement(
        db,
        item,
        new_qty,
        action="remove" if new_qty > 0 else "delete",
        log_details=(
            f"quantity: {old_qty} → {new_qty}"
            if new_qty > 0
            else "removed last item"
        ),
    )
    await db.commit()
    if deleted:
        return {"message": f"Produkt mit Barcode {req.barcode} wurde entfernt."}
    return {"message": f"Produkt um 1 reduziert. Verbleibend: {new_qty}"}
```

- [ ] **Step 6: Rewrite the quantity-edit branch of `update_item`**

Modify `recipe-assistant/backend/app/routers/inventory.py`, the `update_item` function (starts at line 352). Replace the quantity-handling block (currently lines 365-373) with:

```python
    if req.quantity is not None:
        old_qty = item.quantity
        if req.quantity < old_qty:
            # Decrement path: helper enforces delete-iff-not-tracked and
            # fires the restock check.
            deleted = await _apply_decrement(
                db,
                item,
                req.quantity,
                action="update" if req.quantity > 0 else "delete",
                log_details=f"quantity: {old_qty} → {req.quantity}",
            )
            if deleted:
                await db.commit()
                return {"message": f"Artikel mit Barcode {barcode} wurde gelöscht."}
        else:
            # Non-decrement (increment or no-op on quantity): no restock
            # check, no delete rule — simple assignment.
            item.quantity = req.quantity
            await _log_action(
                db, barcode, "update", f"quantity: {old_qty} → {req.quantity}"
            )
```

- [ ] **Step 7: Run the restock integration tests**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_inventory_restock.py -v`

Expected: all 10 tests pass.

- [ ] **Step 8: Run the full inventory test suite to verify no regressions**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_inventory.py tests/test_inventory_restock.py -v`

Expected: all existing inventory tests pass (including `test_update_quantity_to_zero_deletes` and `test_remove_last_item_deletes`, both of which use non-tracked products and thus exercise the unchanged-behavior branch of the helper). If any fail, diagnose: likely the old-behavior branch in the helper is wrong, not the test.

- [ ] **Step 9: Run the full backend test suite**

Run: `cd recipe-assistant/backend && python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
cd recipe-assistant/backend
git add app/routers/inventory.py tests/test_inventory_restock.py
git commit -m "$(cat <<'EOF'
feat(restock): wire threshold check into inventory decrement paths

Extracts a shared _apply_decrement helper and routes scan-out, /remove,
and PUT /{barcode} through it. The helper enforces two tracked-product
rules: InventoryItem rows are kept (as zombies with quantity=0) when a
tracked rule exists, and restock.check_and_enqueue runs in the same
transaction as the decrement. Non-tracked products retain their
existing delete-on-zero behavior.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Tracked-products router + mount in main.py

**Files:**
- Create: `recipe-assistant/backend/app/routers/tracked_products.py`
- Modify: `recipe-assistant/backend/app/main.py` (mount the new router)
- Create: `recipe-assistant/backend/tests/test_tracked_products_router.py`

- [ ] **Step 1: Write the failing integration tests**

Create `recipe-assistant/backend/tests/test_tracked_products_router.py`:

```python
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.picnic import ShoppingListItem
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


@pytest.mark.asyncio
async def test_resolve_preview_hit(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products/resolve-preview",
        json={"barcode": "4014400900057"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["picnic_id"] == "s100"
    assert data["picnic_name"] == "Ja! Vollmilch 1 L"


@pytest.mark.asyncio
async def test_resolve_preview_miss(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products/resolve-preview",
        json={"barcode": "0000000000000"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is False
    assert data["reason"] == "not_in_picnic_catalog"


@pytest.mark.asyncio
async def test_create_tracked_product(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["barcode"] == "4014400900057"
    assert data["picnic_id"] == "s100"
    assert data["min_quantity"] == 1
    assert data["target_quantity"] == 4
    assert data["current_quantity"] == 0
    assert data["below_threshold"] is True  # qty=0 < min=1


@pytest.mark.asyncio
async def test_create_seeds_shopping_list_if_below_threshold(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 201

    async with TestingSessionLocal() as session:
        items = (await session.execute(select(ShoppingListItem))).scalars().all()
    assert len(items) == 1
    assert items[0].inventory_barcode == "4014400900057"
    assert items[0].quantity == 4  # target - current=0


@pytest.mark.asyncio
async def test_create_not_in_picnic_catalog_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "0000000000000", "min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 422
    # FastAPI wraps HTTPException(detail={...}) into {"detail": {...}}
    detail = response.json()["detail"]
    assert detail["error"] == "picnic_product_not_found"


@pytest.mark.asyncio
async def test_create_target_le_min_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 5, "target_quantity": 3},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_duplicate_returns_409(client: AsyncClient):
    payload = {
        "barcode": "4014400900057",
        "min_quantity": 1,
        "target_quantity": 4,
    }
    await client.post("/api/tracked-products", json=payload)
    response = await client.post("/api/tracked-products", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_tracked_products_joins_current_quantity(client: AsyncClient):
    # Seed inventory with a quantity
    await client.post(
        "/api/inventory/barcode", json={"barcode": "4014400900057"}
    )
    await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )

    response = await client.get("/api/tracked-products")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["current_quantity"] == 1
    assert items[0]["below_threshold"] is False  # qty=1 == min=1


@pytest.mark.asyncio
async def test_patch_tracked_product_updates_and_rechecks(client: AsyncClient):
    # Seed qty=1 inventory and rule min=1 target=2 → not below threshold
    await client.post(
        "/api/inventory/barcode", json={"barcode": "4014400900057"}
    )
    await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 2},
    )
    async with TestingSessionLocal() as session:
        items = (await session.execute(select(ShoppingListItem))).scalars().all()
    assert items == []

    # Raise min_quantity to 3 → now below threshold, check should fire
    response = await client.patch(
        "/api/tracked-products/4014400900057",
        json={"min_quantity": 3, "target_quantity": 5},
    )
    assert response.status_code == 200
    assert response.json()["below_threshold"] is True

    async with TestingSessionLocal() as session:
        items = (await session.execute(select(ShoppingListItem))).scalars().all()
    assert len(items) == 1
    assert items[0].quantity == 4  # target=5 - current=1


@pytest.mark.asyncio
async def test_delete_tracked_product(client: AsyncClient):
    await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )
    response = await client.delete("/api/tracked-products/4014400900057")
    assert response.status_code == 200

    listing = await client.get("/api/tracked-products")
    assert listing.json() == []


@pytest.mark.asyncio
async def test_patch_nonexistent_returns_404(client: AsyncClient):
    response = await client.patch(
        "/api/tracked-products/nope", json={"min_quantity": 1, "target_quantity": 2}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_feature_disabled_returns_503(client: AsyncClient, monkeypatch):
    monkeypatch.delenv("PICNIC_MAIL", raising=False)
    monkeypatch.delenv("PICNIC_PASSWORD", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    response = await client.get("/api/tracked-products")
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "picnic_not_configured"
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_tracked_products_router.py -v`

Expected: all tests fail with 404 responses (the router is not mounted yet).

- [ ] **Step 3: Implement the router**

Create `recipe-assistant/backend/app/routers/tracked_products.py`:

```python
"""HTTP router for per-product auto-restock rules.

All endpoints require the Picnic feature to be configured (mirrors the
gate in app.routers.picnic). Tracked products can only be created for
products that resolve to a Picnic SKU via get_article_by_gtin.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.inventory import InventoryItem
from app.models.picnic import PicnicProduct
from app.models.tracked_product import TrackedProduct
from app.schemas.tracked_product import (
    ResolvePreviewRequest,
    ResolvePreviewResponse,
    TrackedProductCreate,
    TrackedProductRead,
    TrackedProductUpdate,
)
from app.services.picnic.catalog import (
    PicnicProductData,
    get_product_by_ean,
    upsert_product,
)
from app.services.picnic.client import (
    PicnicClientProtocol,
    PicnicNotConfigured,
    PicnicReauthRequired,
    get_picnic_client,
)
from app.services.restock import check_and_enqueue

log = logging.getLogger("tracked_products.router")

router = APIRouter()


def _feature_enabled() -> bool:
    s = get_settings()
    return bool(s.picnic_email and s.picnic_password)


def _require_enabled() -> None:
    if not _feature_enabled():
        raise HTTPException(
            status_code=503,
            detail={"error": "picnic_not_configured"},
        )


async def _resolve_picnic(
    db: AsyncSession,
    client: PicnicClientProtocol,
    barcode: str,
) -> tuple[PicnicProduct | None, str]:
    """Cache-first Picnic lookup by EAN. Returns (row, reason).

    reason ∈ {"cache_hit", "live_lookup", "not_in_picnic_catalog"}.
    On live hit, caches into picnic_products before returning.
    """
    cached = await get_product_by_ean(db, barcode)
    if cached is not None:
        return cached, "cache_hit"

    result = await client.get_article_by_gtin(barcode)
    if result is None:
        return None, "not_in_picnic_catalog"

    row = await upsert_product(
        db,
        PicnicProductData(
            picnic_id=result["id"],
            ean=barcode,
            name=result["name"],
            unit_quantity=result.get("unit_quantity"),
            image_id=result.get("image_id"),
            last_price_cents=result.get("display_price"),
        ),
    )
    return row, "live_lookup"


async def _current_inventory_quantity(db: AsyncSession, barcode: str) -> int:
    row = (
        await db.execute(
            select(InventoryItem).where(InventoryItem.barcode == barcode)
        )
    ).scalar_one_or_none()
    return row.quantity if row is not None else 0


async def _build_read_model(
    db: AsyncSession, tp: TrackedProduct
) -> TrackedProductRead:
    picnic_row = (
        await db.execute(
            select(PicnicProduct).where(PicnicProduct.picnic_id == tp.picnic_id)
        )
    ).scalar_one_or_none()
    current_qty = await _current_inventory_quantity(db, tp.barcode)
    return TrackedProductRead(
        barcode=tp.barcode,
        picnic_id=tp.picnic_id,
        name=tp.name,
        picnic_name=picnic_row.name if picnic_row else tp.name,
        picnic_image_id=picnic_row.image_id if picnic_row else None,
        picnic_unit_quantity=picnic_row.unit_quantity if picnic_row else None,
        min_quantity=tp.min_quantity,
        target_quantity=tp.target_quantity,
        current_quantity=current_qty,
        below_threshold=current_qty < tp.min_quantity,
        created_at=tp.created_at,
        updated_at=tp.updated_at,
    )


@router.get("", response_model=list[TrackedProductRead])
async def list_tracked(db: AsyncSession = Depends(get_db)):
    _require_enabled()
    rows = (
        await db.execute(
            select(TrackedProduct).order_by(TrackedProduct.created_at.desc())
        )
    ).scalars().all()
    results: list[TrackedProductRead] = []
    for row in rows:
        results.append(await _build_read_model(db, row))
    # Sort by below_threshold desc so action items float to the top.
    results.sort(key=lambda r: (not r.below_threshold, r.barcode))
    return results


@router.post(
    "/resolve-preview",
    response_model=ResolvePreviewResponse,
)
async def resolve_preview(
    req: ResolvePreviewRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        row, reason = await _resolve_picnic(db, client, req.barcode)
    except PicnicNotConfigured:
        raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})
    await db.commit()
    if row is None:
        return ResolvePreviewResponse(
            resolved=False,
            picnic_id=None,
            picnic_name=None,
            picnic_image_id=None,
            picnic_unit_quantity=None,
            reason=reason,
        )
    return ResolvePreviewResponse(
        resolved=True,
        picnic_id=row.picnic_id,
        picnic_name=row.name,
        picnic_image_id=row.image_id,
        picnic_unit_quantity=row.unit_quantity,
        reason=reason,
    )


@router.post("", response_model=TrackedProductRead, status_code=201)
async def create_tracked(
    req: TrackedProductCreate,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()

    # Reject duplicate up front before hitting Picnic API.
    existing = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == req.barcode)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "already_tracked", "barcode": req.barcode},
        )

    # Resolve against Picnic (required for creation).
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

    tp = TrackedProduct(
        barcode=req.barcode,
        picnic_id=picnic_row.picnic_id,
        name=display_name,
        min_quantity=req.min_quantity,
        target_quantity=req.target_quantity,
    )
    db.add(tp)
    await db.flush()

    # Immediate check: if the inventory quantity is already below the new
    # threshold, seed the shopping list in the same transaction.
    current_qty = inventory_row.quantity if inventory_row is not None else 0
    await check_and_enqueue(db, barcode=req.barcode, new_quantity=current_qty)

    result = await _build_read_model(db, tp)
    await db.commit()
    return result


@router.patch("/{barcode}", response_model=TrackedProductRead)
async def update_tracked(
    barcode: str,
    req: TrackedProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()

    tp = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()
    if tp is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})

    new_min = req.min_quantity if req.min_quantity is not None else tp.min_quantity
    new_target = (
        req.target_quantity if req.target_quantity is not None else tp.target_quantity
    )
    if new_target <= new_min:
        raise HTTPException(
            status_code=422,
            detail={"error": "target_must_exceed_min"},
        )

    tp.min_quantity = new_min
    tp.target_quantity = new_target
    await db.flush()

    # Re-run the threshold check so a raised min_quantity/target_quantity
    # is reflected in the shopping list. Lowered thresholds are no-ops by
    # add-only semantics.
    current_qty = await _current_inventory_quantity(db, barcode)
    await check_and_enqueue(db, barcode=barcode, new_quantity=current_qty)

    result = await _build_read_model(db, tp)
    await db.commit()
    return result


@router.delete("/{barcode}")
async def delete_tracked(barcode: str, db: AsyncSession = Depends(get_db)):
    _require_enabled()
    tp = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()
    if tp is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    await db.delete(tp)
    await db.commit()
    return {"message": "deleted"}
```

- [ ] **Step 4: Mount the router in `main.py`**

Modify `recipe-assistant/backend/app/main.py`. Add the import near line 10:

```python
from app.routers import inventory, storage, assistant, persons, picnic, tracked_products
```

And add the mount after the existing `picnic` router line (around line 38):

```python
app.include_router(picnic.router, prefix="/api/picnic", tags=["picnic"])
app.include_router(
    tracked_products.router,
    prefix="/api/tracked-products",
    tags=["tracked-products"],
)
```

- [ ] **Step 5: Run the router tests**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_tracked_products_router.py -v`

Expected: all 12 tests pass.

- [ ] **Step 6: Run the full backend test suite**

Run: `cd recipe-assistant/backend && python -m pytest -q`

Expected: everything passes.

- [ ] **Step 7: Commit**

```bash
cd recipe-assistant/backend
git add app/routers/tracked_products.py app/main.py tests/test_tracked_products_router.py
git commit -m "$(cat <<'EOF'
feat(restock): add /api/tracked-products router

CRUD + resolve-preview endpoints for per-product auto-restock rules.
Creating a rule requires a successful Picnic EAN lookup (HTTP 422 on
miss). The POST flow runs an immediate threshold check so below-limit
products seed the shopping list in the same transaction. PATCH
re-checks to let raised thresholds propagate.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Frontend Tasks

The frontend has no test framework (no vitest/jest), so these tasks rely on the backend integration tests plus the `tsc -b && vite build` type check and a manual smoke test. Follow the existing patterns in `hooks/usePicnic.ts`, `pages/ShoppingListPage.tsx`, and `pages/PicnicImportPage.tsx`.

### Task 6: Frontend types and API client functions

**Files:**
- Modify: `recipe-assistant/frontend/src/types/index.ts`
- Modify: `recipe-assistant/frontend/src/api/client.ts`

- [ ] **Step 1: Add TypeScript types**

Append to `recipe-assistant/frontend/src/types/index.ts` (at the end of the file):

```typescript
// Tracked products (auto-restock)
export interface TrackedProduct {
  barcode: string;
  picnic_id: string;
  name: string;
  picnic_name: string;
  picnic_image_id: string | null;
  picnic_unit_quantity: string | null;
  min_quantity: number;
  target_quantity: number;
  current_quantity: number;
  below_threshold: boolean;
  created_at: string;
  updated_at: string;
}

export interface TrackedProductCreate {
  barcode: string;
  min_quantity: number;
  target_quantity: number;
}

export interface TrackedProductUpdate {
  min_quantity?: number;
  target_quantity?: number;
}

export interface ResolvePreview {
  resolved: boolean;
  picnic_id: string | null;
  picnic_name: string | null;
  picnic_image_id: string | null;
  picnic_unit_quantity: string | null;
  reason: string | null;
}
```

- [ ] **Step 2: Add API client functions**

Append to `recipe-assistant/frontend/src/api/client.ts` (at the end of the file). First add the imports to the top import block:

```typescript
import type {
  // ... existing imports ...
  TrackedProduct,
  TrackedProductCreate,
  TrackedProductUpdate,
  ResolvePreview,
} from "../types";
```

Then append at the bottom of the file:

```typescript
// Tracked products (auto-restock)
export const listTrackedProducts = () =>
  request<TrackedProduct[]>("/tracked-products");

export const createTrackedProduct = (data: TrackedProductCreate) =>
  request<TrackedProduct>("/tracked-products", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateTrackedProduct = (
  barcode: string,
  data: TrackedProductUpdate
) =>
  request<TrackedProduct>(`/tracked-products/${encodeURIComponent(barcode)}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const deleteTrackedProduct = (barcode: string) =>
  request<{ message: string }>(
    `/tracked-products/${encodeURIComponent(barcode)}`,
    { method: "DELETE" }
  );

export const resolveTrackedProductPreview = (barcode: string) =>
  request<ResolvePreview>("/tracked-products/resolve-preview", {
    method: "POST",
    body: JSON.stringify({ barcode }),
  });
```

- [ ] **Step 3: Type-check**

Run: `cd recipe-assistant/frontend && npx tsc -b`

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd recipe-assistant/frontend
git add src/types/index.ts src/api/client.ts
git commit -m "$(cat <<'EOF'
feat(restock): add frontend types and API client for tracked products

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: useTrackedProducts hook

**Files:**
- Create: `recipe-assistant/frontend/src/hooks/useTrackedProducts.ts`

- [ ] **Step 1: Create the hook**

Create `recipe-assistant/frontend/src/hooks/useTrackedProducts.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";
import {
  listTrackedProducts,
  createTrackedProduct,
  updateTrackedProduct,
  deleteTrackedProduct,
  resolveTrackedProductPreview,
} from "../api/client";
import type {
  TrackedProduct,
  TrackedProductCreate,
  TrackedProductUpdate,
  ResolvePreview,
} from "../types";

export function useTrackedProducts() {
  const [items, setItems] = useState<TrackedProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listTrackedProducts());
    } catch (e) {
      // 503 when Picnic is disabled → render as empty state
      setItems([]);
      setError(e instanceof Error ? e.message : "Fehler");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const create = async (data: TrackedProductCreate) => {
    const result = await createTrackedProduct(data);
    await refetch();
    return result;
  };

  const update = async (barcode: string, data: TrackedProductUpdate) => {
    const result = await updateTrackedProduct(barcode, data);
    await refetch();
    return result;
  };

  const remove = async (barcode: string) => {
    await deleteTrackedProduct(barcode);
    await refetch();
  };

  return { items, loading, error, refetch, create, update, remove };
}

export function useResolvePreview() {
  const [preview, setPreview] = useState<ResolvePreview | null>(null);
  const [loading, setLoading] = useState(false);

  const resolve = useCallback(async (barcode: string) => {
    if (!barcode.trim()) {
      setPreview(null);
      return;
    }
    setLoading(true);
    try {
      setPreview(await resolveTrackedProductPreview(barcode));
    } catch {
      setPreview({
        resolved: false,
        picnic_id: null,
        picnic_name: null,
        picnic_image_id: null,
        picnic_unit_quantity: null,
        reason: "error",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => setPreview(null), []);

  return { preview, loading, resolve, clear };
}
```

- [ ] **Step 2: Type-check**

Run: `cd recipe-assistant/frontend && npx tsc -b`

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd recipe-assistant/frontend
git add src/hooks/useTrackedProducts.ts
git commit -m "$(cat <<'EOF'
feat(restock): add useTrackedProducts and useResolvePreview hooks

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: TrackedProductForm modal component

**Files:**
- Create: `recipe-assistant/frontend/src/components/tracked/TrackedProductForm.tsx`

- [ ] **Step 1: Create the form component**

Create `recipe-assistant/frontend/src/components/tracked/TrackedProductForm.tsx`:

```typescript
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from "@mui/material";
import { useResolvePreview } from "../../hooks/useTrackedProducts";
import type {
  TrackedProduct,
  TrackedProductCreate,
  TrackedProductUpdate,
} from "../../types";

type Mode = "create" | "edit";

type Props = {
  open: boolean;
  mode: Mode;
  initialBarcode?: string;
  existing?: TrackedProduct;
  onClose: () => void;
  onSubmitCreate: (data: TrackedProductCreate) => Promise<void>;
  onSubmitUpdate: (barcode: string, data: TrackedProductUpdate) => Promise<void>;
};

const DEBOUNCE_MS = 500;

const TrackedProductForm = ({
  open,
  mode,
  initialBarcode = "",
  existing,
  onClose,
  onSubmitCreate,
  onSubmitUpdate,
}: Props) => {
  const [barcode, setBarcode] = useState(initialBarcode);
  const [minQty, setMinQty] = useState<number>(existing?.min_quantity ?? 1);
  const [targetQty, setTargetQty] = useState<number>(
    existing?.target_quantity ?? 4
  );
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { preview, loading: previewLoading, resolve, clear } = useResolvePreview();

  // Reset internal state whenever we reopen the dialog.
  useEffect(() => {
    if (open) {
      setBarcode(existing?.barcode ?? initialBarcode);
      setMinQty(existing?.min_quantity ?? 1);
      setTargetQty(existing?.target_quantity ?? 4);
      setSubmitError(null);
      if (mode === "edit" && existing) {
        // Edit mode: barcode is fixed and Picnic mapping is locked in; skip
        // the preview call and synthesize a resolved state from the row.
        // (The preview state is used only to show the Picnic name/image.)
        clear();
      }
    }
  }, [open, mode, existing, initialBarcode, clear]);

  // Debounced live Picnic resolution on barcode change (create mode only).
  useEffect(() => {
    if (mode !== "create" || !barcode.trim()) {
      clear();
      return;
    }
    const handle = setTimeout(() => {
      resolve(barcode.trim());
    }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [barcode, mode, resolve, clear]);

  const targetInvalid = targetQty <= minQty;
  const canSubmit = useMemo(() => {
    if (submitting) return false;
    if (minQty < 0) return false;
    if (targetQty <= 0 || targetInvalid) return false;
    if (mode === "edit") return true;
    return preview?.resolved === true;
  }, [mode, preview, minQty, targetQty, targetInvalid, submitting]);

  const handleSubmit = async () => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      if (mode === "create") {
        await onSubmitCreate({
          barcode: barcode.trim(),
          min_quantity: minQty,
          target_quantity: targetQty,
        });
      } else if (existing) {
        await onSubmitUpdate(existing.barcode, {
          min_quantity: minQty,
          target_quantity: targetQty,
        });
      }
      onClose();
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Fehler beim Speichern");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        {mode === "create"
          ? "Nachbestellungs-Regel anlegen"
          : "Nachbestellungs-Regel bearbeiten"}
      </DialogTitle>
      <DialogContent>
        <Box display="flex" flexDirection="column" gap={2} mt={1}>
          <TextField
            label="Barcode"
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
            disabled={mode === "edit"}
            fullWidth
          />

          {mode === "create" && (
            <Box>
              {previewLoading && (
                <Box display="flex" alignItems="center" gap={1}>
                  <CircularProgress size={16} />
                  <Typography variant="body2">
                    Picnic-Verfügbarkeit wird geprüft…
                  </Typography>
                </Box>
              )}
              {!previewLoading && preview?.resolved && (
                <Alert severity="success">
                  Gefunden: {preview.picnic_name}
                  {preview.picnic_unit_quantity
                    ? ` (${preview.picnic_unit_quantity})`
                    : ""}
                </Alert>
              )}
              {!previewLoading &&
                preview !== null &&
                preview.resolved === false && (
                  <Alert severity="error">
                    Nicht bei Picnic verfügbar — Regel kann nicht angelegt
                    werden.
                  </Alert>
                )}
            </Box>
          )}

          {mode === "edit" && existing && (
            <Alert severity="info">
              {existing.picnic_name}
              {existing.picnic_unit_quantity
                ? ` (${existing.picnic_unit_quantity})`
                : ""}
            </Alert>
          )}

          <TextField
            label="Mindestmenge (min_quantity)"
            type="number"
            value={minQty}
            onChange={(e) => setMinQty(parseInt(e.target.value, 10) || 0)}
            inputProps={{ min: 0 }}
            fullWidth
          />
          <TextField
            label="Ziel-Menge (target_quantity)"
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

          {submitError && <Alert severity="error">{submitError}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Abbrechen</Button>
        <Button
          variant="contained"
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          Speichern
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default TrackedProductForm;
```

- [ ] **Step 2: Type-check**

Run: `cd recipe-assistant/frontend && npx tsc -b`

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd recipe-assistant/frontend
git add src/components/tracked/TrackedProductForm.tsx
git commit -m "$(cat <<'EOF'
feat(restock): add TrackedProductForm modal with live Picnic preview

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: TrackedProductsPage + route + Navbar entry

**Files:**
- Create: `recipe-assistant/frontend/src/components/tracked/TrackedProductCard.tsx`
- Create: `recipe-assistant/frontend/src/pages/TrackedProductsPage.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`
- Modify: `recipe-assistant/frontend/src/components/Navbar.tsx`

- [ ] **Step 1: Create the card component**

Create `recipe-assistant/frontend/src/components/tracked/TrackedProductCard.tsx`:

```typescript
import {
  Box,
  Chip,
  IconButton,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import type { TrackedProduct } from "../../types";

type Props = {
  item: TrackedProduct;
  onEdit: (item: TrackedProduct) => void;
  onDelete: (item: TrackedProduct) => void;
};

const TrackedProductCard = ({ item, onEdit, onDelete }: Props) => {
  const badgeColor = item.below_threshold ? "error" : "success";

  return (
    <Paper sx={{ p: 2, mb: 1 }}>
      <Stack direction="row" spacing={2} alignItems="center">
        {item.picnic_image_id && (
          <Box
            component="img"
            src={`https://storefront-prod.nl.picnicinternational.com/static/images/${item.picnic_image_id}/medium.png`}
            alt=""
            sx={{ width: 56, height: 56, objectFit: "contain" }}
          />
        )}
        <Box flex={1}>
          <Typography variant="subtitle1">{item.picnic_name}</Typography>
          {item.picnic_unit_quantity && (
            <Typography variant="body2" color="text.secondary">
              {item.picnic_unit_quantity}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary">
            Auffüllen auf {item.target_quantity}
          </Typography>
        </Box>
        <Chip
          label={`${item.current_quantity} / ${item.min_quantity}`}
          color={badgeColor}
          size="small"
        />
        <IconButton onClick={() => onEdit(item)} size="small">
          <EditIcon fontSize="small" />
        </IconButton>
        <IconButton onClick={() => onDelete(item)} size="small">
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Paper>
  );
};

export default TrackedProductCard;
```

- [ ] **Step 2: Create the page**

Create `recipe-assistant/frontend/src/pages/TrackedProductsPage.tsx`:

```typescript
import { useState } from "react";
import { Alert, Box, Button, Container, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import { usePicnicStatus } from "../hooks/usePicnic";
import { useNotification } from "../components/NotificationProvider";
import TrackedProductCard from "../components/tracked/TrackedProductCard";
import TrackedProductForm from "../components/tracked/TrackedProductForm";
import type { TrackedProduct } from "../types";

const TrackedProductsPage = () => {
  const { status: picnicStatus, loading: statusLoading } = usePicnicStatus();
  const { items, loading, error, create, update, remove } = useTrackedProducts();
  const { notify } = useNotification();

  const [formOpen, setFormOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<TrackedProduct | null>(null);

  if (statusLoading) return null;
  if (!picnicStatus?.enabled) {
    return (
      <Container sx={{ mt: 4 }}>
        <Alert severity="info">
          Nachbestellungen benötigen die Picnic-Integration. Bitte zuerst
          Picnic einrichten.
        </Alert>
      </Container>
    );
  }

  const handleCreate = () => {
    setEditingItem(null);
    setFormOpen(true);
  };

  const handleEdit = (item: TrackedProduct) => {
    setEditingItem(item);
    setFormOpen(true);
  };

  const handleDelete = async (item: TrackedProduct) => {
    if (!window.confirm(`Regel für "${item.name}" wirklich entfernen?`)) return;
    try {
      await remove(item.barcode);
      notify("Regel entfernt", "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  return (
    <Container sx={{ mt: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h4">Nachbestellungen</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleCreate}
        >
          Neu
        </Button>
      </Box>

      {loading && <Typography>Lädt…</Typography>}
      {error && !loading && <Alert severity="error">{error}</Alert>}
      {!loading && items.length === 0 && (
        <Typography color="text.secondary">
          Noch keine Nachbestellungs-Regeln angelegt.
        </Typography>
      )}

      {items.map((item) => (
        <TrackedProductCard
          key={item.barcode}
          item={item}
          onEdit={handleEdit}
          onDelete={handleDelete}
        />
      ))}

      <TrackedProductForm
        open={formOpen}
        mode={editingItem ? "edit" : "create"}
        existing={editingItem ?? undefined}
        onClose={() => setFormOpen(false)}
        onSubmitCreate={async (data) => {
          await create(data);
          notify("Regel angelegt", "success");
        }}
        onSubmitUpdate={async (barcode, data) => {
          await update(barcode, data);
          notify("Regel aktualisiert", "success");
        }}
      />
    </Container>
  );
};

export default TrackedProductsPage;
```

- [ ] **Step 3: Add the route**

Modify `recipe-assistant/frontend/src/App.tsx`. Add the import after the existing `ShoppingListPage` import:

```typescript
import ShoppingListPage from "./pages/ShoppingListPage";
import TrackedProductsPage from "./pages/TrackedProductsPage";
```

And add the route after `/shopping-list`:

```typescript
        <Route path="/shopping-list" element={<ShoppingListPage />} />
        <Route path="/tracked-products" element={<TrackedProductsPage />} />
```

- [ ] **Step 4: Add Navbar entry**

Modify `recipe-assistant/frontend/src/components/Navbar.tsx`. Add an import near the other MUI icon imports (around line 22):

```typescript
import AddAlertIcon from "@mui/icons-material/AddAlert";
```

Then extend the existing `status?.enabled` array (lines 44-48). Replace this block:

```typescript
    ...(status?.enabled
      ? [
          { path: "/picnic-import", label: "Picnic-Import", icon: <LocalGroceryStoreIcon /> },
          { path: "/shopping-list", label: "Einkaufsliste", icon: <ShoppingCartIcon /> },
        ]
```

with:

```typescript
    ...(status?.enabled
      ? [
          { path: "/picnic-import", label: "Picnic-Import", icon: <LocalGroceryStoreIcon /> },
          { path: "/shopping-list", label: "Einkaufsliste", icon: <ShoppingCartIcon /> },
          { path: "/tracked-products", label: "Nachbestellungen", icon: <AddAlertIcon /> },
        ]
```

- [ ] **Step 5: Type-check**

Run: `cd recipe-assistant/frontend && npx tsc -b`

Expected: no errors.

- [ ] **Step 6: Build the frontend to catch any runtime issues**

Run: `cd recipe-assistant/frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
cd recipe-assistant/frontend
git add src/pages/TrackedProductsPage.tsx src/components/tracked/TrackedProductCard.tsx src/App.tsx src/components/Navbar.tsx
git commit -m "$(cat <<'EOF'
feat(restock): add Nachbestellungen page and navigation

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Inventory page integration (restock button + zombie display)

**Files:**
- Create: `recipe-assistant/frontend/src/components/tracked/InventoryRestockButton.tsx`
- Modify: `recipe-assistant/frontend/src/pages/InventoryPage.tsx`

- [ ] **Step 1: Create the per-row restock button component**

Create `recipe-assistant/frontend/src/components/tracked/InventoryRestockButton.tsx`:

```typescript
import { Chip, IconButton, Tooltip } from "@mui/material";
import AddAlertIcon from "@mui/icons-material/AddAlert";
import type { TrackedProduct } from "../../types";

type Props = {
  tracked?: TrackedProduct;
  onClick: () => void;
};

const InventoryRestockButton = ({ tracked, onClick }: Props) => {
  if (!tracked) {
    return (
      <Tooltip title="Nachbestellungs-Regel anlegen">
        <IconButton size="small" onClick={onClick}>
          <AddAlertIcon fontSize="small" color="disabled" />
        </IconButton>
      </Tooltip>
    );
  }

  const label = `${tracked.current_quantity} / ${tracked.min_quantity}`;
  const color = tracked.below_threshold ? "error" : "success";

  return (
    <Tooltip
      title={`Nachbestellen bei < ${tracked.min_quantity}, auffüllen auf ${tracked.target_quantity}`}
    >
      <Chip
        label={label}
        color={color}
        size="small"
        onClick={onClick}
        clickable
      />
    </Tooltip>
  );
};

export default InventoryRestockButton;
```

- [ ] **Step 2: Wire the button into InventoryPage**

Modify `recipe-assistant/frontend/src/pages/InventoryPage.tsx`. The file currently has a table with header cells at lines 225-240 (`columns.map(...)` plus three fixed cells: `Lagerort`, `Ablaufdatum`, `Aktionen`) and a body row starting at line 244. The edits:

**1. Add imports** at the top of the file. Replace the existing line 1:

```typescript
import { useEffect, useRef, useState } from "react";
```

with:

```typescript
import { useEffect, useMemo, useRef, useState } from "react";
```

And add after the existing import of `usePicnicStatus` (around line 26):

```typescript
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import InventoryRestockButton from "../components/tracked/InventoryRestockButton";
import TrackedProductForm from "../components/tracked/TrackedProductForm";
import type { TrackedProduct } from "../types";
```

Also add to the MUI icon imports:

```typescript
import Typography from "@mui/material/Typography";
```

(Typography is already in the existing `@mui/material` import — skip if it is.)

**2. Call the hook and build the barcode map.** Inside the `InventoryPage` component, after the existing `const { status: picnicStatus } = usePicnicStatus();` line (around line 35):

```typescript
  const trackedProducts = useTrackedProducts();
  const trackedByBarcode = useMemo(() => {
    const map = new Map<string, TrackedProduct>();
    for (const tp of trackedProducts.items) {
      map.set(tp.barcode, tp);
    }
    return map;
  }, [trackedProducts.items]);

  const [trackedFormOpen, setTrackedFormOpen] = useState(false);
  const [trackedFormBarcode, setTrackedFormBarcode] = useState("");
  const [trackedFormExisting, setTrackedFormExisting] = useState<
    TrackedProduct | undefined
  >(undefined);

  const openTrackedForm = (barcode: string, existing?: TrackedProduct) => {
    setTrackedFormBarcode(barcode);
    setTrackedFormExisting(existing);
    setTrackedFormOpen(true);
  };
```

**3. Add the new header cell.** In the `<TableHead><TableRow>` block, after the existing `<TableCell>Aktionen</TableCell>` (currently line 239), add:

```typescript
              <TableCell>Nachbest.</TableCell>
```

**4. Zombie row styling on the body `<TableRow>`.** The body row at line 244 reads `<TableRow key={item.id}>`. Replace it with:

```typescript
              <TableRow
                key={item.id}
                sx={{
                  ...(item.quantity === 0 && {
                    backgroundColor: "action.hover",
                  }),
                }}
              >
```

**5. Show the "leer, nachbestellt" marker in the quantity cell.** The quantity cell uses an editable `TextField`. After the closing `</TableCell>` for the category cell OR immediately inside the quantity `<TableCell>` after the `</TextField>`, add a small marker. Concretely, find the quantity `<TableCell>` block (the one containing the `<TextField type="number" ... value={editFields[item.id]?.quantity ?? item.quantity}` around line 254-262) and append — inside the same `<TableCell>` after the `<TextField>` closing tag — this snippet:

```typescript
                  {item.quantity === 0 && trackedByBarcode.has(item.barcode) && (
                    <Typography
                      variant="caption"
                      color="error"
                      display="block"
                      sx={{ mt: 0.5 }}
                    >
                      leer, nachbestellt
                    </Typography>
                  )}
```

**6. Add the per-row restock cell.** As the last `<TableCell>` in each body row (after the existing Aktionen cell), add:

```typescript
                <TableCell>
                  <InventoryRestockButton
                    tracked={trackedByBarcode.get(item.barcode)}
                    onClick={() =>
                      openTrackedForm(
                        item.barcode,
                        trackedByBarcode.get(item.barcode)
                      )
                    }
                  />
                </TableCell>
```

**7. Render the form at the end of the component's JSX.** Just before the closing `</Paper>` of the returned JSX tree, add:

```typescript
      <TrackedProductForm
        open={trackedFormOpen}
        mode={trackedFormExisting ? "edit" : "create"}
        initialBarcode={trackedFormBarcode}
        existing={trackedFormExisting}
        onClose={() => setTrackedFormOpen(false)}
        onSubmitCreate={async (data) => {
          await trackedProducts.create(data);
          notify("Nachbestellungs-Regel angelegt", "success");
        }}
        onSubmitUpdate={async (barcode, data) => {
          await trackedProducts.update(barcode, data);
          notify("Nachbestellungs-Regel aktualisiert", "success");
        }}
      />
```

- [ ] **Step 3: Type-check and build**

Run: `cd recipe-assistant/frontend && npx tsc -b && npm run build`

Expected: both succeed.

- [ ] **Step 4: Manual smoke test**

Start the backend (`cd recipe-assistant/backend && uvicorn app.main:app --reload`) and the frontend (`cd recipe-assistant/frontend && npm run dev`) — or run the addon container locally — then walk through the spec's manual smoke-test checklist:

1. Create a tracked product for a real inventory item via the Nachbestellungen page: `min=1`, `target=4`. Verify the Picnic preview resolves (green), the rule appears with a green badge.
2. On the Inventory page, verify the item's row shows a colored chip with `current / min`.
3. Scan out the item once. Navigate to the shopping list page (`/shopping-list`) and verify the product is present with `quantity = 4 - (current-1)`.
4. Scan out again. Shopping list quantity is raised, no duplicate entry.
5. Continue to `qty=0`. The Inventory row persists with a "leer, nachbestellt" marker.
6. Push the shopping list to the Picnic cart via the existing sync button. Verify the product appears in the real Picnic account.
7. Scan back in. Row quantity goes from 0 → 1. Shopping list unchanged.
8. Delete the tracked rule via the Nachbestellungen page. Inventory row persists at its current quantity.

- [ ] **Step 5: Commit**

```bash
cd recipe-assistant/frontend
git add src/components/tracked/InventoryRestockButton.tsx src/pages/InventoryPage.tsx
git commit -m "$(cat <<'EOF'
feat(restock): integrate restock button and zombie display on inventory page

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] **Backend test suite**

Run: `cd recipe-assistant/backend && python -m pytest -q`

Expected: all tests pass, including the new `test_restock.py`, `test_inventory_restock.py`, `test_tracked_products_router.py`, and `test_tracked_product_schemas.py`.

- [ ] **Frontend build**

Run: `cd recipe-assistant/frontend && npx tsc -b && npm run build`

Expected: no errors.

- [ ] **Commit log check**

Run: `git log --oneline -20`

Expected: clean sequence of feat(restock) commits, one per task.
