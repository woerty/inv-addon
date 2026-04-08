# Picnic Store Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fragmented Picnic pages (Store, Shopping List, Import, Tracked Products) with a unified 4-tab Picnic Store. Picnic cart becomes single source of truth. Pending orders tracked throughout the app.

**Architecture:** Thin shell page with 4 tabs (Store, Cart, Orders, Subscriptions). Shared data (cart, pending orders) loaded by shell, passed to tabs. Backend wraps additional python-picnic-api2 methods (categories, remove_product, clear_cart, get_article). Shopping list model and all related code removed.

**Tech Stack:** FastAPI, SQLAlchemy (async), python-picnic-api2, React 19, TypeScript, Material-UI, Vite

**Spec:** `docs/superpowers/specs/2026-04-08-picnic-store-design.md`

---

## Task 1: Extend PicnicClient with new API methods

**Files:**
- Modify: `recipe-assistant/backend/app/services/picnic/client.py`
- Modify: `recipe-assistant/backend/tests/fixtures/picnic/fake_client.py`

- [ ] **Step 1: Add new methods to PicnicClientProtocol**

In `recipe-assistant/backend/app/services/picnic/client.py`, add to the Protocol class (after `get_user` at ~line 25):

```python
class PicnicClientProtocol(Protocol):
    async def search(self, query: str) -> list[dict[str, Any]]: ...
    async def get_article_by_gtin(self, ean: str) -> dict[str, Any] | None: ...
    async def get_deliveries(self) -> list[dict[str, Any]]: ...
    async def get_delivery(self, delivery_id: str) -> dict[str, Any]: ...
    async def get_cart(self) -> dict[str, Any]: ...
    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]: ...
    async def get_user(self) -> dict[str, Any]: ...
    async def remove_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]: ...
    async def clear_cart(self) -> dict[str, Any]: ...
    async def get_categories(self, depth: int = 0) -> list[dict[str, Any]]: ...
    async def get_article(self, article_id: str) -> dict[str, Any]: ...
```

- [ ] **Step 2: Implement new methods on PicnicClient**

Add after `add_product` method (~line 194):

```python
async def remove_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
    return await self._call("remove_product", picnic_id, count=count)

async def clear_cart(self) -> dict[str, Any]:
    return await self._call("clear_cart")

async def get_categories(self, depth: int = 0) -> list[dict[str, Any]]:
    return await self._call("get_categories", depth=depth)

async def get_article(self, article_id: str) -> dict[str, Any]:
    return await self._call("get_article", article_id)
```

- [ ] **Step 3: Update FakePicnicClient**

In `recipe-assistant/backend/tests/fixtures/picnic/fake_client.py`, add to constructor:

```python
self.removed_products: list[tuple[str, int]] = []
self.categories: list[dict[str, Any]] = []
self.articles: dict[str, dict[str, Any]] = {}
```

Add methods:

```python
async def remove_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
    self.removed_products.append((picnic_id, count))
    current = self.cart_items.get(picnic_id, 0)
    new_qty = max(0, current - count)
    if new_qty == 0:
        self.cart_items.pop(picnic_id, None)
    else:
        self.cart_items[picnic_id] = new_qty
    return {"ok": True}

async def clear_cart(self) -> dict[str, Any]:
    self.cart_items.clear()
    return {"ok": True}

async def get_categories(self, depth: int = 0) -> list[dict[str, Any]]:
    return self.categories

async def get_article(self, article_id: str) -> dict[str, Any]:
    if article_id in self.articles:
        return self.articles[article_id]
    raise Exception(f"Article {article_id} not found")
```

- [ ] **Step 4: Verify fake client still conforms to protocol**

Run: `python -c "from tests.fixtures.picnic.fake_client import FakePicnicClient; print('OK')"`
from `recipe-assistant/backend/`.

Expected: `OK` (the static conformance check at bottom of fake_client.py catches mismatches)

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/picnic/client.py recipe-assistant/backend/tests/fixtures/picnic/fake_client.py
git commit -m "feat(picnic): extend client with remove_product, clear_cart, get_categories, get_article"
```

---

## Task 2: Add new backend schemas for cart, categories, orders, and product detail

**Files:**
- Modify: `recipe-assistant/backend/app/schemas/picnic.py`

- [ ] **Step 1: Add cart schemas**

Add after the `CartSyncResponse` class (~line 133) in `recipe-assistant/backend/app/schemas/picnic.py`:

```python
# ── Cart (Picnic as source of truth) ──────────────────────────────

class CartItemResponse(BaseModel):
    picnic_id: str
    name: str
    quantity: int
    unit_quantity: str | None = None
    image_id: str | None = None
    price_cents: int | None = None
    total_price_cents: int | None = None


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    total_items: int
    total_price_cents: int


class CartModifyRequest(BaseModel):
    picnic_id: str
    count: int = 1
```

- [ ] **Step 2: Add pending orders schemas**

```python
# ── Pending Orders ────────────────────────────────────────────────

class PendingOrderItem(BaseModel):
    picnic_id: str
    name: str
    quantity: int
    image_id: str | None = None
    price_cents: int | None = None


class PendingOrder(BaseModel):
    delivery_id: str
    status: str
    delivery_time: datetime | None = None
    total_items: int
    items: list[PendingOrderItem]


class PendingOrdersResponse(BaseModel):
    orders: list[PendingOrder]
    quantity_map: dict[str, int]
```

- [ ] **Step 3: Add product detail schema**

```python
# ── Product Detail ────────────────────────────────────────────────

class ProductDetailResponse(BaseModel):
    picnic_id: str
    name: str
    unit_quantity: str | None = None
    image_id: str | None = None
    price_cents: int | None = None
    description: str | None = None
    in_cart: int = 0
    on_order: int = 0
    inventory_quantity: int = 0
    is_subscribed: bool = False
```

- [ ] **Step 4: Add categories schema**

```python
# ── Categories ────────────────────────────────────────────────────

class CategoryItem(BaseModel):
    picnic_id: str
    name: str
    unit_quantity: str | None = None
    image_id: str | None = None
    price_cents: int | None = None


class SubCategory(BaseModel):
    id: str
    name: str
    image_id: str | None = None
    items: list[CategoryItem] = []


class Category(BaseModel):
    id: str
    name: str
    image_id: str | None = None
    children: list[SubCategory] = []


class CategoriesResponse(BaseModel):
    categories: list[Category]
```

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/schemas/picnic.py
git commit -m "feat(picnic): add schemas for cart, pending orders, product detail, categories"
```

---

## Task 3: Add backend cart and pending orders service

**Files:**
- Create: `recipe-assistant/backend/app/services/picnic/orders.py`
- Modify: `recipe-assistant/backend/app/services/picnic/cart.py`

- [ ] **Step 1: Write tests for pending orders service**

Create `recipe-assistant/backend/tests/services/picnic/test_orders.py`:

```python
from __future__ import annotations

from tests.fixtures.picnic.fake_client import FakePicnicClient
from app.services.picnic.orders import parse_pending_orders


def _make_delivery(delivery_id: str, status: str, items: list[dict]) -> dict:
    return {
        "id": delivery_id,
        "status": status,
        "delivery_time": {"start": "2026-04-10T14:00:00+02:00"},
        "orders": [{"items": [{"items": items}]}],
    }


def _make_item(picnic_id: str, name: str, qty: int) -> dict:
    return {
        "id": picnic_id,
        "name": name,
        "unit_quantity": "1 stuk",
        "image_id": "img1",
        "display_price": 199,
        "decorators": [{"type": "QUANTITY", "quantity": qty}],
    }


async def test_parse_pending_orders_filters_completed():
    deliveries = [
        {"id": "d1", "status": "CURRENT"},
        {"id": "d2", "status": "COMPLETED"},
        {"id": "d3", "status": "PENDING"},
    ]
    client = FakePicnicClient()
    client.deliveries_summary = deliveries
    client.delivery_details = {
        "d1": _make_delivery("d1", "CURRENT", [_make_item("s100", "Milch", 2)]),
        "d3": _make_delivery("d3", "PENDING", [_make_item("s100", "Milch", 1), _make_item("s200", "Brot", 3)]),
    }
    result = await parse_pending_orders(client)
    assert len(result.orders) == 2
    assert result.quantity_map == {"s100": 3, "s200": 3}


async def test_parse_pending_orders_empty_when_all_completed():
    client = FakePicnicClient()
    client.deliveries_summary = [{"id": "d1", "status": "COMPLETED"}]
    result = await parse_pending_orders(client)
    assert len(result.orders) == 0
    assert result.quantity_map == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/picnic/test_orders.py -v`
Expected: FAIL (module `app.services.picnic.orders` does not exist)

- [ ] **Step 3: Implement pending orders service**

Create `recipe-assistant/backend/app/services/picnic/orders.py`:

```python
from __future__ import annotations

import logging
from collections import defaultdict

from app.schemas.picnic import (
    PendingOrder,
    PendingOrderItem,
    PendingOrdersResponse,
)
from app.services.picnic.client import PicnicClientProtocol
from app.services.picnic.import_flow import _flatten_delivery_items, _parse_delivery_time

log = logging.getLogger(__name__)

_COMPLETED_STATUSES = {"COMPLETED", "CANCELLED"}


async def parse_pending_orders(
    client: PicnicClientProtocol,
) -> PendingOrdersResponse:
    """Fetch all non-completed deliveries and build a quantity map."""
    summaries = await client.get_deliveries()
    pending = [s for s in summaries if s.get("status", "").upper() not in _COMPLETED_STATUSES]

    orders: list[PendingOrder] = []
    quantity_map: dict[str, int] = defaultdict(int)

    for summary in pending:
        delivery_id = summary["id"]
        try:
            detail = await client.get_delivery(delivery_id)
        except Exception:
            log.warning("Failed to fetch delivery %s, skipping", delivery_id)
            continue

        flat_items = _flatten_delivery_items(detail)
        items: list[PendingOrderItem] = []
        for fi in flat_items:
            quantity_map[fi["picnic_id"]] += fi["quantity"]
            items.append(
                PendingOrderItem(
                    picnic_id=fi["picnic_id"],
                    name=fi["name"],
                    quantity=fi["quantity"],
                    image_id=fi.get("image_id"),
                    price_cents=fi.get("price_cents"),
                )
            )

        orders.append(
            PendingOrder(
                delivery_id=delivery_id,
                status=summary.get("status", "UNKNOWN"),
                delivery_time=_parse_delivery_time(detail),
                total_items=sum(i.quantity for i in items),
                items=items,
            )
        )

    return PendingOrdersResponse(orders=orders, quantity_map=dict(quantity_map))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/picnic/test_orders.py -v`
