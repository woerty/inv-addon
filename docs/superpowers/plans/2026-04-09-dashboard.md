# Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a household dashboard as the new homepage showing live inventory status (pinned products, orders, low stock, activity feed) and consumption analytics (trend graphs, top consumers, category breakdown, restock costs, storage locations) with per-product detail drill-down.

**Architecture:** Single new backend router (`/api/dashboard/`) with two endpoints — `summary` (all widget data in one call) and `product/{barcode}` (detail drill-down). All analytics computed server-side by aggregating `InventoryLog`. Frontend gets a new `DashboardPage` at `/` with widget components using `recharts` for graphs. Inventory list moves to `/inventory`.

**Tech Stack:** FastAPI, async SQLAlchemy, Pydantic v2 (backend); React 19, TypeScript, MUI 6, recharts (frontend)

---

### Task 1: Database Migration — add `is_pinned` to InventoryItem

**Files:**
- Modify: `recipe-assistant/backend/app/models/inventory.py`
- Create: `recipe-assistant/backend/alembic/versions/009_add_is_pinned.py`

- [ ] **Step 1: Add `is_pinned` column to InventoryItem model**

In `recipe-assistant/backend/app/models/inventory.py`, add after the `image_url` field:

```python
is_pinned: Mapped[bool] = mapped_column(
    sa.Boolean, nullable=False, server_default=sa.text("0")
)
```

Add `import sqlalchemy as sa` if not already present (the file currently uses individual imports from sqlalchemy — add `Boolean` to the existing imports and use `server_default=text("0")`).

Specifically, add to the imports:

```python
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func, text
```

And add the column:

```python
is_pinned: Mapped[bool] = mapped_column(
    Boolean, nullable=False, server_default=text("0")
)
```

- [ ] **Step 2: Create Alembic migration**

Create `recipe-assistant/backend/alembic/versions/009_add_is_pinned.py`:

```python
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory",
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("inventory", "is_pinned")
```

- [ ] **Step 3: Verify migration applies**

Run from `recipe-assistant/backend/`:

```bash
alembic upgrade head
```

Expected: Migration 009 applies successfully.

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/backend/app/models/inventory.py recipe-assistant/backend/alembic/versions/009_add_is_pinned.py
git commit -m "feat(dashboard): add is_pinned column to inventory"
```

---

### Task 2: Backend — Dashboard Schemas

**Files:**
- Create: `recipe-assistant/backend/app/schemas/dashboard.py`

- [ ] **Step 1: Create dashboard Pydantic schemas**

Create `recipe-assistant/backend/app/schemas/dashboard.py`:

```python
from pydantic import BaseModel


class PinnedProduct(BaseModel):
    barcode: str
    name: str
    quantity: int
    min_quantity: int | None
    image_url: str | None

    model_config = {"from_attributes": True}


class LowStockItem(BaseModel):
    barcode: str
    name: str
    quantity: int
    min_quantity: int


class ActivityEntry(BaseModel):
    action: str
    barcode: str
    product_name: str
    details: str | None
    timestamp: str


class TrendSeries(BaseModel):
    category: str
    data: list[int]


class ConsumptionTrend(BaseModel):
    labels: list[str]
    series: list[TrendSeries]


class TopConsumer(BaseModel):
    barcode: str
    name: str
    count: int
    sparkline: list[int]


class CategoryCount(BaseModel):
    category: str
    inventory_count: int
    on_order_count: int


class WeeklyCost(BaseModel):
    week: str
    cents: int


class RestockCosts(BaseModel):
    total_cents: int
    previous_period_cents: int
    weekly: list[WeeklyCost]


class StorageLocationCount(BaseModel):
    name: str
    item_count: int


class DashboardSummary(BaseModel):
    pinned_products: list[PinnedProduct]
    low_stock: list[LowStockItem]
    recent_activity: list[ActivityEntry]
    consumption_trend: ConsumptionTrend
    top_consumers: list[TopConsumer]
    categories: list[CategoryCount]
    restock_costs: RestockCosts
    storage_locations: list[StorageLocationCount]


class ProductHistoryEntry(BaseModel):
    timestamp: str
    quantity_after: int
    action: str


class ProductStats(BaseModel):
    total_consumed: int
    avg_per_week: float
    times_restocked: int
    total_cost_cents: int
    estimated_days_remaining: float | None


class ProductDetailResponse(BaseModel):
    barcode: str
    name: str
    current_quantity: int
    min_quantity: int | None
    history: list[ProductHistoryEntry]
    stats: ProductStats
```

- [ ] **Step 2: Commit**

```bash
git add recipe-assistant/backend/app/schemas/dashboard.py
git commit -m "feat(dashboard): add dashboard Pydantic schemas"
```

---

### Task 3: Backend — Dashboard Service (aggregation logic)

**Files:**
- Create: `recipe-assistant/backend/app/services/dashboard.py`
- Test: `recipe-assistant/backend/tests/test_dashboard_service.py`

- [ ] **Step 1: Write tests for the dashboard service**

Create `recipe-assistant/backend/tests/test_dashboard_service.py`:

```python
import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.models.picnic import PicnicProduct
from app.services.dashboard import (
    get_pinned_products,
    get_low_stock,
    get_recent_activity,
    get_consumption_trend,
    get_top_consumers,
    get_category_counts,
    get_restock_costs,
    get_storage_location_counts,
    get_product_detail,
)


async def _seed_basics(db: AsyncSession):
    """Seed inventory items and logs for testing."""
    loc = StorageLocation(name="Kühlschrank")
    db.add(loc)
    await db.flush()

    milk = InventoryItem(
        barcode="111", name="Milch", quantity=3, category="Milchprodukte",
        storage_location_id=loc.id, is_pinned=True,
    )
    butter = InventoryItem(
        barcode="222", name="Butter", quantity=1, category="Milchprodukte",
        storage_location_id=loc.id, is_pinned=False,
    )
    bread = InventoryItem(
        barcode="333", name="Brot", quantity=5, category="Backwaren",
        is_pinned=True,
    )
    db.add_all([milk, butter, bread])
    await db.flush()

    # Tracked product for butter: min=2, so it's low stock (quantity=1)
    tp = TrackedProduct(
        barcode="222", picnic_id="p222", name="Butter",
        min_quantity=2, target_quantity=4,
    )
    db.add(tp)

    # Picnic product for cost lookup
    pp = PicnicProduct(picnic_id="p222", name="Butter", last_price_cents=199)
    db.add(pp)
    await db.flush()

    now = datetime.utcnow()
    logs = [
        InventoryLog(barcode="111", action="remove", details="quantity: 4 → 3", timestamp=now - timedelta(days=1)),
        InventoryLog(barcode="111", action="remove", details="quantity: 5 → 4", timestamp=now - timedelta(days=3)),
        InventoryLog(barcode="111", action="scan-out", details="quantity: 6 → 5", timestamp=now - timedelta(days=5)),
        InventoryLog(barcode="222", action="remove", details="quantity: 2 → 1", timestamp=now - timedelta(days=2)),
        InventoryLog(barcode="222", action="restock_auto", details="qty→4, cart delta=3", timestamp=now - timedelta(days=10)),
        InventoryLog(barcode="333", action="add", details="quantity: 4 → 5", timestamp=now - timedelta(days=1)),
    ]
    db.add_all(logs)
    await db.commit()
    return {"loc": loc, "milk": milk, "butter": butter, "bread": bread}