Expected: 2 passed

- [ ] **Step 5: Write tests for new cart parsing**

Add to `recipe-assistant/backend/tests/services/picnic/test_cart.py`:

```python
from app.services.picnic.cart import parse_cart_response


async def test_parse_cart_response_builds_items():
    client = FakePicnicClient()
    client.cart_items = {"s100": 2, "s200": 1}
    result = await parse_cart_response(client)
    assert result.total_items == 3
    assert len(result.items) == 2
    ids = {item.picnic_id for item in result.items}
    assert ids == {"s100", "s200"}


async def test_parse_cart_response_empty():
    client = FakePicnicClient()
    result = await parse_cart_response(client)
    assert result.total_items == 0
    assert result.items == []
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/picnic/test_cart.py::test_parse_cart_response_builds_items -v`
Expected: FAIL (no function `parse_cart_response`)

- [ ] **Step 7: Implement parse_cart_response**

Add to `recipe-assistant/backend/app/services/picnic/cart.py` (keep `_parse_cart_quantities` which is reused):

```python
from app.schemas.picnic import CartItemResponse, CartResponse


async def parse_cart_response(
    client: PicnicClientProtocol,
) -> CartResponse:
    """Fetch cart from Picnic and return structured response."""
    raw = await client.get_cart()
    items: list[CartItemResponse] = []
    total_price = 0

    for line in raw.get("items", []):
        inner = line.get("items", [])
        if inner:
            product = inner[0]
            picnic_id = product.get("id", line.get("id", ""))
            name = product.get("name", line.get("name", "unknown"))
            qty_raw = product.get("decorators", [])
            quantity = 1
            for d in qty_raw:
                if d.get("type") == "QUANTITY":
                    quantity = d.get("quantity", 1)
                    break
            unit_quantity = product.get("unit_quantity")
            image_id = product.get("image_id")
            price_cents = product.get("display_price")
        else:
            picnic_id = line.get("id", "")
            name = line.get("name", "unknown")
            quantity = line.get("quantity", line.get("count", 1))
            unit_quantity = line.get("unit_quantity")
            image_id = line.get("image_id")
            price_cents = line.get("display_price")

        item_total = (price_cents or 0) * quantity
        total_price += item_total
        items.append(
            CartItemResponse(
                picnic_id=picnic_id,
                name=name,
                quantity=quantity,
                unit_quantity=unit_quantity,
                image_id=image_id,
                price_cents=price_cents,
                total_price_cents=item_total,
            )
        )

    return CartResponse(
        items=items,
        total_items=sum(i.quantity for i in items),
        total_price_cents=total_price,
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/picnic/test_cart.py -v`
Expected: All pass (existing + 2 new)

- [ ] **Step 9: Commit**

```bash
git add recipe-assistant/backend/app/services/picnic/orders.py recipe-assistant/backend/app/services/picnic/cart.py recipe-assistant/backend/tests/services/picnic/test_orders.py recipe-assistant/backend/tests/services/picnic/test_cart.py
git commit -m "feat(picnic): add pending orders service and cart response parser"
```

---

## Task 4: Add new router endpoints (cart, categories, product detail, pending orders)

**Files:**
- Modify: `recipe-assistant/backend/app/routers/picnic.py`

- [ ] **Step 1: Write endpoint tests**

Add to `recipe-assistant/backend/tests/test_picnic_router.py`:

```python
async def test_get_cart(client, override_picnic_client):
    fake = override_picnic_client
    fake.cart_items = {"s100": 2}
    resp = await client.get("/api/picnic/cart")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2
    assert len(data["items"]) == 1
    assert data["items"][0]["picnic_id"] == "s100"


async def test_cart_add(client, override_picnic_client):
    resp = await client.post("/api/picnic/cart/add", json={"picnic_id": "s100", "count": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 3


async def test_cart_remove(client, override_picnic_client):
    fake = override_picnic_client
    fake.cart_items = {"s100": 5}
    resp = await client.post("/api/picnic/cart/remove", json={"picnic_id": "s100", "count": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 3


async def test_cart_clear(client, override_picnic_client):
    fake = override_picnic_client
    fake.cart_items = {"s100": 5, "s200": 2}
    resp = await client.post("/api/picnic/cart/clear")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 0


async def test_get_pending_orders(client, override_picnic_client):
    resp = await client.get("/api/picnic/orders/pending")
    assert resp.status_code == 200
    data = resp.json()
    assert "orders" in data
    assert "quantity_map" in data


async def test_get_categories(client, override_picnic_client):
    fake = override_picnic_client
    fake.categories = [{"id": "cat1", "name": "Obst", "items": []}]
    resp = await client.get("/api/picnic/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_picnic_router.py::test_get_cart -v`
Expected: FAIL (404)

- [ ] **Step 3: Add imports to router**

At top of `recipe-assistant/backend/app/routers/picnic.py`, update imports:

```python
from app.schemas.picnic import (
    CartModifyRequest,
    CartResponse,
    CartSyncResponse,
    CategoriesResponse,
    Category,
    CategoryItem,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportFetchResponse,
    PendingOrdersResponse,
    PicnicLoginSendCodeRequest,
    PicnicLoginSendCodeResponse,
    PicnicLoginStartResponse,
    PicnicLoginVerifyRequest,
    PicnicLoginVerifyResponse,
    PicnicProductCacheEntry,
    PicnicSearchResponse,
    PicnicSearchResult,
    PicnicStatusResponse,
    ProductDetailResponse,
    ShoppingListAddRequest,
    ShoppingListItemResponse,
    ShoppingListUpdateRequest,
    SubCategory,
)
from app.services.picnic.cart import (
    parse_cart_response,
    resolve_shopping_list_status,
    sync_shopping_list_to_cart,
)
from app.services.picnic.orders import parse_pending_orders
```

- [ ] **Step 4: Add cart endpoints**

Add after the `/shopping-list/sync` endpoint (~line 354):

```python
# ── Cart (Picnic as source of truth) ──────────────────────────────

@router.get("/cart", response_model=CartResponse)
async def get_cart(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    return await parse_cart_response(client)


@router.post("/cart/add", response_model=CartResponse)
async def cart_add(
    body: CartModifyRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    await client.add_product(body.picnic_id, count=body.count)
    return await parse_cart_response(client)


@router.post("/cart/remove", response_model=CartResponse)
async def cart_remove(
    body: CartModifyRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    await client.remove_product(body.picnic_id, count=body.count)
    return await parse_cart_response(client)


@router.post("/cart/clear", response_model=CartResponse)
async def cart_clear(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    await client.clear_cart()
    return await parse_cart_response(client)
```

- [ ] **Step 5: Add pending orders endpoint**

```python
# ── Pending Orders ────────────────────────────────────────────────

@router.get("/orders/pending", response_model=PendingOrdersResponse)
async def get_pending_orders(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    return await parse_pending_orders(client)
```

- [ ] **Step 6: Add categories endpoint**

```python
# ── Categories ────────────────────────────────────────────────────

@router.get("/categories", response_model=CategoriesResponse)
async def get_categories(
    depth: int = 2,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    raw = await client.get_categories(depth=depth)
    categories: list[Category] = []
    for group in raw:
        children: list[SubCategory] = []
        for sub in group.get("items", []):
            if sub.get("type") == "CATEGORY":
                items: list[CategoryItem] = []
                for product in sub.get("items", []):
                    if product.get("type") == "SINGLE_ARTICLE":
                        items.append(
                            CategoryItem(
                                picnic_id=product.get("id", ""),
                                name=product.get("name", ""),
                                unit_quantity=product.get("unit_quantity"),
                                image_id=product.get("image_id"),
                                price_cents=product.get("display_price"),
                            )
                        )
                children.append(
                    SubCategory(
                        id=sub.get("id", ""),
                        name=sub.get("name", ""),
                        image_id=sub.get("image_id"),
                        items=items,
                    )
                )
        categories.append(
            Category(
                id=group.get("id", ""),
                name=group.get("name", ""),
                image_id=group.get("image_id"),
                children=children,
            )
        )
    return CategoriesResponse(categories=categories)
```

- [ ] **Step 7: Add product detail endpoint**

```python
# ── Product Detail ────────────────────────────────────────────────

@router.get("/products/{picnic_id}", response_model=ProductDetailResponse)
async def get_product_detail(
    picnic_id: str,
    db: AsyncSession = Depends(get_db),
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    from app.models.inventory import InventoryItem
    from app.models.tracked_product import TrackedProduct

    try:
        article = await client.get_article(picnic_id)
    except Exception:
        article = {}

    # Check cart quantity
    cart_quantities = {}
    try:
        raw_cart = await client.get_cart()
        from app.services.picnic.cart import _parse_cart_quantities
        cart_quantities = _parse_cart_quantities(raw_cart)
    except Exception:
        pass

    # Check pending order quantity
    on_order = 0
    try:
        pending = await parse_pending_orders(client)
        on_order = pending.quantity_map.get(picnic_id, 0)
    except Exception:
        pass

    # Check inventory via EAN match
    inventory_quantity = 0
    cached = await get_product(db, picnic_id)
    if cached and cached.ean:
        result = await db.execute(
            select(InventoryItem.quantity).where(InventoryItem.barcode == cached.ean)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            inventory_quantity = row

    # Check subscription
    is_subscribed = False
    tp_result = await db.execute(
        select(TrackedProduct).where(TrackedProduct.picnic_id == picnic_id)
    )
    is_subscribed = tp_result.scalar_one_or_none() is not None

    # Cache the article
    name = article.get("name", cached.name if cached else "Unknown")
    unit_quantity = article.get("unit_quantity", cached.unit_quantity if cached else None)
    image_id = article.get("image_id", cached.image_id if cached else None)
    price_cents = article.get("display_price", cached.last_price_cents if cached else None)

    return ProductDetailResponse(
        picnic_id=picnic_id,
        name=name,
        unit_quantity=unit_quantity,
        image_id=image_id,
        price_cents=price_cents,
        description=article.get("description"),
        in_cart=cart_quantities.get(picnic_id, 0),
        on_order=on_order,
        inventory_quantity=inventory_quantity,
        is_subscribed=is_subscribed,
    )
```

Also add import at top:
```python
from app.services.picnic.catalog import PicnicProductData, get_product, upsert_product
```
(Change the existing `from app.services.picnic.catalog import PicnicProductData, upsert_product` to include `get_product`.)

- [ ] **Step 8: Run all endpoint tests**

Run: `cd recipe-assistant/backend && python -m pytest tests/test_picnic_router.py -v`
Expected: All pass

- [ ] **Step 9: Commit**

```bash
git add recipe-assistant/backend/app/routers/picnic.py recipe-assistant/backend/tests/test_picnic_router.py
git commit -m "feat(picnic): add cart, categories, product detail, pending orders endpoints"
```

---

## Task 5: Modify restock service to add directly to Picnic cart

**Files:**
- Modify: `recipe-assistant/backend/app/services/restock.py`
- Modify: `recipe-assistant/backend/tests/services/test_restock.py`

- [ ] **Step 1: Update restock tests for new behavior**

In `recipe-assistant/backend/tests/services/test_restock.py`, the restock service currently creates ShoppingListItem rows. We need to change it to call `client.add_product()` instead. Update imports and the test that checks below-threshold behavior.

First, update the test fixture setup. Add a `fake_picnic` fixture and modify existing tests:

```python
import pytest
from tests.fixtures.picnic.fake_client import FakePicnicClient
from app.services.picnic.client import get_picnic_client


@pytest.fixture
def fake_picnic(app):
    """Provide a FakePicnicClient and override the FastAPI dependency."""
    fake = FakePicnicClient()
    from app.main import app as fastapi_app
    fastapi_app.dependency_overrides[get_picnic_client] = lambda: fake
    yield fake
    fastapi_app.dependency_overrides.pop(get_picnic_client, None)
```

Replace `test_below_threshold_creates_shopping_list_entry`:

```python
async def test_below_threshold_adds_to_picnic_cart(session, fake_picnic):
    tracked = TrackedProduct(barcode="123", picnic_id="s100", name="Milch",
                             min_quantity=2, target_quantity=5)
    session.add(tracked)
    await session.flush()

    result = await check_and_enqueue(session, "123", new_quantity=1, picnic_client=fake_picnic)
    assert result is not None
    assert result.added_quantity == 4  # target(5) - current(1)
    assert ("s100", 4) in fake_picnic.added_products
```

Replace `test_below_threshold_with_zero_quantity_fills_to_target`:

```python
async def test_below_threshold_with_zero_fills_to_target(session, fake_picnic):
    tracked = TrackedProduct(barcode="123", picnic_id="s100", name="Milch",
                             min_quantity=2, target_quantity=5)
    session.add(tracked)
    await session.flush()

    result = await check_and_enqueue(session, "123", new_quantity=0, picnic_client=fake_picnic)
    assert result is not None
    assert result.added_quantity == 5
    assert ("s100", 5) in fake_picnic.added_products
```

Add test for pending order deduction:

```python
async def test_below_threshold_deducts_pending_orders(session, fake_picnic):
    tracked = TrackedProduct(barcode="123", picnic_id="s100", name="Milch",
                             min_quantity=2, target_quantity=5)
    session.add(tracked)
    await session.flush()

    # Simulate 3 already on order
    fake_picnic.cart_items = {"s100": 1}  # 1 in cart already

    result = await check_and_enqueue(session, "123", new_quantity=0, picnic_client=fake_picnic)
    assert result is not None
    # need 5, already 1 in cart → add 4
    assert result.added_quantity == 4
```

Add test for skipping when enough in cart + on order:

```python
async def test_below_threshold_skips_if_enough_in_cart(session, fake_picnic):
    tracked = TrackedProduct(barcode="123", picnic_id="s100", name="Milch",
                             min_quantity=2, target_quantity=5)
    session.add(tracked)
    await session.flush()

    fake_picnic.cart_items = {"s100": 5}  # already 5 in cart
    result = await check_and_enqueue(session, "123", new_quantity=0, picnic_client=fake_picnic)
    assert result is None  # nothing to do
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/test_restock.py -v`
Expected: FAIL

- [ ] **Step 3: Rewrite restock service**

In `recipe-assistant/backend/app/services/restock.py`, update to use Picnic cart directly:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem, InventoryLog
from app.models.tracked_product import TrackedProduct
from app.services.picnic.cart import _parse_cart_quantities
from app.services.picnic.client import PicnicClientProtocol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RestockResult:
    barcode: str
    added_quantity: int


async def check_and_enqueue(
    db: AsyncSession,
    barcode: str,
    new_quantity: int,
    *,
    tracked: TrackedProduct | None = None,
    picnic_client: PicnicClientProtocol | None = None,
) -> RestockResult | None:
    """Auto-restock: add to Picnic cart if inventory falls below threshold.

    Checks current cart to avoid duplicates. Adds only the delta needed.
    """
    if tracked is None:
        result = await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
        tracked = result.scalar_one_or_none()

    if tracked is None:
        return None

    if new_quantity >= tracked.min_quantity:
        return None

    if not tracked.picnic_id or picnic_client is None:
        log.warning("Cannot restock %s: no picnic_id or no client", barcode)
        return None

    needed = tracked.target_quantity - new_quantity
    if needed <= 0:
        return None

    # Check what's already in cart
    already_in_cart = 0
    try:
        raw_cart = await picnic_client.get_cart()
        cart_quantities = _parse_cart_quantities(raw_cart)
        already_in_cart = cart_quantities.get(tracked.picnic_id, 0)
    except Exception:
        log.warning("Failed to fetch cart for restock dedup, proceeding anyway")

    delta = needed - already_in_cart
    if delta <= 0:
        log.info("Restock skip %s: need %d, already %d in cart", barcode, needed, already_in_cart)
        return None

    try:
        await picnic_client.add_product(tracked.picnic_id, count=delta)
    except Exception:
        log.exception("Failed to add %s to Picnic cart", tracked.picnic_id)
        return None

    # Log the action
    db.add(InventoryLog(
        inventory_item_id=(await db.execute(
            select(InventoryItem.id).where(InventoryItem.barcode == barcode)
        )).scalar_one_or_none(),
        action="restock_auto",
        quantity_change=delta,
    ))

    log.info("Restock %s: added %d to Picnic cart (was %d in cart, need %d)",
             barcode, delta, already_in_cart, needed)
    return RestockResult(barcode=barcode, added_quantity=delta)
```

- [ ] **Step 4: Update callers of check_and_enqueue to pass picnic_client**

Search for all callers of `check_and_enqueue` and add the `picnic_client` parameter. These are in the inventory router — add `picnic_client: PicnicClientProtocol = Depends(get_picnic_client)` to relevant endpoint signatures and pass it through.

- [ ] **Step 5: Run tests**

Run: `cd recipe-assistant/backend && python -m pytest tests/services/test_restock.py -v`
Expected: All pass

- [ ] **Step 6: Run full test suite**

Run: `cd recipe-assistant/backend && python -m pytest -v`
Expected: All pass (some old shopping-list-dependent tests may need updating — fix as needed)

- [ ] **Step 7: Commit**

```bash
git add recipe-assistant/backend/app/services/restock.py recipe-assistant/backend/tests/services/test_restock.py
git commit -m "feat(restock): add directly to Picnic cart instead of shopping list"
```

---

## Task 6: Remove shopping list (backend)

**Files:**
- Modify: `recipe-assistant/backend/app/routers/picnic.py` (remove shopping list endpoints)
- Modify: `recipe-assistant/backend/app/models/picnic.py` (remove ShoppingListItem)
- Modify: `recipe-assistant/backend/app/schemas/picnic.py` (remove shopping list schemas)
- Modify: `recipe-assistant/backend/app/services/picnic/cart.py` (remove shopping list functions)
- Modify: `recipe-assistant/backend/tests/test_picnic_router.py` (remove shopping list test)
- Modify: `recipe-assistant/backend/tests/services/picnic/test_cart.py` (remove shopping list tests)
- Create: `recipe-assistant/backend/alembic/versions/xxxx_drop_shopping_list.py`

- [ ] **Step 1: Remove ShoppingListItem model**

In `recipe-assistant/backend/app/models/picnic.py`, delete the `ShoppingListItem` class (lines 46-57).

- [ ] **Step 2: Remove shopping list schemas**

In `recipe-assistant/backend/app/schemas/picnic.py`, delete:
- `ShoppingListItemResponse` (lines 97-107)
- `ShoppingListAddRequest` (lines 110-114)
- `ShoppingListUpdateRequest` (lines 117-119)
- `CartSyncItemResult` (lines 122-126)
- `CartSyncResponse` (lines 129-133)

- [ ] **Step 3: Remove shopping list service functions**

In `recipe-assistant/backend/app/services/picnic/cart.py`, delete:
- `Resolution` dataclass
- `_resolve()` function
- `resolve_shopping_list_status()` function
- `sync_shopping_list_to_cart()` function

Keep: `_parse_cart_quantities()` (used by restock and parse_cart_response) and `parse_cart_response()`.

- [ ] **Step 4: Remove shopping list router endpoints**

In `recipe-assistant/backend/app/routers/picnic.py`, delete:
- `GET /shopping-list` endpoint
- `POST /shopping-list` endpoint
- `PATCH /shopping-list/{item_id}` endpoint
- `DELETE /shopping-list/{item_id}` endpoint
- `POST /shopping-list/sync` endpoint

Remove unused imports: `ShoppingListItem`, `ShoppingListAddRequest`, `ShoppingListItemResponse`, `ShoppingListUpdateRequest`, `CartSyncResponse`, `resolve_shopping_list_status`, `sync_shopping_list_to_cart`.

- [ ] **Step 5: Remove shopping list tests**

In `tests/test_picnic_router.py`, delete `test_shopping_list_crud_and_sync`.

In `tests/services/picnic/test_cart.py`, delete all tests that use `ShoppingListItem`:
- `test_resolve_status_mapped_via_explicit_picnic_id`
- `test_resolve_status_hits_cached_ean_pairing`
- `test_resolve_status_uses_live_gtin_lookup_and_caches`
- `test_resolve_status_unavailable_when_gtin_lookup_misses`
- `test_sync_adds_mapped_items_to_cart`
- `test_sync_deduplicates_against_cart`
- `test_sync_skips_item_fully_in_cart`
- `test_sync_idempotent_on_double_click`
- `test_sync_reports_failures_per_item`

Also remove `ShoppingListItem` import from test files.

- [ ] **Step 6: Run full test suite**

Run: `cd recipe-assistant/backend && python -m pytest -v`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add -A recipe-assistant/backend/
git commit -m "refactor(picnic): remove shopping list model, endpoints, and service"
```