@pytest.fixture
async def db(setup_db) -> AsyncSession:
    from tests.conftest import TestingSessionLocal
    async with TestingSessionLocal() as session:
        yield session


async def test_get_pinned_products(db: AsyncSession):
    await _seed_basics(db)
    result = await get_pinned_products(db)
    assert len(result) == 2
    names = {p.name for p in result}
    assert names == {"Milch", "Brot"}


async def test_get_low_stock(db: AsyncSession):
    await _seed_basics(db)
    result = await get_low_stock(db)
    assert len(result) == 1
    assert result[0].barcode == "222"
    assert result[0].quantity == 1
    assert result[0].min_quantity == 2


async def test_get_recent_activity(db: AsyncSession):
    await _seed_basics(db)
    result = await get_recent_activity(db, limit=3)
    assert len(result) == 3
    # Most recent first
    assert result[0].barcode in ("111", "333")


async def test_get_consumption_trend(db: AsyncSession):
    await _seed_basics(db)
    result = await get_consumption_trend(db, days=30)
    assert len(result.labels) > 0
    assert len(result.series) > 0
    # Milchprodukte should have consumption data
    dairy = next((s for s in result.series if s.category == "Milchprodukte"), None)
    assert dairy is not None
    assert sum(dairy.data) >= 4  # 3 milk removes + 1 butter remove


async def test_get_top_consumers(db: AsyncSession):
    await _seed_basics(db)
    result = await get_top_consumers(db, days=30)
    assert len(result) >= 2
    # Milch should be top (3 consumption events)
    assert result[0].barcode == "111"
    assert result[0].count == 3


async def test_get_restock_costs(db: AsyncSession):
    await _seed_basics(db)
    result = await get_restock_costs(db, days=30)
    # 1 restock_auto for butter, delta=3, price=199 cents
    assert result.total_cents == 3 * 199


async def test_get_storage_location_counts(db: AsyncSession):
    await _seed_basics(db)
    result = await get_storage_location_counts(db)
    assert len(result) >= 1
    kuehl = next((s for s in result if s.name == "Kühlschrank"), None)
    assert kuehl is not None
    assert kuehl.item_count == 2  # milk + butter


async def test_get_product_detail(db: AsyncSession):
    await _seed_basics(db)
    result = await get_product_detail(db, barcode="111", days=30)
    assert result.barcode == "111"
    assert result.current_quantity == 3
    assert result.stats.total_consumed == 3
    assert len(result.history) >= 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd recipe-assistant/backend && pytest tests/test_dashboard_service.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.dashboard'`

- [ ] **Step 3: Implement the dashboard service**

Create `recipe-assistant/backend/app/services/dashboard.py`:

```python
import re
from datetime import datetime, timedelta

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.models.picnic import PicnicProduct
from app.schemas.dashboard import (
    PinnedProduct,
    LowStockItem,
    ActivityEntry,
    ConsumptionTrend,
    TrendSeries,
    TopConsumer,
    CategoryCount,
    RestockCosts,
    WeeklyCost,
    StorageLocationCount,
    ProductDetailResponse,
    ProductHistoryEntry,
    ProductStats,
)

CONSUME_ACTIONS = ("remove", "scan-out")


async def get_pinned_products(db: AsyncSession) -> list[PinnedProduct]:
    query = (
        select(
            InventoryItem.barcode,
            InventoryItem.name,
            InventoryItem.quantity,
            InventoryItem.image_url,
            TrackedProduct.min_quantity,
        )
        .outerjoin(TrackedProduct, InventoryItem.barcode == TrackedProduct.barcode)
        .where(InventoryItem.is_pinned == True)  # noqa: E712
        .order_by(InventoryItem.name)
    )
    rows = (await db.execute(query)).all()
    return [
        PinnedProduct(
            barcode=r.barcode,
            name=r.name,
            quantity=r.quantity,
            min_quantity=r.min_quantity,
            image_url=r.image_url,
        )
        for r in rows
    ]


async def get_low_stock(db: AsyncSession) -> list[LowStockItem]:
    query = (
        select(
            InventoryItem.barcode,
            InventoryItem.name,
            InventoryItem.quantity,
            TrackedProduct.min_quantity,
        )
        .join(TrackedProduct, InventoryItem.barcode == TrackedProduct.barcode)
        .where(InventoryItem.quantity < TrackedProduct.min_quantity)
        .order_by(
            (InventoryItem.quantity * 1.0 / TrackedProduct.min_quantity).asc()
        )
    )
    rows = (await db.execute(query)).all()
    return [
        LowStockItem(
            barcode=r.barcode,
            name=r.name,
            quantity=r.quantity,
            min_quantity=r.min_quantity,
        )
        for r in rows
    ]


async def get_recent_activity(
    db: AsyncSession, limit: int = 15
) -> list[ActivityEntry]:
    query = (
        select(
            InventoryLog.action,
            InventoryLog.barcode,
            InventoryLog.details,
            InventoryLog.timestamp,
            InventoryItem.name,
        )
        .outerjoin(InventoryItem, InventoryLog.barcode == InventoryItem.barcode)
        .order_by(InventoryLog.timestamp.desc())
        .limit(limit)
    )
    rows = (await db.execute(query)).all()
    return [
        ActivityEntry(
            action=r.action,
            barcode=r.barcode,
            product_name=r.name or r.barcode,
            details=r.details,
            timestamp=r.timestamp.isoformat(),
        )
        for r in rows
    ]


def _week_label(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"KW{iso.week:02d}"


async def get_consumption_trend(
    db: AsyncSession, days: int = 30
) -> ConsumptionTrend:
    since = datetime.utcnow() - timedelta(days=days)
    query = (
        select(
            InventoryLog.timestamp,
            InventoryItem.category,
        )
        .join(InventoryItem, InventoryLog.barcode == InventoryItem.barcode)
        .where(
            InventoryLog.action.in_(CONSUME_ACTIONS),
            InventoryLog.timestamp >= since,
        )
        .order_by(InventoryLog.timestamp)
    )
    rows = (await db.execute(query)).all()

    # Build week buckets
    week_set: dict[str, int] = {}
    cat_week: dict[str, dict[str, int]] = {}
    for r in rows:
        wk = _week_label(r.timestamp)
        if wk not in week_set:
            week_set[wk] = len(week_set)
        cat_week.setdefault(r.category, {})
        cat_week[r.category][wk] = cat_week[r.category].get(wk, 0) + 1

    labels = sorted(week_set.keys(), key=lambda w: week_set[w])
    series = []
    for cat, weeks in sorted(cat_week.items()):
        data = [weeks.get(wk, 0) for wk in labels]
        series.append(TrendSeries(category=cat, data=data))

    return ConsumptionTrend(labels=labels, series=series)


async def get_top_consumers(
    db: AsyncSession, days: int = 30, limit: int = 10
) -> list[TopConsumer]:
    since = datetime.utcnow() - timedelta(days=days)

    # Total counts
    count_q = (
        select(
            InventoryLog.barcode,
            func.count().label("cnt"),
        )
        .where(
            InventoryLog.action.in_(CONSUME_ACTIONS),
            InventoryLog.timestamp >= since,
        )
        .group_by(InventoryLog.barcode)
        .order_by(func.count().desc())
        .limit(limit)
    )
    count_rows = (await db.execute(count_q)).all()
    if not count_rows:
        return []

    barcodes = [r.barcode for r in count_rows]
    count_map = {r.barcode: r.cnt for r in count_rows}

    # Get names
    name_q = select(InventoryItem.barcode, InventoryItem.name).where(
        InventoryItem.barcode.in_(barcodes)
    )
    name_map = {r.barcode: r.name for r in (await db.execute(name_q)).all()}

    # Sparkline data: split time range into 4 buckets
    bucket_size = max(days // 4, 1)
    now = datetime.utcnow()

    result = []
    for bc in barcodes:
        sparkline = []
        for i in range(4):
            bucket_end = now - timedelta(days=i * bucket_size)
            bucket_start = now - timedelta(days=(i + 1) * bucket_size)
            sq = (
                select(func.count())
                .where(
                    InventoryLog.barcode == bc,
                    InventoryLog.action.in_(CONSUME_ACTIONS),
                    InventoryLog.timestamp >= bucket_start,
                    InventoryLog.timestamp < bucket_end,
                )
            )
            cnt = (await db.execute(sq)).scalar() or 0
            sparkline.append(cnt)
        sparkline.reverse()  # oldest first

        result.append(
            TopConsumer(
                barcode=bc,
                name=name_map.get(bc, bc),
                count=count_map[bc],
                sparkline=sparkline,
            )
        )

    return result


async def get_category_counts(db: AsyncSession) -> list[CategoryCount]:
    query = (
        select(
            InventoryItem.category,
            func.count().label("cnt"),
        )
        .group_by(InventoryItem.category)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(query)).all()
    return [
        CategoryCount(category=r.category, inventory_count=r.cnt, on_order_count=0)
        for r in rows
    ]


def _parse_restock_delta(details: str | None) -> int:
    """Parse cart delta from restock_auto log details like 'qty→4, cart delta=3'."""
    if not details:
        return 1
    m = re.search(r"cart delta=(\d+)", details)
    return int(m.group(1)) if m else 1


async def get_restock_costs(
    db: AsyncSession, days: int = 30
) -> RestockCosts:
    since = datetime.utcnow() - timedelta(days=days)
    previous_since = since - timedelta(days=days)

    # Current period
    query = (
        select(InventoryLog.barcode, InventoryLog.details, InventoryLog.timestamp)
        .where(
            InventoryLog.action == "restock_auto",
            InventoryLog.timestamp >= since,
        )
    )
    rows = (await db.execute(query)).all()

    # Get prices for all barcodes involved
    barcodes = list({r.barcode for r in rows})
    price_map: dict[str, int] = {}
    if barcodes:
        price_q = (
            select(TrackedProduct.barcode, PicnicProduct.last_price_cents)
            .join(PicnicProduct, TrackedProduct.picnic_id == PicnicProduct.picnic_id)
            .where(TrackedProduct.barcode.in_(barcodes))
        )
        for r in (await db.execute(price_q)).all():
            if r.last_price_cents is not None:
                price_map[r.barcode] = r.last_price_cents

    total_cents = 0
    week_costs: dict[str, int] = {}
    for r in rows:
        delta = _parse_restock_delta(r.details)
        cost = delta * price_map.get(r.barcode, 0)
        total_cents += cost
        wk = _week_label(r.timestamp)
        week_costs[wk] = week_costs.get(wk, 0) + cost

    # Previous period
    prev_query = (
        select(InventoryLog.barcode, InventoryLog.details)
        .where(
            InventoryLog.action == "restock_auto",
            InventoryLog.timestamp >= previous_since,
            InventoryLog.timestamp < since,
        )
    )
    prev_rows = (await db.execute(prev_query)).all()
    prev_total = sum(
        _parse_restock_delta(r.details) * price_map.get(r.barcode, 0)
        for r in prev_rows
    )

    weekly = sorted(
        [WeeklyCost(week=wk, cents=c) for wk, c in week_costs.items()],
        key=lambda w: w.week,
    )

    return RestockCosts(
        total_cents=total_cents,
        previous_period_cents=prev_total,
        weekly=weekly,
    )


async def get_storage_location_counts(
    db: AsyncSession,
) -> list[StorageLocationCount]:
    query = (
        select(
            StorageLocation.name,
            func.count(InventoryItem.id).label("cnt"),
        )
        .join(InventoryItem, StorageLocation.id == InventoryItem.storage_location_id)
        .group_by(StorageLocation.name)
        .order_by(func.count(InventoryItem.id).desc())
    )
    rows = (await db.execute(query)).all()
    return [
        StorageLocationCount(name=r.name, item_count=r.cnt)
        for r in rows
    ]


def _parse_quantity_after(details: str | None) -> int | None:
    """Parse the target quantity from details like 'quantity: 5 → 3' or 'qty→4, cart delta=3'."""
    if not details:
        return None
    # "quantity: X → Y"
    m = re.search(r"→\s*(\d+)", details)
    if m:
        return int(m.group(1))
    # "qty→N"
    m = re.search(r"qty→(\d+)", details)
    if m:
        return int(m.group(1))
    return None


async def get_product_detail(
    db: AsyncSession, barcode: str, days: int = 30
) -> ProductDetailResponse:
    since = datetime.utcnow() - timedelta(days=days)

    # Get current item
    item = (
        await db.execute(
            select(InventoryItem).where(InventoryItem.barcode == barcode)
        )
    ).scalar_one_or_none()

    name = item.name if item else barcode
    current_qty = item.quantity if item else 0

    # Get tracked product for min_quantity
    tp = (
        await db.execute(
            select(TrackedProduct.min_quantity).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()

    # Get all logs in range
    logs_q = (
        select(InventoryLog)
        .where(
            InventoryLog.barcode == barcode,
            InventoryLog.timestamp >= since,
        )
        .order_by(InventoryLog.timestamp)
    )
    logs = (await db.execute(logs_q)).scalars().all()

    # Build history: reconstruct quantity at each point
    history = []
    for log in logs:
        qty_after = _parse_quantity_after(log.details)
        if log.details == "removed last item":
            qty_after = 0
        if log.details == "new item":
            qty_after = 1
        if qty_after is not None:
            history.append(
                ProductHistoryEntry(
                    timestamp=log.timestamp.isoformat(),
                    quantity_after=qty_after,
                    action=log.action,
                )
            )

    # Stats
    consumed = sum(1 for log in logs if log.action in CONSUME_ACTIONS)
    restocked = sum(1 for log in logs if log.action == "restock_auto")

    days_in_range = max(days, 1)
    avg_per_week = consumed / days_in_range * 7

    # Cost
    cost_cents = 0
    if restocked > 0:
        price_q = (
            select(PicnicProduct.last_price_cents)
            .join(TrackedProduct, TrackedProduct.picnic_id == PicnicProduct.picnic_id)
            .where(TrackedProduct.barcode == barcode)
        )
        price = (await db.execute(price_q)).scalar_one_or_none()
        if price:
            for log in logs:
                if log.action == "restock_auto":
                    delta = _parse_restock_delta(log.details)
                    cost_cents += delta * price

    # Estimated days remaining
    estimated_days = None
    if avg_per_week > 0 and current_qty > 0:
        estimated_days = round(current_qty / avg_per_week * 7, 1)

    return ProductDetailResponse(
        barcode=barcode,
        name=name,
        current_quantity=current_qty,
        min_quantity=tp,
        history=history,
        stats=ProductStats(
            total_consumed=consumed,
            avg_per_week=round(avg_per_week, 1),
            times_restocked=restocked,
            total_cost_cents=cost_cents,
            estimated_days_remaining=estimated_days,
        ),
    )
```