---

## Task 7: Add frontend TypeScript types and API client functions

**Files:**
- Modify: `recipe-assistant/frontend/src/types/index.ts`
- Modify: `recipe-assistant/frontend/src/api/client.ts`

- [ ] **Step 1: Add new types**

In `recipe-assistant/frontend/src/types/index.ts`, add after the existing Picnic types:

```typescript
// ── Cart (Picnic as source of truth) ──────────────────────────────

export interface CartItem {
  picnic_id: string;
  name: string;
  quantity: number;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
  total_price_cents: number | null;
}

export interface Cart {
  items: CartItem[];
  total_items: number;
  total_price_cents: number;
}

// ── Pending Orders ────────────────────────────────────────────────

export interface PendingOrderItem {
  picnic_id: string;
  name: string;
  quantity: number;
  image_id: string | null;
  price_cents: number | null;
}

export interface PendingOrder {
  delivery_id: string;
  status: string;
  delivery_time: string | null;
  total_items: number;
  items: PendingOrderItem[];
}

export interface PendingOrdersResponse {
  orders: PendingOrder[];
  quantity_map: Record<string, number>;
}

// ── Product Detail ────────────────────────────────────────────────

export interface ProductDetail {
  picnic_id: string;
  name: string;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
  description: string | null;
  in_cart: number;
  on_order: number;
  inventory_quantity: number;
  is_subscribed: boolean;
}

// ── Categories ────────────────────────────────────────────────────

export interface CategoryItem {
  picnic_id: string;
  name: string;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
}

export interface SubCategory {
  id: string;
  name: string;
  image_id: string | null;
  items: CategoryItem[];
}

export interface PicnicCategory {
  id: string;
  name: string;
  image_id: string | null;
  children: SubCategory[];
}
```

- [ ] **Step 2: Remove old shopping list types**

Delete from `types/index.ts`:
- `ShoppingListItem` interface
- `CartSyncItemResult` interface
- `CartSyncResponse` interface

- [ ] **Step 3: Add new API client functions**

In `recipe-assistant/frontend/src/api/client.ts`, add:

```typescript
// ── Cart ──────────────────────────────────────────────────────────

export const getCart = () =>
  request<Cart>("/picnic/cart");

export const cartAdd = (picnic_id: string, count: number = 1) =>
  request<Cart>("/picnic/cart/add", {
    method: "POST",
    body: JSON.stringify({ picnic_id, count }),
  });

export const cartRemove = (picnic_id: string, count: number = 1) =>
  request<Cart>("/picnic/cart/remove", {
    method: "POST",
    body: JSON.stringify({ picnic_id, count }),
  });

export const cartClear = () =>
  request<Cart>("/picnic/cart/clear", { method: "POST" });

// ── Pending Orders ────────────────────────────────────────────────

export const getPendingOrders = () =>
  request<PendingOrdersResponse>("/picnic/orders/pending");

// ── Product Detail ────────────────────────────────────────────────

export const getProductDetail = (picnicId: string) =>
  request<ProductDetail>(`/picnic/products/${encodeURIComponent(picnicId)}`);

// ── Categories ────────────────────────────────────────────────────

export const getCategories = (depth: number = 2) =>
  request<{ categories: PicnicCategory[] }>(`/picnic/categories?depth=${depth}`);
```

- [ ] **Step 4: Remove old shopping list API functions**

Delete from `client.ts`:
- `getShoppingList`
- `addShoppingListItem`
- `updateShoppingListItem`
- `deleteShoppingListItem`
- `syncShoppingListToCart`

- [ ] **Step 5: Update type imports**

Add new types to the import block in `client.ts`:
```typescript
import type { Cart, PendingOrdersResponse, ProductDetail, PicnicCategory } from "../types";
```

Remove old types: `PicnicShoppingListItem`, `CartSyncResponse` (or whatever alias was used).

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/frontend/src/types/index.ts recipe-assistant/frontend/src/api/client.ts
git commit -m "feat(frontend): add cart, orders, categories, product detail types and API client"
```

---

## Task 8: Add frontend hooks (usePicnicCart, usePicnicPendingOrders, usePicnicCategories, usePicnicProduct)

**Files:**
- Create: `recipe-assistant/frontend/src/hooks/usePicnicCart.ts`
- Create: `recipe-assistant/frontend/src/hooks/usePicnicCategories.ts`
- Create: `recipe-assistant/frontend/src/hooks/usePicnicOrders.ts`
- Create: `recipe-assistant/frontend/src/hooks/usePicnicProduct.ts`
- Modify: `recipe-assistant/frontend/src/hooks/usePicnic.ts` (remove useShoppingList)

- [ ] **Step 1: Create usePicnicCart hook**

Create `recipe-assistant/frontend/src/hooks/usePicnicCart.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";
import { getCart, cartAdd, cartRemove, cartClear } from "../api/client";
import type { Cart } from "../types";