- [ ] **Step 4: Run tests**

```bash
cd recipe-assistant/backend && pytest tests/test_dashboard_service.py -v
```

Expected: All 8 tests pass. If there are import or fixture issues, fix them before proceeding.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/dashboard.py recipe-assistant/backend/tests/test_dashboard_service.py
git commit -m "feat(dashboard): add dashboard aggregation service with tests"
```

---

### Task 4: Backend — Dashboard Router

**Files:**
- Create: `recipe-assistant/backend/app/routers/dashboard.py`
- Modify: `recipe-assistant/backend/app/main.py`
- Test: `recipe-assistant/backend/tests/test_dashboard_router.py`

- [ ] **Step 1: Write router tests**

Create `recipe-assistant/backend/tests/test_dashboard_router.py`:

```python
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient

from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.models.picnic import PicnicProduct


async def _seed(client: AsyncClient):
    """Seed data via direct DB access."""
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as db:
        loc = StorageLocation(name="Kühlschrank")
        db.add(loc)
        await db.flush()

        milk = InventoryItem(
            barcode="111", name="Milch", quantity=3, category="Milchprodukte",
            storage_location_id=loc.id, is_pinned=True,
        )
        butter = InventoryItem(
            barcode="222", name="Butter", quantity=1, category="Milchprodukte",
            is_pinned=False,
        )
        db.add_all([milk, butter])

        tp = TrackedProduct(
            barcode="222", picnic_id="p222", name="Butter",
            min_quantity=2, target_quantity=4,
        )
        pp = PicnicProduct(picnic_id="p222", name="Butter", last_price_cents=199)
        db.add_all([tp, pp])

        now = datetime.utcnow()
        logs = [
            InventoryLog(barcode="111", action="remove", details="quantity: 4 → 3", timestamp=now - timedelta(hours=2)),
            InventoryLog(barcode="222", action="restock_auto", details="qty→4, cart delta=2", timestamp=now - timedelta(days=3)),
        ]
        db.add_all(logs)
        await db.commit()