export function usePicnicCart() {
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCart();
      setCart(data);
    } catch {
      setCart(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const add = useCallback(async (picnicId: string, count = 1) => {
    const updated = await cartAdd(picnicId, count);
    setCart(updated);
    return updated;
  }, []);

  const remove = useCallback(async (picnicId: string, count = 1) => {
    const updated = await cartRemove(picnicId, count);
    setCart(updated);
    return updated;
  }, []);

  const clear = useCallback(async () => {
    const updated = await cartClear();
    setCart(updated);
    return updated;
  }, []);

  return { cart, loading, refetch, add, remove, clear };
}
```

- [ ] **Step 2: Create usePicnicCategories hook**

Create `recipe-assistant/frontend/src/hooks/usePicnicCategories.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";
import { getCategories } from "../api/client";
import type { PicnicCategory } from "../types";

export function usePicnicCategories() {
  const [categories, setCategories] = useState<PicnicCategory[]>([]);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCategories();
      setCategories(data.categories);
    } catch {
      setCategories([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { categories, loading, refetch };
}
```

- [ ] **Step 3: Create usePicnicOrders hook**

Create `recipe-assistant/frontend/src/hooks/usePicnicOrders.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";
import { getPendingOrders } from "../api/client";
import type { PendingOrdersResponse } from "../types";

export function usePicnicPendingOrders() {
  const [data, setData] = useState<PendingOrdersResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getPendingOrders();
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const quantityMap = data?.quantity_map ?? {};

  return { orders: data?.orders ?? [], quantityMap, loading, refetch };
}
```

- [ ] **Step 4: Create usePicnicProduct hook**

Create `recipe-assistant/frontend/src/hooks/usePicnicProduct.ts`:

```typescript
import { useCallback, useState } from "react";
import { getProductDetail } from "../api/client";
import type { ProductDetail } from "../types";

export function usePicnicProduct() {
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (picnicId: string) => {
    setLoading(true);
    setProduct(null);
    try {
      const data = await getProductDetail(picnicId);
      setProduct(data);
    } catch {
      setProduct(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => setProduct(null), []);

  return { product, loading, load, clear };
}
```

- [ ] **Step 5: Remove useShoppingList from usePicnic.ts**

In `recipe-assistant/frontend/src/hooks/usePicnic.ts`, delete the entire `useShoppingList` function (lines 142-181) and remove its related imports (`getShoppingList`, `addShoppingListItem`, `updateShoppingListItem`, `deleteShoppingListItem`, `syncShoppingListToCart`).

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/frontend/src/hooks/
git commit -m "feat(frontend): add cart, categories, orders, product detail hooks; remove useShoppingList"
```

---

## Task 9: Build ProductCard and ProductDetailModal components

**Files:**
- Create: `recipe-assistant/frontend/src/components/picnic/store/ProductCard.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/store/ProductDetailModal.tsx`

- [ ] **Step 1: Create ProductCard**

Create `recipe-assistant/frontend/src/components/picnic/store/ProductCard.tsx`:

```tsx
import {
  Card,
  CardActionArea,
  CardContent,
  CardMedia,
  Chip,
  Stack,
  Typography,
} from "@mui/material";
import RepeatIcon from "@mui/icons-material/Repeat";

interface ProductCardProps {
  picnicId: string;
  name: string;
  unitQuantity: string | null;
  imageId: string | null;
  priceCents: number | null;
  inCart: number;
  onOrder: number;
  inInventory: number;
  isSubscribed: boolean;
  onClick: (picnicId: string) => void;
}

const imgUrl = (imageId: string | null, size = "medium") =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/${size}.png`
    : undefined;

const formatPrice = (cents: number | null) =>
  cents != null ? `€${(cents / 100).toFixed(2).replace(".", ",")}` : "";

export default function ProductCard({
  picnicId,
  name,
  unitQuantity,
  imageId,
  priceCents,
  inCart,
  onOrder,
  inInventory,
  isSubscribed,
  onClick,
}: ProductCardProps) {
  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <CardActionArea onClick={() => onClick(picnicId)} sx={{ flex: 1 }}>
        <CardMedia
          component="img"
          height="140"
          image={imgUrl(imageId)}
          alt={name}
          sx={{ objectFit: "contain", p: 1, bgcolor: "#fafafa" }}
        />
        <CardContent sx={{ pb: 1 }}>
          <Typography variant="body2" fontWeight={500} noWrap>
            {name}
          </Typography>
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
            {unitQuantity && (
              <Typography variant="caption" color="text.secondary">
                {unitQuantity}
              </Typography>
            )}
            {priceCents != null && (
              <Typography variant="caption" fontWeight={600}>
                {formatPrice(priceCents)}
              </Typography>
            )}
            {isSubscribed && <RepeatIcon sx={{ fontSize: 14, color: "text.secondary" }} />}
          </Stack>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
            {inCart > 0 && <Chip label={`${inCart} im Warenkorb`} size="small" color="primary" />}
            {onOrder > 0 && <Chip label={`${onOrder} in Bestellung`} size="small" color="warning" />}
            {inInventory > 0 && <Chip label={`${inInventory} im Inventar`} size="small" color="success" />}
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
```

- [ ] **Step 2: Create ProductDetailModal**

Create `recipe-assistant/frontend/src/components/picnic/store/ProductDetailModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import CloseIcon from "@mui/icons-material/Close";
import RepeatIcon from "@mui/icons-material/Repeat";
import { usePicnicProduct } from "../../../hooks/usePicnicProduct";

interface ProductDetailModalProps {
  picnicId: string | null;
  onClose: () => void;
  onCartAdd: (picnicId: string, count: number) => Promise<void>;
  onCartRemove: (picnicId: string, count: number) => Promise<void>;
  onSubscribe: (picnicId: string, name: string) => void;
}

const imgUrl = (imageId: string | null) =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/large.png`
    : undefined;

const formatPrice = (cents: number | null) =>
  cents != null ? `€${(cents / 100).toFixed(2).replace(".", ",")}` : "";

export default function ProductDetailModal({
  picnicId,
  onClose,
  onCartAdd,
  onCartRemove,
  onSubscribe,
}: ProductDetailModalProps) {
  const { product, loading, load, clear } = usePicnicProduct();
  const [addQty, setAddQty] = useState(1);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (picnicId) {
      load(picnicId);
      setAddQty(1);
    } else {
      clear();
    }
  }, [picnicId, load, clear]);

  const handleAdd = async () => {
    if (!product) return;
    setBusy(true);
    try {
      await onCartAdd(product.picnic_id, addQty);
      load(product.picnic_id); // refresh
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async () => {
    if (!product) return;
    setBusy(true);
    try {
      await onCartRemove(product.picnic_id, 1);
      load(product.picnic_id);
    } finally {
      setBusy(false);
    }
  };

  const handleAddOne = async () => {
    if (!product) return;
    setBusy(true);
    try {
      await onCartAdd(product.picnic_id, 1);
      load(product.picnic_id);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={!!picnicId} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        {product?.name ?? "Produkt"}
        <IconButton onClick={onClose} size="small"><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent>
        {loading ? (
          <Box display="flex" justifyContent="center" py={4}>
            <CircularProgress />
          </Box>
        ) : product ? (
          <Stack spacing={2}>
            {product.image_id && (
              <Box display="flex" justifyContent="center" sx={{ bgcolor: "#fafafa", borderRadius: 1, p: 2 }}>
                <img
                  src={imgUrl(product.image_id)}
                  alt={product.name}
                  style={{ maxHeight: 200, objectFit: "contain" }}
                />
              </Box>
            )}

            <Stack direction="row" spacing={1} alignItems="center">
              {product.unit_quantity && (
                <Typography variant="body2" color="text.secondary">{product.unit_quantity}</Typography>
              )}
              {product.price_cents != null && (
                <Typography variant="h6">{formatPrice(product.price_cents)}</Typography>
              )}
            </Stack>

            <Stack direction="row" spacing={1} flexWrap="wrap">
              {product.in_cart > 0 && <Chip label={`${product.in_cart} im Warenkorb`} color="primary" />}
              {product.on_order > 0 && <Chip label={`${product.on_order} in Bestellung`} color="warning" />}
              {product.inventory_quantity > 0 && <Chip label={`${product.inventory_quantity} im Inventar`} color="success" />}
            </Stack>

            {product.description && (
              <Typography variant="body2" color="text.secondary">{product.description}</Typography>
            )}

            {/* Cart controls */}
            {product.in_cart > 0 ? (
              <Stack direction="row" alignItems="center" spacing={1} justifyContent="center">
                <IconButton onClick={handleRemove} disabled={busy} color="primary">
                  <RemoveIcon />
                </IconButton>
                <Typography variant="h6" sx={{ minWidth: 40, textAlign: "center" }}>
                  {product.in_cart}
                </Typography>
                <IconButton onClick={handleAddOne} disabled={busy} color="primary">
                  <AddIcon />
                </IconButton>
              </Stack>
            ) : (
              <Stack direction="row" alignItems="center" spacing={1}>
                <IconButton
                  onClick={() => setAddQty((q) => Math.max(1, q - 1))}
                  disabled={addQty <= 1}
                  size="small"
                >
                  <RemoveIcon />
                </IconButton>
                <Typography sx={{ minWidth: 30, textAlign: "center" }}>{addQty}</Typography>
                <IconButton onClick={() => setAddQty((q) => q + 1)} size="small">
                  <AddIcon />
                </IconButton>
                <Button variant="contained" onClick={handleAdd} disabled={busy} sx={{ flex: 1 }}>
                  In den Warenkorb
                </Button>
              </Stack>
            )}

            {/* Subscribe */}
            {product.is_subscribed ? (
              <Chip icon={<RepeatIcon />} label="Abonniert" color="success" />
            ) : (
              <Button
                variant="outlined"
                startIcon={<RepeatIcon />}
                onClick={() => onSubscribe(product.picnic_id, product.name)}
              >
                Abonnieren
              </Button>
            )}
          </Stack>
        ) : (
          <Typography color="text.secondary">Produkt nicht gefunden</Typography>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/frontend/src/components/picnic/store/
git commit -m "feat(frontend): add ProductCard and ProductDetailModal components"
```

---

## Task 10: Build StoreTab component (categories + search + product grid)

**Files:**
- Create: `recipe-assistant/frontend/src/components/picnic/store/StoreTab.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/store/CategoryChips.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/store/ProductGrid.tsx`

- [ ] **Step 1: Create CategoryChips**

Create `recipe-assistant/frontend/src/components/picnic/store/CategoryChips.tsx`:

```tsx
import { Chip, Stack } from "@mui/material";

interface CategoryChipsProps {
  items: { id: string; name: string }[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}

export default function CategoryChips({ items, selected, onSelect }: CategoryChipsProps) {
  return (
    <Stack direction="row" spacing={1} sx={{ overflowX: "auto", pb: 1 }}>
      {items.map((cat) => (
        <Chip
          key={cat.id}
          label={cat.name}
          variant={selected === cat.id ? "filled" : "outlined"}
          color={selected === cat.id ? "primary" : "default"}
          onClick={() => onSelect(selected === cat.id ? null : cat.id)}
        />
      ))}
    </Stack>
  );
}
```

- [ ] **Step 2: Create ProductGrid**

Create `recipe-assistant/frontend/src/components/picnic/store/ProductGrid.tsx`:

```tsx
import { Grid } from "@mui/material";
import ProductCard from "./ProductCard";

interface ProductGridItem {
  picnic_id: string;
  name: string;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
}

interface ProductGridProps {
  items: ProductGridItem[];
  cartQuantities: Record<string, number>;
  orderQuantities: Record<string, number>;
  inventoryQuantities: Record<string, number>;
  subscribedIds: Set<string>;
  onProductClick: (picnicId: string) => void;
}

export default function ProductGrid({
  items,
  cartQuantities,
  orderQuantities,
  inventoryQuantities,
  subscribedIds,
  onProductClick,
}: ProductGridProps) {
  return (
    <Grid container spacing={2}>
      {items.map((item) => (
        <Grid key={item.picnic_id} size={{ xs: 6, sm: 4, md: 3 }}>
          <ProductCard
            picnicId={item.picnic_id}
            name={item.name}
            unitQuantity={item.unit_quantity}
            imageId={item.image_id}
            priceCents={item.price_cents}
            inCart={cartQuantities[item.picnic_id] ?? 0}
            onOrder={orderQuantities[item.picnic_id] ?? 0}
            inInventory={inventoryQuantities[item.picnic_id] ?? 0}
            isSubscribed={subscribedIds.has(item.picnic_id)}
            onClick={onProductClick}
          />
        </Grid>
      ))}
    </Grid>
  );
}
```

- [ ] **Step 3: Create StoreTab**

Create `recipe-assistant/frontend/src/components/picnic/store/StoreTab.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, CircularProgress, TextField, Typography } from "@mui/material";
import { usePicnicCategories } from "../../../hooks/usePicnicCategories";
import { usePicnicSearch } from "../../../hooks/usePicnic";
import CategoryChips from "./CategoryChips";
import ProductGrid from "./ProductGrid";

const DEBOUNCE_MS = 400;

interface StoreTabProps {
  cartQuantities: Record<string, number>;
  orderQuantities: Record<string, number>;
  inventoryQuantities: Record<string, number>;
  subscribedIds: Set<string>;
  onProductClick: (picnicId: string) => void;
}

export default function StoreTab({
  cartQuantities,
  orderQuantities,
  inventoryQuantities,
  subscribedIds,
  onProductClick,
}: StoreTabProps) {
  const { categories, loading: catLoading } = usePicnicCategories();
  const { results: searchResults, loading: searchLoading, search } = usePicnicSearch();
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSubCategory, setSelectedSubCategory] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const isSearching = query.length >= 2;

  const handleQueryChange = useCallback(
    (value: string) => {
      setQuery(value);
      clearTimeout(timerRef.current);
      if (value.length >= 2) {
        timerRef.current = setTimeout(() => search(value), DEBOUNCE_MS);
      }
    },
    [search],
  );

  // Reset subcategory when category changes
  useEffect(() => {
    setSelectedSubCategory(null);
  }, [selectedCategory]);

  const activeCategory = useMemo(
    () => categories.find((c) => c.id === selectedCategory),
    [categories, selectedCategory],
  );

  const activeSubCategory = useMemo(
    () => activeCategory?.children.find((s) => s.id === selectedSubCategory),
    [activeCategory, selectedSubCategory],
  );

  // Products to display
  const products = useMemo(() => {
    if (isSearching) return searchResults;
    if (activeSubCategory) return activeSubCategory.items;
    if (activeCategory) return activeCategory.children.flatMap((s) => s.items);
    return [];
  }, [isSearching, searchResults, activeSubCategory, activeCategory]);

  const loading = isSearching ? searchLoading : catLoading;

  return (
    <Box>
      <TextField
        fullWidth
        size="small"
        placeholder="Produkt suchen..."
        value={query}
        onChange={(e) => handleQueryChange(e.target.value)}
        sx={{ mb: 2 }}
      />

      {!isSearching && (
        <>
          <CategoryChips
            items={categories}
            selected={selectedCategory}
            onSelect={setSelectedCategory}
          />
          {activeCategory && activeCategory.children.length > 0 && (
            <Box sx={{ mt: 1 }}>
              <CategoryChips
                items={activeCategory.children}
                selected={selectedSubCategory}
                onSelect={setSelectedSubCategory}
              />
            </Box>
          )}
        </>
      )}

      <Box sx={{ mt: 2 }}>
        {loading ? (
          <Box display="flex" justifyContent="center" py={4}>
            <CircularProgress />
          </Box>
        ) : products.length === 0 ? (
          <Typography color="text.secondary" textAlign="center" py={4}>
            {isSearching
              ? "Keine Ergebnisse"
              : selectedCategory
                ? "Keine Produkte in dieser Kategorie"
                : "Wähle eine Kategorie oder suche nach Produkten"}
          </Typography>
        ) : (
          <ProductGrid
            items={products}
            cartQuantities={cartQuantities}
            orderQuantities={orderQuantities}
            inventoryQuantities={inventoryQuantities}
            subscribedIds={subscribedIds}
            onProductClick={onProductClick}
          />
        )}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/frontend/src/components/picnic/store/
git commit -m "feat(frontend): add StoreTab with category navigation and product grid"
```

---

## Task 11: Build CartTab component

**Files:**
- Create: `recipe-assistant/frontend/src/components/picnic/cart/CartTab.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/cart/CartItem.tsx`

- [ ] **Step 1: Create CartItem**

Create `recipe-assistant/frontend/src/components/picnic/cart/CartItem.tsx`:

```tsx
import { useState } from "react";
import { Box, IconButton, Stack, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import type { CartItem as CartItemType } from "../../../types";

const imgUrl = (imageId: string | null) =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/small.png`
    : undefined;

const formatPrice = (cents: number | null) =>
  cents != null ? `€${(cents / 100).toFixed(2).replace(".", ",")}` : "";

interface CartItemProps {
  item: CartItemType;
  onAdd: (picnicId: string) => Promise<void>;
  onRemove: (picnicId: string, count: number) => Promise<void>;
  onClick: (picnicId: string) => void;
}

export default function CartItem({ item, onAdd, onRemove, onClick }: CartItemProps) {
  const [busy, setBusy] = useState(false);

  const handleAdd = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true);
    try { await onAdd(item.picnic_id); } finally { setBusy(false); }
  };

  const handleRemove = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true);
    try { await onRemove(item.picnic_id, 1); } finally { setBusy(false); }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true);
    try { await onRemove(item.picnic_id, item.quantity); } finally { setBusy(false); }
  };

  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={1.5}
      sx={{ py: 1, px: 1, borderBottom: "1px solid", borderColor: "divider", cursor: "pointer" }}
      onClick={() => onClick(item.picnic_id)}
    >
      {item.image_id && (
        <Box
          component="img"
          src={imgUrl(item.image_id)}
          alt={item.name}
          sx={{ width: 48, height: 48, objectFit: "contain" }}
        />
      )}
      <Box flex={1} minWidth={0}>
        <Typography variant="body2" noWrap fontWeight={500}>{item.name}</Typography>
        <Typography variant="caption" color="text.secondary">
          {item.unit_quantity} {item.price_cents != null && `· ${formatPrice(item.price_cents)}`}
        </Typography>
      </Box>
      <Stack direction="row" alignItems="center" spacing={0.5}>
        <IconButton size="small" onClick={handleRemove} disabled={busy}><RemoveIcon fontSize="small" /></IconButton>
        <Typography variant="body2" sx={{ minWidth: 24, textAlign: "center" }}>{item.quantity}</Typography>
        <IconButton size="small" onClick={handleAdd} disabled={busy}><AddIcon fontSize="small" /></IconButton>
        <IconButton size="small" onClick={handleDelete} disabled={busy} color="error"><DeleteOutlineIcon fontSize="small" /></IconButton>
      </Stack>
      <Typography variant="body2" fontWeight={600} sx={{ minWidth: 50, textAlign: "right" }}>
        {formatPrice(item.total_price_cents)}
      </Typography>
    </Stack>
  );
}
```

- [ ] **Step 2: Create CartTab**

Create `recipe-assistant/frontend/src/components/picnic/cart/CartTab.tsx`:

```tsx
import { Box, Button, CircularProgress, Divider, Stack, Typography } from "@mui/material";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import CartItemComponent from "./CartItem";
import type { Cart } from "../../../types";

const formatPrice = (cents: number) => `€${(cents / 100).toFixed(2).replace(".", ",")}`;

interface CartTabProps {
  cart: Cart | null;
  loading: boolean;
  onAdd: (picnicId: string, count?: number) => Promise<void>;
  onRemove: (picnicId: string, count: number) => Promise<void>;
  onClear: () => Promise<void>;
  onProductClick: (picnicId: string) => void;
}

export default function CartTab({ cart, loading, onAdd, onRemove, onClear, onProductClick }: CartTabProps) {
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" py={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (!cart || cart.items.length === 0) {
    return (
      <Typography color="text.secondary" textAlign="center" py={4}>
        Dein Warenkorb ist leer
      </Typography>
    );
  }

  const handleAdd = async (picnicId: string) => {
    await onAdd(picnicId, 1);
  };

  return (
    <Box>
      {cart.items.map((item) => (
        <CartItemComponent
          key={item.picnic_id}
          item={item}
          onAdd={handleAdd}
          onRemove={onRemove}
          onClick={onProductClick}
        />
      ))}
      <Divider sx={{ my: 2 }} />
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 1 }}>
        <Typography variant="body1">
          {cart.total_items} Artikel
        </Typography>
        <Typography variant="h6" fontWeight={600}>
          {formatPrice(cart.total_price_cents)}
        </Typography>
      </Stack>
      <Box sx={{ mt: 2, display: "flex", justifyContent: "flex-end" }}>
        <Button
          variant="outlined"
          color="error"
          startIcon={<DeleteSweepIcon />}
          onClick={onClear}
          size="small"
        >
          Warenkorb leeren
        </Button>
      </Box>
    </Box>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/frontend/src/components/picnic/cart/
git commit -m "feat(frontend): add CartTab and CartItem components"
```

---

## Task 12: Build OrdersTab component (pending orders + import)

**Files:**
- Create: `recipe-assistant/frontend/src/components/picnic/orders/OrdersTab.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/orders/OrderCard.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/orders/ImportSection.tsx`

- [ ] **Step 1: Create OrderCard**

Create `recipe-assistant/frontend/src/components/picnic/orders/OrderCard.tsx`:

```tsx
import { useState } from "react";
import {
  Box,
  Card,
  CardContent,
  Chip,
  Collapse,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { PendingOrder } from "../../../types";

const imgUrl = (imageId: string | null) =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/small.png`
    : undefined;

const formatDate = (iso: string | null) => {
  if (!iso) return "Unbekannt";
  const d = new Date(iso);
  return d.toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

interface OrderCardProps {
  order: PendingOrder;
}

export default function OrderCard({ order }: OrderCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card variant="outlined" sx={{ mb: 1 }}>
      <CardContent sx={{ pb: expanded ? 1 : "16px !important" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="body1" fontWeight={500}>
              Lieferung {formatDate(order.delivery_time)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {order.total_items} Artikel
            </Typography>
          </Box>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Chip label={order.status} size="small" variant="outlined" />
            <IconButton
              size="small"
              onClick={() => setExpanded(!expanded)}
              sx={{ transform: expanded ? "rotate(180deg)" : "none", transition: "0.2s" }}
            >
              <ExpandMoreIcon />
            </IconButton>
          </Stack>
        </Stack>
        <Collapse in={expanded}>
          <Stack spacing={1} sx={{ mt: 2 }}>
            {order.items.map((item, i) => (
              <Stack key={i} direction="row" alignItems="center" spacing={1}>
                {item.image_id && (
                  <Box
                    component="img"
                    src={imgUrl(item.image_id)}
                    alt={item.name}
                    sx={{ width: 32, height: 32, objectFit: "contain" }}
                  />
                )}
                <Typography variant="body2" flex={1} noWrap>{item.name}</Typography>
                <Typography variant="body2" color="text.secondary">{item.quantity}x</Typography>
              </Stack>
            ))}
          </Stack>
        </Collapse>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Create ImportSection**

Refactor the import logic from `PicnicImportPage.tsx` into a standalone component.

Create `recipe-assistant/frontend/src/components/picnic/orders/ImportSection.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Paper, Typography } from "@mui/material";
import { usePicnicImport } from "../../../hooks/usePicnic";
import { useTrackedProducts } from "../../../hooks/useTrackedProducts";
import { getStorageLocations } from "../../../api/client";
import { useNotification } from "../../NotificationProvider";
import ReviewCard from "../ReviewCard";
import PromoteBarcodeDialog from "../PromoteBarcodeDialog";
import type { ImportDecision, TrackedProduct } from "../../../types";