async def test_dashboard_summary(client: AsyncClient):
    await _seed(client)
    resp = await client.get("/api/dashboard/summary?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "pinned_products" in data
    assert "low_stock" in data
    assert "recent_activity" in data
    assert "consumption_trend" in data
    assert "top_consumers" in data
    assert "categories" in data
    assert "restock_costs" in data
    assert "storage_locations" in data

    # Pinned products
    assert len(data["pinned_products"]) == 1
    assert data["pinned_products"][0]["name"] == "Milch"

    # Low stock
    assert len(data["low_stock"]) == 1
    assert data["low_stock"][0]["barcode"] == "222"


async def test_dashboard_product_detail(client: AsyncClient):
    await _seed(client)
    resp = await client.get("/api/dashboard/product/111?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode"] == "111"
    assert data["current_quantity"] == 3
    assert data["stats"]["total_consumed"] == 1


async def test_dashboard_product_not_found(client: AsyncClient):
    resp = await client.get("/api/dashboard/product/nonexistent?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_quantity"] == 0


async def test_dashboard_pin_toggle(client: AsyncClient):
    await _seed(client)
    # Pin butter
    resp = await client.patch("/api/dashboard/pin/222")
    assert resp.status_code == 200
    assert resp.json()["is_pinned"] is True

    # Unpin butter
    resp = await client.patch("/api/dashboard/pin/222")
    assert resp.status_code == 200
    assert resp.json()["is_pinned"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd recipe-assistant/backend && pytest tests/test_dashboard_router.py -v
```

Expected: FAIL — import errors / 404s.

- [ ] **Step 3: Create the dashboard router**

Create `recipe-assistant/backend/app/routers/dashboard.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.inventory import InventoryItem
from app.schemas.dashboard import DashboardSummary, ProductDetailResponse
from app.services.dashboard import (
    get_pinned_products,
    get_low_stock,
    get_recent_activity,
    get_consumption_trend,
    get_top_consumers,
    get_category_counts,
    get_restock_costs,
    get_storage_location_counts,
    get_product_detail,
)

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    return DashboardSummary(
        pinned_products=await get_pinned_products(db),
        low_stock=await get_low_stock(db),
        recent_activity=await get_recent_activity(db),
        consumption_trend=await get_consumption_trend(db, days=days),
        top_consumers=await get_top_consumers(db, days=days),
        categories=await get_category_counts(db),
        restock_costs=await get_restock_costs(db, days=days),
        storage_locations=await get_storage_location_counts(db),
    )


@router.get("/product/{barcode}", response_model=ProductDetailResponse)
async def product_detail(
    barcode: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    return await get_product_detail(db, barcode=barcode, days=days)


@router.patch("/pin/{barcode}")
async def toggle_pin(
    barcode: str,
    db: AsyncSession = Depends(get_db),
):
    item = (
        await db.execute(
            select(InventoryItem).where(InventoryItem.barcode == barcode)
        )
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.is_pinned = not item.is_pinned
    await db.commit()
    return {"barcode": barcode, "is_pinned": item.is_pinned}
```

- [ ] **Step 4: Register the router in main.py**

In `recipe-assistant/backend/app/main.py`, add the import:

```python
from app.routers import inventory, storage, assistant, persons, picnic, tracked_products, dashboard
```

And add the router registration after the existing ones:

```python
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
```

- [ ] **Step 5: Run tests**

```bash
cd recipe-assistant/backend && pytest tests/test_dashboard_router.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 6: Run all tests to check for regressions**

```bash
cd recipe-assistant/backend && pytest -v
```

Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add recipe-assistant/backend/app/routers/dashboard.py recipe-assistant/backend/app/main.py recipe-assistant/backend/tests/test_dashboard_router.py
git commit -m "feat(dashboard): add dashboard API endpoints"
```

---

### Task 5: Frontend — Install recharts + Add Types + API Client

**Files:**
- Modify: `recipe-assistant/frontend/package.json` (via npm)
- Modify: `recipe-assistant/frontend/src/types/index.ts`
- Modify: `recipe-assistant/frontend/src/api/client.ts`

- [ ] **Step 1: Install recharts**

```bash
cd recipe-assistant/frontend && npm install --legacy-peer-deps recharts
```

- [ ] **Step 2: Add dashboard TypeScript types**

Append to `recipe-assistant/frontend/src/types/index.ts`:

```typescript
// ── Dashboard ────────────────────────────────────────────────────

export interface PinnedProduct {
  barcode: string;
  name: string;
  quantity: number;
  min_quantity: number | null;
  image_url: string | null;
}

export interface LowStockItem {
  barcode: string;
  name: string;
  quantity: number;
  min_quantity: number;
}

export interface ActivityEntry {
  action: string;
  barcode: string;
  product_name: string;
  details: string | null;
  timestamp: string;
}

export interface TrendSeries {
  category: string;
  data: number[];
}

export interface ConsumptionTrend {
  labels: string[];
  series: TrendSeries[];
}

export interface TopConsumer {
  barcode: string;
  name: string;
  count: number;
  sparkline: number[];
}

export interface CategoryCount {
  category: string;
  inventory_count: number;
  on_order_count: number;
}

export interface WeeklyCost {
  week: string;
  cents: number;
}

export interface RestockCosts {
  total_cents: number;
  previous_period_cents: number;
  weekly: WeeklyCost[];
}

export interface StorageLocationCount {
  name: string;
  item_count: number;
}

export interface DashboardSummary {
  pinned_products: PinnedProduct[];
  low_stock: LowStockItem[];
  recent_activity: ActivityEntry[];
  consumption_trend: ConsumptionTrend;
  top_consumers: TopConsumer[];
  categories: CategoryCount[];
  restock_costs: RestockCosts;
  storage_locations: StorageLocationCount[];
}

export interface ProductHistoryEntry {
  timestamp: string;
  quantity_after: number;
  action: string;
}

export interface ProductStats {
  total_consumed: number;
  avg_per_week: number;
  times_restocked: number;
  total_cost_cents: number;
  estimated_days_remaining: number | null;
}

export interface DashboardProductDetail {
  barcode: string;
  name: string;
  current_quantity: number;
  min_quantity: number | null;
  history: ProductHistoryEntry[];
  stats: ProductStats;
}
```

- [ ] **Step 3: Add dashboard API functions**

Append to `recipe-assistant/frontend/src/api/client.ts`:

Add the import for the new types at the top (extend the existing import):

```typescript
import type {
  // ... existing imports ...
  DashboardSummary,
  DashboardProductDetail,
} from "../types";
```

Then append these functions at the bottom:

```typescript
// Dashboard
export const getDashboardSummary = (days: number = 30) =>
  request<DashboardSummary>(`/dashboard/summary?days=${days}`);

export const getDashboardProductDetail = (barcode: string, days: number = 30) =>
  request<DashboardProductDetail>(`/dashboard/product/${encodeURIComponent(barcode)}?days=${days}`);

export const togglePin = (barcode: string) =>
  request<{ barcode: string; is_pinned: boolean }>(`/dashboard/pin/${encodeURIComponent(barcode)}`, {
    method: "PATCH",
  });
```

- [ ] **Step 4: Verify build**

```bash
cd recipe-assistant/frontend && npm run build
```

Expected: Build succeeds (no type errors).

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/package.json recipe-assistant/frontend/package-lock.json recipe-assistant/frontend/src/types/index.ts recipe-assistant/frontend/src/api/client.ts
git commit -m "feat(dashboard): add recharts, dashboard types and API client"
```

---

### Task 6: Frontend — Dashboard Hooks

**Files:**
- Create: `recipe-assistant/frontend/src/hooks/useDashboard.ts`

- [ ] **Step 1: Create useDashboard hook**

Create `recipe-assistant/frontend/src/hooks/useDashboard.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";
import type { DashboardSummary, DashboardProductDetail } from "../types";
import { getDashboardSummary, getDashboardProductDetail, togglePin as apiTogglePin } from "../api/client";

export function useDashboard(days: number = 30) {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getDashboardSummary(days);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Laden");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetch();
    const handleVisibility = () => {
      if (document.visibilityState === "visible") fetch();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [fetch]);

  const togglePin = async (barcode: string) => {
    await apiTogglePin(barcode);
    await fetch();
  };

  return { data, loading, error, refetch: fetch, togglePin };
}

export function useProductDetail() {
  const [data, setData] = useState<DashboardProductDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async (barcode: string, days: number = 30) => {
    setLoading(true);
    try {
      const result = await getDashboardProductDetail(barcode, days);
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const close = () => setData(null);

  return { data, loading, fetch, close };
}
```

- [ ] **Step 2: Commit**

```bash
git add recipe-assistant/frontend/src/hooks/useDashboard.ts
git commit -m "feat(dashboard): add useDashboard and useProductDetail hooks"
```

---

### Task 7: Frontend — Dashboard Widget Components

**Files:**
- Create: `recipe-assistant/frontend/src/components/dashboard/PinnedProducts.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/PendingOrders.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/LowStockAlerts.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/RecentActivity.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/ConsumptionTrend.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/TopConsumers.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/CategoryBreakdown.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/RestockCostsWidget.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/StorageLocations.tsx`
- Create: `recipe-assistant/frontend/src/components/dashboard/ProductDetail.tsx`

This is the largest task. Each widget is a focused component. Create the directory first:

```bash
mkdir -p recipe-assistant/frontend/src/components/dashboard
```

- [ ] **Step 1: Create PinnedProducts widget**

Create `recipe-assistant/frontend/src/components/dashboard/PinnedProducts.tsx`:

```tsx
import { Box, Paper, Typography } from "@mui/material";
import type { PinnedProduct } from "../../types";

function qtyColor(qty: number, min: number | null): string {
  if (qty === 0) return "error.main";
  if (min !== null && qty < min) return "error.main";
  if (min !== null && qty === min) return "warning.main";
  return "success.main";
}

interface Props {
  products: PinnedProduct[];
}

export default function PinnedProducts({ products }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Gepinnte Produkte
      </Typography>
      {products.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Keine Produkte gepinnt
        </Typography>
      )}
      {products.map((p) => (
        <Box key={p.barcode} sx={{ display: "flex", justifyContent: "space-between", py: 0.5 }}>
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {p.name}
          </Typography>
          <Typography variant="body2" fontWeight={600} color={qtyColor(p.quantity, p.min_quantity)}>
            {p.quantity}
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}
```

- [ ] **Step 2: Create PendingOrders widget**

Create `recipe-assistant/frontend/src/components/dashboard/PendingOrders.tsx`:

```tsx
import { Box, Paper, Typography } from "@mui/material";
import type { PendingOrder, Cart } from "../../types";

interface Props {
  orders: PendingOrder[];
  cart: Cart | null;
}

export default function PendingOrders({ orders, cart }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Laufende Bestellungen
      </Typography>
      {orders.map((o) => (
        <Box key={o.delivery_id} sx={{ bgcolor: "action.hover", borderRadius: 1, p: 1, mb: 1 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between" }}>
            <Typography variant="body2">
              {o.delivery_time
                ? `Lieferung ${new Date(o.delivery_time).toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "short" })}`
                : "Lieferung geplant"}
            </Typography>
            <Typography variant="caption" color={o.status === "COMPLETED" ? "success.main" : "warning.main"}>
              {o.status}
            </Typography>
          </Box>
          <Typography variant="caption" color="text.secondary">
            {o.total_items} Artikel
          </Typography>
        </Box>
      ))}
      {cart && cart.total_items > 0 && (
        <Box sx={{ bgcolor: "action.hover", borderRadius: 1, p: 1 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between" }}>
            <Typography variant="body2">Warenkorb</Typography>
            <Typography variant="caption" color="warning.main">Offen</Typography>
          </Box>
          <Typography variant="caption" color="text.secondary">
            {cart.total_items} Artikel · €{(cart.total_price_cents / 100).toFixed(2)}
          </Typography>
        </Box>
      )}
      {orders.length === 0 && (!cart || cart.total_items === 0) && (
        <Typography variant="body2" color="text.secondary">
          Keine offenen Bestellungen
        </Typography>
      )}
    </Paper>
  );
}
```

- [ ] **Step 3: Create LowStockAlerts widget**

Create `recipe-assistant/frontend/src/components/dashboard/LowStockAlerts.tsx`:

```tsx
import { Box, Paper, Typography } from "@mui/material";
import type { LowStockItem } from "../../types";

interface Props {
  items: LowStockItem[];
}

export default function LowStockAlerts({ items }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Niedrig-Bestand
      </Typography>
      {items.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Alles ausreichend vorrätig
        </Typography>
      )}
      {items.map((item) => (
        <Box key={item.barcode} sx={{ display: "flex", justifyContent: "space-between", py: 0.5 }}>
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {item.name}
          </Typography>
          <Box>
            <Typography component="span" variant="body2" fontWeight={600} color="error.main">
              {item.quantity}
            </Typography>
            <Typography component="span" variant="caption" color="text.secondary">
              {" "}/ min {item.min_quantity}
            </Typography>
          </Box>
        </Box>
      ))}
    </Paper>
  );
}
```

- [ ] **Step 4: Create RecentActivity widget**

Create `recipe-assistant/frontend/src/components/dashboard/RecentActivity.tsx`:

```tsx
import { Box, Paper, Typography } from "@mui/material";
import type { ActivityEntry } from "../../types";

const ACTION_LABELS: Record<string, string> = {
  "add": "hinzugefügt",
  "remove": "entnommen",
  "scan-out": "gescannt (raus)",
  "scan-in": "gescannt (rein)",
  "restock_auto": "auto-nachbestellt",
  "delete": "gelöscht",
  "update": "aktualisiert",
};

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `vor ${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `vor ${hours}h`;
  const days = Math.floor(hours / 24);
  return `vor ${days}d`;
}

interface Props {
  entries: ActivityEntry[];
}

export default function RecentActivity({ entries }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%", overflow: "auto", maxHeight: 300 }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Letzte Aktivität
      </Typography>
      {entries.map((e, i) => (
        <Box key={i} sx={{ display: "flex", justifyContent: "space-between", py: 0.5 }}>
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {e.product_name} {ACTION_LABELS[e.action] ?? e.action}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ ml: 1, whiteSpace: "nowrap" }}>
            {timeAgo(e.timestamp)}
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}
```

- [ ] **Step 5: Create ConsumptionTrend chart**

Create `recipe-assistant/frontend/src/components/dashboard/ConsumptionTrend.tsx`:

```tsx
import { Paper, Typography } from "@mui/material";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { ConsumptionTrend as TrendData } from "../../types";

const COLORS = ["#5c6bc0", "#26a69a", "#ff9800", "#ef5350", "#ab47bc", "#42a5f5"];

interface Props {
  trend: TrendData;
}

export default function ConsumptionTrend({ trend }: Props) {
  const chartData = trend.labels.map((label, i) => {
    const point: Record<string, string | number> = { week: label };
    for (const s of trend.series) {
      point[s.category] = s.data[i] ?? 0;
    }
    return point;
  });

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Verbrauchstrend
      </Typography>
      {chartData.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Keine Daten im Zeitraum</Typography>
      ) : (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis dataKey="week" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            {trend.series.map((s, i) => (
              <Line
                key={s.category}
                type="monotone"
                dataKey={s.category}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
```

- [ ] **Step 6: Create TopConsumers widget**

Create `recipe-assistant/frontend/src/components/dashboard/TopConsumers.tsx`:

```tsx
import { Box, Paper, Typography } from "@mui/material";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import type { TopConsumer } from "../../types";

interface Props {
  consumers: TopConsumer[];
  onSelect: (barcode: string) => void;
}

export default function TopConsumers({ consumers, onSelect }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Top-Verbraucher
      </Typography>
      {consumers.length === 0 && (
        <Typography variant="body2" color="text.secondary">Keine Daten</Typography>
      )}
      {consumers.map((c) => (
        <Box
          key={c.barcode}
          onClick={() => onSelect(c.barcode)}
          sx={{
            display: "flex", alignItems: "center", gap: 1, py: 0.5,
            cursor: "pointer", "&:hover": { bgcolor: "action.hover" }, borderRadius: 1, px: 0.5,
          }}
        >
          <Typography variant="body2" noWrap sx={{ flex: 1 }}>
            {c.name}
          </Typography>
          <Box sx={{ width: 50, height: 20 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={c.sparkline.map((v, i) => ({ v, i }))}>
                <Line type="monotone" dataKey="v" stroke="#5c6bc0" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ width: 32, textAlign: "right" }}>
            {c.count}×
          </Typography>
        </Box>
      ))}
    </Paper>
  );
}
```

- [ ] **Step 7: Create CategoryBreakdown widget**

Create `recipe-assistant/frontend/src/components/dashboard/CategoryBreakdown.tsx`:

```tsx
import { Paper, Typography } from "@mui/material";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { CategoryCount } from "../../types";

interface Props {
  categories: CategoryCount[];
}

export default function CategoryBreakdown({ categories }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Kategorien
      </Typography>
      {categories.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Keine Daten</Typography>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={categories} layout="vertical">
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={100} />
            <Tooltip />
            <Legend />
            <Bar dataKey="inventory_count" name="Bestand" fill="#5c6bc0" stackId="a" />
            <Bar dataKey="on_order_count" name="Bestellt" fill="#26a69a" stackId="a" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
```

- [ ] **Step 8: Create RestockCostsWidget**

Create `recipe-assistant/frontend/src/components/dashboard/RestockCostsWidget.tsx`:

```tsx
import { Box, Paper, Typography } from "@mui/material";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { RestockCosts } from "../../types";

interface Props {
  costs: RestockCosts;
}

export default function RestockCostsWidget({ costs }: Props) {
  const diff = costs.previous_period_cents > 0
    ? Math.round((costs.total_cents - costs.previous_period_cents) / costs.previous_period_cents * 100)
    : 0;

  const chartData = costs.weekly.map((w) => ({ week: w.week, euro: w.cents / 100 }));

  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Restock-Kosten
      </Typography>
      <Box sx={{ textAlign: "center", mb: 1 }}>
        <Typography variant="h5" fontWeight={700}>
          €{(costs.total_cents / 100).toFixed(2)}
        </Typography>
        {diff !== 0 && (
          <Typography variant="caption" color={diff < 0 ? "success.main" : "error.main"}>
            {diff > 0 ? "↑" : "↓"} {Math.abs(diff)}% vs. Vorperiode
          </Typography>
        )}
      </Box>
      {chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={chartData}>
            <XAxis dataKey="week" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v: number) => `€${v.toFixed(2)}`} />
            <Bar dataKey="euro" fill="#5c6bc0" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
```

- [ ] **Step 9: Create StorageLocations widget**

Create `recipe-assistant/frontend/src/components/dashboard/StorageLocations.tsx`:

```tsx
import { Paper, Typography } from "@mui/material";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { StorageLocationCount } from "../../types";

interface Props {
  locations: StorageLocationCount[];
}

export default function StorageLocations({ locations }: Props) {
  return (
    <Paper sx={{ p: 2, height: "100%" }}>
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        Lagerorte
      </Typography>
      {locations.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Keine Lagerorte</Typography>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={locations} layout="vertical">
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
            <Tooltip />
            <Bar dataKey="item_count" name="Artikel" fill="#26a69a" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}
```

- [ ] **Step 10: Create ProductDetail panel**

Create `recipe-assistant/frontend/src/components/dashboard/ProductDetail.tsx`:

```tsx
import { Box, IconButton, Paper, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, Tooltip, ResponsiveContainer } from "recharts";
import type { DashboardProductDetail } from "../../types";

interface Props {
  detail: DashboardProductDetail;
  onClose: () => void;
}

export default function ProductDetail({ detail, onClose }: Props) {
  const chartData = detail.history.map((h) => ({
    time: new Date(h.timestamp).toLocaleDateString("de-DE", { day: "numeric", month: "numeric" }),
    quantity: h.quantity_after,
    isRestock: h.action === "restock_auto" || h.action === "add",
  }));

  return (
    <Paper sx={{ p: 2, gridColumn: "1 / -1" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
        <Box>
          <Typography variant="h6">{detail.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            Aktuell: {detail.current_quantity}
            {" · "}Verbrauch: ~{detail.stats.avg_per_week}×/Woche
            {detail.stats.estimated_days_remaining !== null && (
              <> · Reicht noch ~{detail.stats.estimated_days_remaining} Tage</>
            )}
          </Typography>
        </Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </Box>

      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis dataKey="time" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line type="stepAfter" dataKey="quantity" stroke="#5c6bc0" strokeWidth={2} dot={{ r: 3 }} />
            {detail.min_quantity !== null && (
              <ReferenceLine y={detail.min_quantity} stroke="#f44336" strokeDasharray="6 3" label="min" />
            )}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <Typography variant="body2" color="text.secondary">Keine Verlaufsdaten</Typography>
      )}

      <Box sx={{ display: "flex", gap: 3, mt: 2, pt: 1, borderTop: 1, borderColor: "divider", justifyContent: "center" }}>
        <Box sx={{ textAlign: "center" }}>
          <Typography variant="h6">{detail.stats.total_consumed}</Typography>
          <Typography variant="caption" color="text.secondary">Verbraucht</Typography>
        </Box>
        <Box sx={{ textAlign: "center" }}>
          <Typography variant="h6">{detail.stats.avg_per_week}/W</Typography>
          <Typography variant="caption" color="text.secondary">Ø Rate</Typography>
        </Box>
        <Box sx={{ textAlign: "center" }}>
          <Typography variant="h6">{detail.stats.times_restocked}×</Typography>
          <Typography variant="caption" color="text.secondary">Nachbestellt</Typography>
        </Box>
        <Box sx={{ textAlign: "center" }}>
          <Typography variant="h6">€{(detail.stats.total_cost_cents / 100).toFixed(2)}</Typography>
          <Typography variant="caption" color="text.secondary">Kosten</Typography>
        </Box>
      </Box>
    </Paper>
  );
}
```

- [ ] **Step 11: Verify build**

```bash
cd recipe-assistant/frontend && npm run build
```

Expected: Build succeeds. Fix any type errors before proceeding.

- [ ] **Step 12: Commit**

```bash
git add recipe-assistant/frontend/src/components/dashboard/
git commit -m "feat(dashboard): add all dashboard widget components"
```

---

### Task 8: Frontend — DashboardPage + Routing

**Files:**
- Create: `recipe-assistant/frontend/src/pages/DashboardPage.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`
- Modify: `recipe-assistant/frontend/src/components/Navbar.tsx`

- [ ] **Step 1: Create DashboardPage**

Create `recipe-assistant/frontend/src/pages/DashboardPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Box, ToggleButton, ToggleButtonGroup, Typography, CircularProgress } from "@mui/material";
import { useDashboard, useProductDetail } from "../hooks/useDashboard";
import { usePicnicPendingOrders } from "../hooks/usePicnicOrders";
import { usePicnicStatus } from "../hooks/usePicnic";
import PinnedProducts from "../components/dashboard/PinnedProducts";
import PendingOrders from "../components/dashboard/PendingOrders";
import LowStockAlerts from "../components/dashboard/LowStockAlerts";
import RecentActivity from "../components/dashboard/RecentActivity";
import ConsumptionTrend from "../components/dashboard/ConsumptionTrend";
import TopConsumers from "../components/dashboard/TopConsumers";
import CategoryBreakdown from "../components/dashboard/CategoryBreakdown";
import RestockCostsWidget from "../components/dashboard/RestockCostsWidget";
import StorageLocations from "../components/dashboard/StorageLocations";
import ProductDetail from "../components/dashboard/ProductDetail";

const DashboardPage = () => {
  const [days, setDays] = useState(30);
  const { data, loading } = useDashboard(days);
  const productDetail = useProductDetail();
  const { status: picnicStatus } = usePicnicStatus();
  const { orders } = usePicnicPendingOrders();

  // Fetch cart only if Picnic is enabled
  const [cart, setCart] = useState<import("../types").Cart | null>(null);
  useEffect(() => {
    if (picnicStatus?.enabled) {
      import("../api/client").then(({ getCart }) => getCart().then(setCart).catch(() => {}));
    }
  }, [picnicStatus?.enabled]);

  const handleProductSelect = (barcode: string) => {
    productDetail.fetch(barcode, days);
  };

  if (loading && !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!data) return null;

  return (
    <Box sx={{ p: 2, maxWidth: 1200, mx: "auto" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
        <Typography variant="h5">Dashboard</Typography>
        <ToggleButtonGroup
          value={days}
          exclusive
          onChange={(_, v) => v !== null && setDays(v)}
          size="small"
        >
          <ToggleButton value={7}>7T</ToggleButton>
          <ToggleButton value={30}>30T</ToggleButton>
          <ToggleButton value={90}>90T</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Live Status */}
      <Typography variant="overline" color="text.secondary">Live Status</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2, mb: 3 }}>
        <PinnedProducts products={data.pinned_products} />
        {picnicStatus?.enabled && (
          <PendingOrders orders={orders ?? []} cart={cart} />
        )}
        <LowStockAlerts items={data.low_stock} />
        <RecentActivity entries={data.recent_activity} />
      </Box>

      {/* Analyse */}
      <Typography variant="overline" color="text.secondary">Analyse</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
        <Box sx={{ gridColumn: { md: "1 / -1" } }}>
          <ConsumptionTrend trend={data.consumption_trend} />
        </Box>
        <TopConsumers consumers={data.top_consumers} onSelect={handleProductSelect} />
        <CategoryBreakdown categories={data.categories} />
        <RestockCostsWidget costs={data.restock_costs} />
        <StorageLocations locations={data.storage_locations} />
        {productDetail.data && (
          <ProductDetail detail={productDetail.data} onClose={productDetail.close} />
        )}
      </Box>
    </Box>
  );
};

export default DashboardPage;
```

- [ ] **Step 2: Update App.tsx routing**

In `recipe-assistant/frontend/src/App.tsx`:

Add the import at the top:

```typescript
import DashboardPage from "./pages/DashboardPage";
```

Change the routes — replace the `<Route path="/" element={<InventoryPage />} />` line and add the inventory route:

```tsx
<Route path="/" element={<DashboardPage />} />
<Route path="/inventory" element={<InventoryPage />} />
```

- [ ] **Step 3: Update Navbar**

In `recipe-assistant/frontend/src/components/Navbar.tsx`:

Add the import:

```typescript
import DashboardIcon from "@mui/icons-material/Dashboard";
```

Update `NAV_ITEMS` to put Dashboard first and change Inventar path:

```typescript
const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: <DashboardIcon /> },
  { path: "/inventory", label: "Inventar", icon: <InventoryIcon /> },
  { path: "/scan", label: "Scannen", icon: <QrCodeScannerIcon /> },
  { path: "/scan-station", label: "Scan-Station", icon: <CropFreeIcon /> },
  { path: "/recipes", label: "Rezepte", icon: <RestaurantIcon /> },
  { path: "/chat", label: "Chat", icon: <ChatIcon /> },
  { path: "/persons", label: "Personen", icon: <PeopleIcon /> },
];
```

- [ ] **Step 4: Verify build**

```bash
cd recipe-assistant/frontend && npm run build
```

Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/pages/DashboardPage.tsx recipe-assistant/frontend/src/App.tsx recipe-assistant/frontend/src/components/Navbar.tsx
git commit -m "feat(dashboard): add DashboardPage as new homepage, move inventory to /inventory"
```

---

### Task 9: Update InventoryItemResponse schema for is_pinned

**Files:**
- Modify: `recipe-assistant/backend/app/schemas/inventory.py`

- [ ] **Step 1: Add is_pinned to InventoryItemResponse**

In `recipe-assistant/backend/app/schemas/inventory.py`, add `is_pinned` to `InventoryItemResponse`:

```python
class InventoryItemResponse(BaseModel):
    id: int
    barcode: str
    name: str
    quantity: int
    category: str
    storage_location: StorageLocationResponse | None = None
    expiration_date: date | None = None
    image_url: str | None = None
    is_pinned: bool = False
    added_date: datetime
    updated_date: datetime
    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Run all backend tests**

```bash
cd recipe-assistant/backend && pytest -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/app/schemas/inventory.py
git commit -m "feat(dashboard): expose is_pinned in InventoryItemResponse"
```

---

### Task 10: Integration Test + Version Bump

**Files:**
- Modify: `recipe-assistant/config.json`

- [ ] **Step 1: Run full backend test suite**

```bash
cd recipe-assistant/backend && pytest -v
```

Expected: All tests pass.

- [ ] **Step 2: Run frontend build**

```bash
cd recipe-assistant/frontend && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 3: Bump version in config.json**

Read `recipe-assistant/config.json` and increment the version number (e.g., from "2.23" to "2.24").

- [ ] **Step 4: Commit version bump**

```bash
git add recipe-assistant/config.json
git commit -m "chore: bump version to 2.24"
```