export default function ImportSection() {
  const { data, loading, error, fetchImport, commit } = usePicnicImport();
  const { items: tracked } = useTrackedProducts();
  const { notify } = useNotification();
  const [storageLocations, setStorageLocations] = useState<string[]>([]);
  const [decisions, setDecisions] = useState<Record<string, Record<string, ImportDecision>>>({});
  const [promoteTarget, setPromoteTarget] = useState<TrackedProduct | null>(null);

  useEffect(() => {
    fetchImport();
    getStorageLocations().then(setStorageLocations).catch(() => {});
  }, [fetchImport]);

  const synthTrackedMap = useMemo(() => {
    const map: Record<string, TrackedProduct> = {};
    for (const tp of tracked) {
      if (tp.barcode.startsWith("picnic:") && tp.picnic_id) {
        map[tp.picnic_id] = tp;
      }
    }
    return map;
  }, [tracked]);

  const handleDecision = (deliveryId: string, picnicId: string, decision: ImportDecision) => {
    setDecisions((prev) => ({
      ...prev,
      [deliveryId]: { ...prev[deliveryId], [picnicId]: decision },
    }));
  };

  const handleCommit = async (deliveryId: string) => {
    const deliveryDecisions = Object.values(decisions[deliveryId] ?? {});
    if (deliveryDecisions.length === 0) return;
    try {
      const result = await commit(deliveryId, deliveryDecisions);
      notify(`Import: ${result.imported} zugeordnet, ${result.created} neu, ${result.skipped} übersprungen`, "success");
      fetchImport();
    } catch {
      notify("Import fehlgeschlagen", "error");
    }
  };

  if (loading) return <Typography color="text.secondary">Lade Lieferungen...</Typography>;
  if (error) return <Alert severity="error">{error}</Alert>;
  if (!data || data.deliveries.length === 0) {
    return <Typography color="text.secondary" textAlign="center" py={2}>Keine neuen Lieferungen zum Importieren</Typography>;
  }

  return (
    <Box>
      {data.deliveries.map((delivery) => (
        <Paper key={delivery.delivery_id} variant="outlined" sx={{ p: 2, mb: 2 }}>
          <Typography variant="subtitle1" fontWeight={500} gutterBottom>
            Lieferung vom {delivery.delivered_at ? new Date(delivery.delivered_at).toLocaleDateString("de-DE") : "Unbekannt"}
          </Typography>
          {delivery.items.map((candidate) => (
            <ReviewCard
              key={candidate.picnic_id}
              candidate={candidate}
              storageLocations={storageLocations}
              onChange={(d) => handleDecision(delivery.delivery_id, candidate.picnic_id, d)}
              synthTracked={synthTrackedMap[candidate.picnic_id] ?? null}
              onPromote={setPromoteTarget}
            />
          ))}
          <Button
            variant="contained"
            onClick={() => handleCommit(delivery.delivery_id)}
            disabled={Object.keys(decisions[delivery.delivery_id] ?? {}).length === 0}
            sx={{ mt: 1 }}
          >
            Importieren
          </Button>
        </Paper>
      ))}
      {promoteTarget && (
        <PromoteBarcodeDialog
          product={promoteTarget}
          onClose={() => setPromoteTarget(null)}
          onSuccess={() => { setPromoteTarget(null); fetchImport(); }}
        />
      )}
    </Box>
  );
}
```

- [ ] **Step 3: Create OrdersTab**

Create `recipe-assistant/frontend/src/components/picnic/orders/OrdersTab.tsx`:

```tsx
import { Box, CircularProgress, Divider, Typography } from "@mui/material";
import type { PendingOrder } from "../../../types";
import OrderCard from "./OrderCard";
import ImportSection from "./ImportSection";

interface OrdersTabProps {
  orders: PendingOrder[];
  loading: boolean;
}

export default function OrdersTab({ orders, loading }: OrdersTabProps) {
  return (
    <Box>
      <Typography variant="h6" gutterBottom>Laufende Bestellungen</Typography>
      {loading ? (
        <Box display="flex" justifyContent="center" py={2}><CircularProgress /></Box>
      ) : orders.length === 0 ? (
        <Typography color="text.secondary" sx={{ mb: 2 }}>Keine laufenden Bestellungen</Typography>
      ) : (
        <Box sx={{ mb: 3 }}>
          {orders.map((order) => (
            <OrderCard key={order.delivery_id} order={order} />
          ))}
        </Box>
      )}

      <Divider sx={{ my: 3 }} />

      <Typography variant="h6" gutterBottom>Lieferungen importieren</Typography>
      <ImportSection />
    </Box>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/frontend/src/components/picnic/orders/
git commit -m "feat(frontend): add OrdersTab with pending orders and import section"
```

---

## Task 13: Build SubscriptionsTab component

**Files:**
- Create: `recipe-assistant/frontend/src/components/picnic/subscriptions/SubscriptionsTab.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/subscriptions/SubscriptionCard.tsx`

- [ ] **Step 1: Create SubscriptionCard**

Create `recipe-assistant/frontend/src/components/picnic/subscriptions/SubscriptionCard.tsx`:

```tsx
import { Box, Card, CardContent, Chip, IconButton, Stack, Typography } from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import type { TrackedProduct } from "../../../types";

const imgUrl = (imageId: string | null) =>
  imageId
    ? `https://storefront-prod.de.picnicinternational.com/static/images/${imageId}/small.png`
    : undefined;

interface SubscriptionCardProps {
  item: TrackedProduct;
  onOrder: number;
  onEdit: (item: TrackedProduct) => void;
  onDelete: (item: TrackedProduct) => void;
}

type ThresholdStatus = "ok" | "on_order" | "critical";

function getStatus(item: TrackedProduct, onOrder: number): ThresholdStatus {
  if (item.current_quantity >= item.min_quantity) return "ok";
  if (onOrder > 0) return "on_order";
  return "critical";
}

const statusColor: Record<ThresholdStatus, "success" | "warning" | "error"> = {
  ok: "success",
  on_order: "warning",
  critical: "error",
};

const statusLabel: Record<ThresholdStatus, string> = {
  ok: "Auf Lager",
  on_order: "In Bestellung",
  critical: "Nachbestellen",
};

export default function SubscriptionCard({ item, onOrder, onEdit, onDelete }: SubscriptionCardProps) {
  const status = getStatus(item, onOrder);

  return (
    <Card variant="outlined" sx={{ mb: 1 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          {item.picnic_image_id && (
            <Box
              component="img"
              src={imgUrl(item.picnic_image_id)}
              alt={item.name}
              sx={{ width: 48, height: 48, objectFit: "contain" }}
            />
          )}
          <Box flex={1} minWidth={0}>
            <Typography variant="body1" fontWeight={500} noWrap>
              {item.picnic_name || item.name}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
              <Typography variant="caption" color="text.secondary">
                Bestand: {item.current_quantity} · Min: {item.min_quantity} · Ziel: {item.target_quantity}
              </Typography>
              {onOrder > 0 && (
                <Chip label={`${onOrder} in Bestellung`} size="small" color="warning" />
              )}
            </Stack>
          </Box>
          <Chip label={statusLabel[status]} size="small" color={statusColor[status]} />
          <IconButton size="small" onClick={() => onEdit(item)}><EditIcon fontSize="small" /></IconButton>
          <IconButton size="small" onClick={() => onDelete(item)} color="error"><DeleteIcon fontSize="small" /></IconButton>
        </Stack>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Create SubscriptionsTab**

Create `recipe-assistant/frontend/src/components/picnic/subscriptions/SubscriptionsTab.tsx`:

```tsx
import { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { useTrackedProducts } from "../../../hooks/useTrackedProducts";
import { useNotification } from "../../NotificationProvider";
import SubscriptionCard from "./SubscriptionCard";
import TrackedProductForm from "../TrackedProductForm";
import PromoteBarcodeDialog from "../PromoteBarcodeDialog";
import type { TrackedProduct, TrackedProductCreate } from "../../../types";

interface SubscriptionsTabProps {
  orderQuantities: Record<string, number>;
}

export default function SubscriptionsTab({ orderQuantities }: SubscriptionsTabProps) {
  const { items, loading, create, update, remove, promote, refetch } = useTrackedProducts();
  const { notify } = useNotification();
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TrackedProduct | null>(null);
  const [promoteTarget, setPromoteTarget] = useState<TrackedProduct | null>(null);

  const handleCreate = async (data: TrackedProductCreate) => {
    await create(data);
    notify("Abo erstellt", "success");
    setFormOpen(false);
  };

  const handleUpdate = async (data: { min_quantity?: number; target_quantity?: number }) => {
    if (!editTarget) return;
    await update(editTarget.barcode, data);
    notify("Abo aktualisiert", "success");
    setEditTarget(null);
  };

  const handleDelete = async (item: TrackedProduct) => {
    if (!window.confirm(`"${item.picnic_name || item.name}" wirklich löschen?`)) return;
    await remove(item.barcode);
    notify("Abo gelöscht", "success");
  };

  if (loading) {
    return <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>;
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h6">Abos ({items.length})</Typography>
        <Button startIcon={<AddIcon />} variant="contained" size="small" onClick={() => setFormOpen(true)}>
          Neues Abo
        </Button>
      </Box>

      {items.length === 0 ? (
        <Typography color="text.secondary" textAlign="center" py={4}>
          Noch keine Abos eingerichtet
        </Typography>
      ) : (
        items.map((item) => (
          <SubscriptionCard
            key={item.barcode}
            item={item}
            onOrder={orderQuantities[item.picnic_id] ?? 0}
            onEdit={setEditTarget}
            onDelete={handleDelete}
          />
        ))
      )}

      {(formOpen || editTarget) && (
        <TrackedProductForm
          product={editTarget}
          onClose={() => { setFormOpen(false); setEditTarget(null); }}
          onSubmit={editTarget ? handleUpdate : handleCreate}
        />
      )}

      {promoteTarget && (
        <PromoteBarcodeDialog
          product={promoteTarget}
          onClose={() => setPromoteTarget(null)}
          onSuccess={() => { setPromoteTarget(null); refetch(); }}
        />
      )}
    </Box>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/frontend/src/components/picnic/subscriptions/
git commit -m "feat(frontend): add SubscriptionsTab and SubscriptionCard components"
```

---

## Task 14: Build the new PicnicStorePage shell

**Files:**
- Modify: `recipe-assistant/frontend/src/pages/PicnicStorePage.tsx`

- [ ] **Step 1: Rewrite PicnicStorePage**

Replace the entire contents of `recipe-assistant/frontend/src/pages/PicnicStorePage.tsx`:

```tsx
import { useCallback, useMemo, useState } from "react";
import { Alert, Badge, Box, CircularProgress, Container, Tab, Tabs } from "@mui/material";
import { usePicnicStatus } from "../hooks/usePicnic";
import { usePicnicCart } from "../hooks/usePicnicCart";
import { usePicnicPendingOrders } from "../hooks/usePicnicOrders";
import { useTrackedProducts } from "../hooks/useTrackedProducts";
import StoreTab from "../components/picnic/store/StoreTab";
import CartTab from "../components/picnic/cart/CartTab";
import OrdersTab from "../components/picnic/orders/OrdersTab";
import SubscriptionsTab from "../components/picnic/subscriptions/SubscriptionsTab";
import ProductDetailModal from "../components/picnic/store/ProductDetailModal";
import SubscribeDialog from "../components/picnic/SubscribeDialog";
import type { TrackedProductCreate } from "../types";

export default function PicnicStorePage() {
  const { status, loading: statusLoading } = usePicnicStatus();
  const { cart, loading: cartLoading, add: cartAdd, remove: cartRemove, clear: cartClear, refetch: refetchCart } = usePicnicCart();
  const { orders, quantityMap: orderQuantities, loading: ordersLoading } = usePicnicPendingOrders();
  const { items: tracked, create: createTracked } = useTrackedProducts();

  const [tab, setTab] = useState(0);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [subscribeTarget, setSubscribeTarget] = useState<{ picnicId: string; name: string } | null>(null);

  // Derived data for badges
  const cartQuantities = useMemo(() => {
    const map: Record<string, number> = {};
    for (const item of cart?.items ?? []) {
      map[item.picnic_id] = item.quantity;
    }
    return map;
  }, [cart]);

  const inventoryQuantities = useMemo<Record<string, number>>(() => {
    // This would need an endpoint or be empty for now — products show inventory via detail modal
    return {};
  }, []);

  const subscribedIds = useMemo(() => {
    return new Set(tracked.map((t) => t.picnic_id));
  }, [tracked]);

  const handleCartAdd = useCallback(async (picnicId: string, count = 1) => {
    await cartAdd(picnicId, count);
  }, [cartAdd]);

  const handleCartRemove = useCallback(async (picnicId: string, count = 1) => {
    await cartRemove(picnicId, count);
  }, [cartRemove]);

  const handleSubscribe = useCallback(async (data: TrackedProductCreate) => {
    await createTracked(data);
    setSubscribeTarget(null);
  }, [createTracked]);

  if (statusLoading) {
    return <Box display="flex" justifyContent="center" py={8}><CircularProgress /></Box>;
  }

  if (!status?.enabled) {
    return (
      <Container maxWidth="sm" sx={{ mt: 4 }}>
        <Alert severity="info">Picnic ist nicht konfiguriert.</Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 2, mb: 4 }}>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Store" />
        <Tab
          label={
            <Badge badgeContent={cart?.total_items ?? 0} color="primary" max={99}>
              <Box sx={{ px: 1 }}>Warenkorb</Box>
            </Badge>
          }
        />
        <Tab label="Bestellungen" />
        <Tab label="Abos" />
      </Tabs>

      {tab === 0 && (
        <StoreTab
          cartQuantities={cartQuantities}
          orderQuantities={orderQuantities}
          inventoryQuantities={inventoryQuantities}
          subscribedIds={subscribedIds}
          onProductClick={setDetailId}
        />
      )}
      {tab === 1 && (
        <CartTab
          cart={cart}
          loading={cartLoading}
          onAdd={handleCartAdd}
          onRemove={handleCartRemove}
          onClear={cartClear}
          onProductClick={setDetailId}
        />
      )}
      {tab === 2 && (
        <OrdersTab orders={orders} loading={ordersLoading} />
      )}
      {tab === 3 && (
        <SubscriptionsTab orderQuantities={orderQuantities} />
      )}

      <ProductDetailModal
        picnicId={detailId}
        onClose={() => setDetailId(null)}
        onCartAdd={handleCartAdd}
        onCartRemove={handleCartRemove}
        onSubscribe={(picnicId, name) => setSubscribeTarget({ picnicId, name })}
      />

      {subscribeTarget && (
        <SubscribeDialog
          product={{ picnic_id: subscribeTarget.picnicId, name: subscribeTarget.name, image_id: null, unit_quantity: null, price_cents: null }}
          onClose={() => setSubscribeTarget(null)}
          onSubmit={handleSubscribe}
        />
      )}
    </Container>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add recipe-assistant/frontend/src/pages/PicnicStorePage.tsx
git commit -m "feat(frontend): rewrite PicnicStorePage as 4-tab shell"
```

---

## Task 15: Update routing and navigation

**Files:**
- Modify: `recipe-assistant/frontend/src/App.tsx`
- Modify: `recipe-assistant/frontend/src/components/Navbar.tsx`

- [ ] **Step 1: Remove old routes**

In `recipe-assistant/frontend/src/App.tsx`:
- Remove imports: `ShoppingListPage`, `PicnicImportPage`, `TrackedProductsPage`
- Remove routes: `/shopping-list`, `/picnic-import`, `/tracked-products`
- Rename `/picnic-store` to `/picnic`

Keep: `/picnic-login` route.

- [ ] **Step 2: Update Navbar**

In `recipe-assistant/frontend/src/components/Navbar.tsx`:
- Replace the 4 Picnic nav items (Picnic-Import, Einkaufsliste, Nachbestellungen, Picnic Store) with a single entry:
  ```tsx
  { path: "/picnic", label: "Picnic", icon: <StorefrontIcon /> }
  ```
- Keep the Picnic Login entry for `needs_login` state.

- [ ] **Step 3: Delete removed pages**

Delete these files (they are now integrated into the store):
- `recipe-assistant/frontend/src/pages/ShoppingListPage.tsx`
- `recipe-assistant/frontend/src/pages/PicnicImportPage.tsx`
- `recipe-assistant/frontend/src/pages/TrackedProductsPage.tsx`

- [ ] **Step 4: Remove old StoreResultCard**

Delete `recipe-assistant/frontend/src/components/picnic/StoreResultCard.tsx` (replaced by `store/ProductCard.tsx`).

- [ ] **Step 5: Verify build**

Run: `cd recipe-assistant/frontend && npm run build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add -A recipe-assistant/frontend/
git commit -m "refactor(frontend): consolidate routing — single Picnic nav entry, remove old pages"
```

---

## Task 16: Add "in Bestellung" badges to InventoryPage

**Files:**
- Modify: `recipe-assistant/frontend/src/pages/InventoryPage.tsx`

- [ ] **Step 1: Import pending orders hook and add to page**

At top of `InventoryPage.tsx`, add:
```tsx
import { usePicnicPendingOrders } from "../hooks/usePicnicOrders";
```

Inside the component, add:
```tsx
const { quantityMap: orderQuantities } = usePicnicPendingOrders();
```

- [ ] **Step 2: Build EAN-to-picnic-id reverse lookup**

To show "in Bestellung" badges, we need to map inventory barcodes to picnic_ids. The cleanest approach: add a lightweight endpoint or use the tracked products data which already has barcode→picnic_id mappings.

Use the existing tracked products data:
```tsx
const barcodeToOrderQty = useMemo(() => {
  const map: Record<string, number> = {};
  for (const tp of trackedProducts) {
    if (tp.picnic_id && orderQuantities[tp.picnic_id]) {
      map[tp.barcode] = orderQuantities[tp.picnic_id];
    }
  }
  return map;
}, [trackedProducts, orderQuantities]);
```

(Note: `trackedProducts` may need to be loaded — check if `useTrackedProducts` is already imported in the page. If not, add it.)

- [ ] **Step 3: Add orange chip in quantity cell**

In the table row where item quantity is displayed (~line 324), after the existing "leer, nachbestellt" text, add:

```tsx
{barcodeToOrderQty[item.barcode] > 0 && (
  <Chip
    label={`${barcodeToOrderQty[item.barcode]} in Bestellung`}
    size="small"
    color="warning"
    sx={{ mt: 0.5 }}
  />
)}
```

- [ ] **Step 4: Update threshold color logic**

Where the page currently shows red for items below threshold, update to show yellow when the item is in a pending order:

```tsx
{item.quantity === 0 && trackedByBarcode.has(item.barcode) && (
  <Typography
    variant="caption"
    color={barcodeToOrderQty[item.barcode] > 0 ? "warning.main" : "error"}
    display="block"
    sx={{ mt: 0.5 }}
  >
    {barcodeToOrderQty[item.barcode] > 0 ? "in Bestellung" : "leer, nachbestellen"}
  </Typography>
)}
```

- [ ] **Step 5: Verify build**

Run: `cd recipe-assistant/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/frontend/src/pages/InventoryPage.tsx
git commit -m "feat(inventory): show 'in Bestellung' badges for items in pending Picnic orders"
```

---

## Task 17: Create Alembic migration and run full test suite

**Files:**
- Create: Alembic migration (auto-generated)

- [ ] **Step 1: Generate migration**

Run: `cd recipe-assistant/backend && alembic revision --autogenerate -m "drop shopping_list table"`

Verify the migration file contains:
- `op.drop_table('shopping_list')` in `upgrade()`
- Corresponding `create_table` in `downgrade()`

- [ ] **Step 2: Run backend tests**

Run: `cd recipe-assistant/backend && python -m pytest -v`
Expected: All pass.

- [ ] **Step 3: Run frontend build**

Run: `cd recipe-assistant/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Commit migration**

```bash
git add recipe-assistant/backend/alembic/
git commit -m "migration: drop shopping_list table"
```

---

## Task 18: Bump version

**Files:**
- Modify: `recipe-assistant/config.json`

- [ ] **Step 1: Read current version**

Read `recipe-assistant/config.json` to find the current `version` field.

- [ ] **Step 2: Bump minor version**

Increment the minor version number.

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/config.json
git commit -m "chore: bump version to X.Y.Z"
```
