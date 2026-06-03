# Eigene Produkte + A4-Barcode-Blatt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nutzer können eigene Produkte (z. B. „Banane") ohne echten EAN anlegen und ein druckbares A4-Barcode-Blatt für beliebige Inventar-Produkte (eigene *und* echte) erzeugen.

**Architecture:** Eigene Produkte bekommen einen synthetischen Barcode `EIGEN-<token>` (analog zum bestehenden `picnic:<id>`-Muster). Scan-Pfade überspringen den externen Lookup bei diesem Präfix; eigene Produkte werden bei Menge 0 als Zombie-Zeile behalten, damit der gedruckte Code gültig bleibt. Eine neue Spalte `include_in_sheet` markiert Produkte fürs A4-Blatt, das per reportlab (Code128, eingebaut) im Backend als PDF gerendert wird.

**Tech Stack:** FastAPI, async SQLAlchemy, Alembic, Pydantic, pytest (asyncio_mode=auto, SQLite in-memory), reportlab (neu); Frontend React 19 + TypeScript + MUI.

**Referenz-Spec:** `docs/superpowers/specs/2026-06-03-custom-products-barcode-sheet-design.md`

---

## File Structure

**Backend (neu):**
- `recipe-assistant/backend/app/services/custom_products.py` — `EIGEN-`-Barcode-Konvention (Helper)
- `recipe-assistant/backend/app/services/barcode_sheet.py` — PDF-Rendering via reportlab
- `recipe-assistant/backend/alembic/versions/010_add_include_in_sheet.py` — Migration
- `recipe-assistant/backend/tests/test_custom_products.py` — Helper-Tests
- `recipe-assistant/backend/tests/test_inventory_custom.py` — Endpoint-/Scan-/Zombie-Tests
- `recipe-assistant/backend/tests/test_barcode_sheet.py` — PDF-Endpoint-Tests

**Backend (geändert):**
- `app/models/inventory.py` — Spalte `include_in_sheet`
- `app/schemas/inventory.py` — `CustomProductCreate`, `include_in_sheet` in Response + Update
- `app/routers/inventory.py` — `POST /custom`, `GET /barcode-sheet.pdf`, Scan-Lookup-Skip, Zombie-Regel, Update-Feld
- `pyproject.toml` — Dependency `reportlab`

**Frontend (geändert):**
- `src/types/index.ts` — `include_in_sheet` in `InventoryItem`
- `src/api/client.ts` — `createCustomProduct`, `updateItem` erweitern, `barcodeSheetUrl`
- `src/hooks/useInventory.ts` — `createCustom`
- `src/pages/InventoryPage.tsx` — Dialog, „auf PDF"-Spalte, Download-Button

---

## Task 1: `EIGEN-`-Barcode-Helper

**Files:**
- Create: `recipe-assistant/backend/app/services/custom_products.py`
- Test: `recipe-assistant/backend/tests/test_custom_products.py`

- [ ] **Step 1: Write the failing test**

```python
# recipe-assistant/backend/tests/test_custom_products.py
from app.services.custom_products import (
    CUSTOM_BARCODE_PREFIX,
    is_custom_barcode,
    make_custom_barcode,
)


def test_make_custom_barcode_has_prefix():
    bc = make_custom_barcode()
    assert bc.startswith(CUSTOM_BARCODE_PREFIX)
    assert is_custom_barcode(bc)


def test_make_custom_barcode_is_unique():
    assert make_custom_barcode() != make_custom_barcode()


def test_real_ean_is_not_custom():
    assert not is_custom_barcode("4006381333931")
    assert not is_custom_barcode("picnic:12345")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd recipe-assistant/backend && pytest tests/test_custom_products.py -v`
Expected: FAIL (ModuleNotFoundError: app.services.custom_products)

- [ ] **Step 3: Write minimal implementation**

```python
# recipe-assistant/backend/app/services/custom_products.py
"""Synthetic barcode convention for user-created ("eigene") products.

Products the user defines themselves (e.g. loose fruit with no EAN) get a
placeholder barcode of the form ``EIGEN-<token>``. The scan paths detect this
prefix to skip the external OpenFoodFacts lookup, and the decrement logic keeps
such rows alive at quantity 0 so a printed barcode stays valid.
"""

from __future__ import annotations

import uuid

CUSTOM_BARCODE_PREFIX = "EIGEN-"


def is_custom_barcode(barcode: str) -> bool:
    """Return True if *barcode* follows the ``EIGEN-<token>`` convention."""
    return barcode.startswith(CUSTOM_BARCODE_PREFIX)


def make_custom_barcode() -> str:
    """Build a collision-free synthetic barcode for a user-created product."""
    return f"{CUSTOM_BARCODE_PREFIX}{uuid.uuid4().hex[:12].upper()}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd recipe-assistant/backend && pytest tests/test_custom_products.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/custom_products.py recipe-assistant/backend/tests/test_custom_products.py
git commit -m "feat: add EIGEN- custom barcode helper"
```

---

## Task 2: Modell-Spalte `include_in_sheet`

**Files:**
- Modify: `recipe-assistant/backend/app/models/inventory.py:31-35`

> Tests erzeugen das Schema via `Base.metadata.create_all` (conftest.py:29), daher reicht für Tests die Modell-Spalte. Die Alembic-Migration (Task 9) ist für die Produktions-DB.

- [ ] **Step 1: Add the column to the model**

In `recipe-assistant/backend/app/models/inventory.py`, direkt nach der `image_url`-Spalte (Zeile 31) einfügen:

```python
    include_in_sheet: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
```

(`Boolean` und `text` sind bereits importiert, siehe Zeile 5.)

- [ ] **Step 2: Verify the model imports cleanly**

Run: `cd recipe-assistant/backend && python -c "from app.models.inventory import InventoryItem; print(InventoryItem.include_in_sheet)"`
Expected: gibt das Spalten-Attribut aus, kein ImportError

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/app/models/inventory.py
git commit -m "feat: add include_in_sheet column to InventoryItem model"
```

---

## Task 3: Schemas erweitern (`CustomProductCreate`, `include_in_sheet`)

**Files:**
- Modify: `recipe-assistant/backend/app/schemas/inventory.py`

- [ ] **Step 1: Add include_in_sheet to InventoryItemResponse**

In `recipe-assistant/backend/app/schemas/inventory.py`, in `InventoryItemResponse` (nach Zeile 28 `is_pinned: bool = False`) ergänzen:

```python
    include_in_sheet: bool = False
```

- [ ] **Step 2: Add include_in_sheet to InventoryUpdateRequest**

In `InventoryUpdateRequest` (nach Zeile 48 `expiration_date: date | None = None`) ergänzen:

```python
    include_in_sheet: bool | None = None
```

- [ ] **Step 3: Add CustomProductCreate schema**

Am Ende von `recipe-assistant/backend/app/schemas/inventory.py` anfügen:

```python
class CustomProductCreate(BaseModel):
    name: str
    category: str | None = None
    storage_location: str | None = None
    quantity: int = 0
```

- [ ] **Step 4: Verify import**

Run: `cd recipe-assistant/backend && python -c "from app.schemas.inventory import CustomProductCreate, InventoryUpdateRequest, InventoryItemResponse; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/schemas/inventory.py
git commit -m "feat: add CustomProductCreate schema and include_in_sheet fields"
```

---

## Task 4: `POST /api/inventory/custom` Endpoint

**Files:**
- Modify: `recipe-assistant/backend/app/routers/inventory.py`
- Test: `recipe-assistant/backend/tests/test_inventory_custom.py`

- [ ] **Step 1: Write the failing test**

```python
# recipe-assistant/backend/tests/test_inventory_custom.py
async def test_create_custom_product_generates_eigen_barcode(client):
    resp = await client.post("/api/inventory/custom", json={"name": "Banane"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Banane"
    assert data["barcode"].startswith("EIGEN-")
    assert data["quantity"] == 0
    assert data["category"] == "Eigene Produkte"


async def test_create_custom_product_with_quantity_and_location(client):
    resp = await client.post(
        "/api/inventory/custom",
        json={"name": "Apfel", "quantity": 3, "storage_location": "Obstkorb"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["quantity"] == 3
    assert data["storage_location"]["name"] == "Obstkorb"


async def test_custom_product_appears_in_inventory(client):
    await client.post("/api/inventory/custom", json={"name": "Gurke"})
    listing = await client.get("/api/inventory/")
    names = [i["name"] for i in listing.json()]
    assert "Gurke" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_custom.py -v`
Expected: FAIL (404 — Endpoint existiert nicht)

- [ ] **Step 3: Add the endpoint**

In `recipe-assistant/backend/app/routers/inventory.py`:

Import-Block ergänzen (bei den Schema-Imports, nach Zeile 26):

```python
from app.schemas.inventory import (
    BarcodeAddRequest,
    BarcodeRemoveRequest,
    CustomProductCreate,
    InventoryItemResponse,
    InventoryUpdateRequest,
    ScanInRequest,
    ScanOutRequest,
)
```

Und den Helper-Import nach Zeile 31:

```python
from app.services.custom_products import is_custom_barcode, make_custom_barcode
```

Neuen Endpoint direkt vor `@router.post("/barcode", ...)` (Zeile 327) einfügen:

```python
@router.post("/custom", status_code=201, response_model=InventoryItemResponse)
async def create_custom_product(
    req: CustomProductCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a user-defined product with an auto-assigned EIGEN- barcode.

    No external barcode lookup: name/category come straight from the user.
    """
    barcode = make_custom_barcode()
    location_id = await _resolve_storage_location(db, req.storage_location)
    item = InventoryItem(
        barcode=barcode,
        name=req.name,
        quantity=req.quantity,
        category=req.category or "Eigene Produkte",
        storage_location_id=location_id,
    )
    db.add(item)
    await _log_action(db, barcode, "create-custom", f"name: {req.name}")
    await db.commit()

    result = await db.execute(
        select(InventoryItem)
        .options(selectinload(InventoryItem.storage_location))
        .where(InventoryItem.barcode == barcode)
    )
    return result.scalar_one()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_custom.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/routers/inventory.py recipe-assistant/backend/tests/test_inventory_custom.py
git commit -m "feat: add POST /inventory/custom endpoint"
```

---

## Task 5: Scan-Pfade überspringen Lookup bei `EIGEN-`

**Files:**
- Modify: `recipe-assistant/backend/app/routers/inventory.py` (`scan_in` ~Zeile 542, `add_item_by_barcode` ~Zeile 346)
- Test: `recipe-assistant/backend/tests/test_inventory_custom.py`

- [ ] **Step 1: Write the failing test**

An `tests/test_inventory_custom.py` anhängen:

```python
async def test_scan_in_existing_custom_product_increments_without_lookup(client):
    created = (await client.post("/api/inventory/custom", json={"name": "Banane"})).json()
    barcode = created["barcode"]

    resp = await client.post("/api/inventory/scan-in", json={"barcode": barcode})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["name"] == "Banane"  # NOT "Testprodukt" from the mock lookup
    assert data["quantity"] == 1


async def test_scan_in_unknown_custom_barcode_errors(client):
    resp = await client.post(
        "/api/inventory/scan-in", json={"barcode": "EIGEN-DEADBEEF0000"}
    )
    assert resp.status_code == 404
    assert resp.json()["status"] == "unknown_custom_product"


async def test_add_by_barcode_unknown_custom_errors(client):
    resp = await client.post(
        "/api/inventory/barcode", json={"barcode": "EIGEN-DEADBEEF0000"}
    )
    assert resp.status_code == 404
```

> Der autouse-Mock (`conftest.py:36`) lässt `lookup_barcode` `{"name": "Testprodukt", ...}` zurückgeben. Wenn der Skip greift, bleibt der Name „Banane".

- [ ] **Step 2: Run test to verify it fails**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_custom.py -v -k "custom"`
Expected: FAIL (`test_scan_in_unknown_custom_barcode_errors`: 404 vs 200, da aktuell ein neues Item via Lookup angelegt wird)

- [ ] **Step 3: Patch the not-existing branch in `scan_in`**

In `recipe-assistant/backend/app/routers/inventory.py`, in `scan_in`, die „New item"-Stelle (aktuell Zeile 542-545) ersetzen. Vor dem `product = await lookup_barcode(req.barcode)` einfügen:

```python
    # Custom (EIGEN-) products are never auto-created via scan: they must be
    # defined in the UI first. Skip the external lookup entirely.
    if is_custom_barcode(req.barcode):
        return JSONResponse(
            status_code=404,
            content={
                "status": "unknown_custom_product",
                "barcode": req.barcode,
                "error": "Unbekanntes eigenes Produkt — bitte erst anlegen",
            },
        )

    # New item — resolve product details via the normal lookup pipeline.
    product = await lookup_barcode(req.barcode)
```

- [ ] **Step 4: Patch the not-existing branch in `add_item_by_barcode`**

In `add_item_by_barcode`, ganz am Anfang der Funktion (vor `product = await lookup_barcode(req.barcode)`, Zeile 332) einfügen — aber nur greifen, wenn das Item noch nicht existiert. Funktion so umstellen:

```python
@router.post("/barcode", status_code=201)
async def add_item_by_barcode(
    req: BarcodeAddRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == req.barcode)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity += 1
        await _log_action(db, req.barcode, "add", f"quantity: {existing.quantity - 1} → {existing.quantity}")
        await db.commit()
        return {"message": f'Produkt "{existing.name}" existierte bereits. Menge um 1 erhöht.'}

    if is_custom_barcode(req.barcode):
        raise HTTPException(
            status_code=404,
            detail="Unbekanntes eigenes Produkt — bitte erst anlegen",
        )

    product = await lookup_barcode(req.barcode)
    location_id = await _resolve_storage_location(db, req.storage_location)

    item = InventoryItem(
        barcode=req.barcode,
        name=product["name"],
        quantity=1,
        category=product["category"],
        image_url=product.get("image_url"),
        storage_location_id=location_id,
        expiration_date=req.expiration_date,
    )
    db.add(item)
    await _log_action(db, req.barcode, "add")
    await db.commit()
    return {"message": f'Artikel "{product["name"]}" hinzugefügt!'}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_custom.py -v`
Expected: PASS (alle)

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/app/routers/inventory.py recipe-assistant/backend/tests/test_inventory_custom.py
git commit -m "feat: skip barcode lookup for EIGEN- products, error on unknown"
```

---

## Task 6: Eigene Produkte bei Menge 0 als Zombie behalten

**Files:**
- Modify: `recipe-assistant/backend/app/routers/inventory.py` (`_apply_decrement`, Zeile 83-103)
- Test: `recipe-assistant/backend/tests/test_inventory_custom.py`

- [ ] **Step 1: Write the failing test**

An `tests/test_inventory_custom.py` anhängen:

```python
async def test_custom_product_kept_as_zombie_at_zero(client):
    created = (await client.post("/api/inventory/custom", json={"name": "Banane", "quantity": 1})).json()
    barcode = created["barcode"]

    resp = await client.post("/api/inventory/scan-out", json={"barcode": barcode})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is False
    assert resp.json()["remaining_quantity"] == 0

    listing = await client.get("/api/inventory/")
    assert any(i["barcode"] == barcode for i in listing.json())


async def test_real_product_still_deleted_at_zero(client):
    await client.post("/api/inventory/barcode", json={"barcode": "1234567890123"})
    resp = await client.post("/api/inventory/scan-out", json={"barcode": "1234567890123"})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_custom.py -v -k zombie`
Expected: FAIL (`deleted` ist True, da eigenes Produkt aktuell gelöscht wird)

- [ ] **Step 3: Patch the delete condition**

In `_apply_decrement` die Bedingung (Zeile 89) ändern:

```python
    if new_quantity <= 0 and tracked is None and not is_custom_barcode(item.barcode):
        await _log_action(db, item.barcode, action, log_details)
        await db.delete(item)
        return True
```

> `check_and_enqueue` läuft danach mit `tracked=None` weiter (Zeile 96) — das ist ein No-op ohne Tracking-Regel, also unschädlich für eigene Produkte.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_custom.py -v`
Expected: PASS (alle)

- [ ] **Step 5: Run the full restock regression suite (Zombie-Logik berührt)**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_restock.py tests/test_restock.py -v`
Expected: PASS (keine Regression bei der bestehenden Tracking-Zombie-Logik)

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/app/routers/inventory.py recipe-assistant/backend/tests/test_inventory_custom.py
git commit -m "feat: keep custom (EIGEN-) products as zombie rows at quantity 0"
```

---

## Task 7: `include_in_sheet` über Update-Endpoint umschaltbar

**Files:**
- Modify: `recipe-assistant/backend/app/routers/inventory.py` (`update_item`, Zeile 571-615)
- Test: `recipe-assistant/backend/tests/test_inventory_custom.py`

- [ ] **Step 1: Write the failing test**

An `tests/test_inventory_custom.py` anhängen:

```python
async def test_toggle_include_in_sheet(client):
    await client.post("/api/inventory/barcode", json={"barcode": "1234567890123"})

    resp = await client.put(
        "/api/inventory/1234567890123", json={"include_in_sheet": True}
    )
    assert resp.status_code == 200

    listing = await client.get("/api/inventory/")
    item = next(i for i in listing.json() if i["barcode"] == "1234567890123")
    assert item["include_in_sheet"] is True

    await client.put("/api/inventory/1234567890123", json={"include_in_sheet": False})
    listing = await client.get("/api/inventory/")
    item = next(i for i in listing.json() if i["barcode"] == "1234567890123")
    assert item["include_in_sheet"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_custom.py -v -k include_in_sheet`
Expected: FAIL (`include_in_sheet` bleibt False / KeyError)

- [ ] **Step 3: Handle the field in update_item**

In `update_item`, vor `await db.commit()` (Zeile 614) einfügen:

```python
    if req.include_in_sheet is not None:
        item.include_in_sheet = req.include_in_sheet
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd recipe-assistant/backend && pytest tests/test_inventory_custom.py -v -k include_in_sheet`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/routers/inventory.py recipe-assistant/backend/tests/test_inventory_custom.py
git commit -m "feat: allow toggling include_in_sheet via update endpoint"
```

---

## Task 8: reportlab-Dependency + PDF-Render-Service + Endpoint

**Files:**
- Modify: `recipe-assistant/backend/pyproject.toml:8-22`
- Create: `recipe-assistant/backend/app/services/barcode_sheet.py`
- Modify: `recipe-assistant/backend/app/routers/inventory.py`
- Test: `recipe-assistant/backend/tests/test_barcode_sheet.py`

- [ ] **Step 1: Add reportlab dependency**

In `recipe-assistant/backend/pyproject.toml`, in der `dependencies`-Liste (nach `"rapidfuzz>=3.10.0",`, Zeile 21) ergänzen:

```python
    "reportlab>=4.2.0",
```

- [ ] **Step 2: Install it**

Run: `cd recipe-assistant/backend && pip install -e .[dev]`
Expected: reportlab wird installiert, kein Fehler

- [ ] **Step 3: Write the failing test**

```python
# recipe-assistant/backend/tests/test_barcode_sheet.py
from app.services.barcode_sheet import render_barcode_sheet


def test_render_returns_pdf_bytes():
    pdf = render_barcode_sheet([("EIGEN-ABC123", "Banane"), ("4006381333931", "Pizza")])
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


def test_render_empty_selection_still_returns_pdf():
    pdf = render_barcode_sheet([])
    assert pdf[:4] == b"%PDF"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd recipe-assistant/backend && pytest tests/test_barcode_sheet.py -v`
Expected: FAIL (ModuleNotFoundError: app.services.barcode_sheet)

- [ ] **Step 5: Write the PDF render service**

```python
# recipe-assistant/backend/app/services/barcode_sheet.py
"""Render a printable A4 sheet of Code128 barcodes for inventory items.

Used for products whose packaging (and barcode) gets thrown away, e.g. loose
fruit defined as custom EIGEN- products, or a pizza box. Print the sheet, stick
the codes near the fridge, scan to add/remove.
"""

from __future__ import annotations

import io

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

COLS = 3
ROWS = 8
MARGIN = 12 * mm


def render_barcode_sheet(items: list[tuple[str, str]]) -> bytes:
    """Render ``items`` (list of ``(barcode, name)``) to an A4 PDF.

    Each cell holds one Code128 barcode with the product name beneath it.
    An empty selection yields a single page with an explanatory note so the
    download never looks broken.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    if not items:
        c.setFont("Helvetica", 12)
        c.drawCentredString(
            page_w / 2, page_h / 2,
            "Keine Produkte für das Barcode-Blatt ausgewählt.",
        )
        c.showPage()
        c.save()
        return buf.getvalue()

    cell_w = (page_w - 2 * MARGIN) / COLS
    cell_h = (page_h - 2 * MARGIN) / ROWS
    per_page = COLS * ROWS

    for index, (barcode, name) in enumerate(items):
        pos = index % per_page
        if index > 0 and pos == 0:
            c.showPage()
        col = pos % COLS
        row = pos // COLS
        x = MARGIN + col * cell_w
        y_top = page_h - MARGIN - row * cell_h

        bc = code128.Code128(barcode, barHeight=12 * mm, barWidth=0.4 * mm)
        bc_x = x + (cell_w - bc.width) / 2
        bc_y = y_top - 16 * mm
        bc.drawOn(c, bc_x, bc_y)

        c.setFont("Helvetica", 9)
        label = name if len(name) <= 28 else name[:27] + "…"
        c.drawCentredString(x + cell_w / 2, bc_y - 5 * mm, label)

    c.showPage()
    c.save()
    return buf.getvalue()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd recipe-assistant/backend && pytest tests/test_barcode_sheet.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Write the failing endpoint test**

An `tests/test_barcode_sheet.py` anhängen:

```python
async def test_barcode_sheet_endpoint_returns_pdf(client):
    await client.post("/api/inventory/custom", json={"name": "Banane"})
    listing = await client.get("/api/inventory/")
    barcode = listing.json()[0]["barcode"]
    await client.put(f"/api/inventory/{barcode}", json={"include_in_sheet": True})

    resp = await client.get("/api/inventory/barcode-sheet.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


async def test_barcode_sheet_endpoint_empty_is_ok(client):
    resp = await client.get("/api/inventory/barcode-sheet.pdf")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
```

- [ ] **Step 8: Run test to verify it fails**

Run: `cd recipe-assistant/backend && pytest tests/test_barcode_sheet.py -v -k endpoint`
Expected: FAIL (404 — Endpoint fehlt)

- [ ] **Step 9: Add the endpoint**

In `recipe-assistant/backend/app/routers/inventory.py`:

Import für `Response` ergänzen (Zeile 8, neben `JSONResponse`):

```python
from fastapi.responses import JSONResponse, Response
```

Render-Import nach Zeile 31:

```python
from app.services.barcode_sheet import render_barcode_sheet
```

Endpoint direkt nach `get_inventory` (vor `@router.post("/barcode", ...)`) einfügen:

```python
@router.get("/barcode-sheet.pdf")
async def barcode_sheet(db: AsyncSession = Depends(get_db)):
    """Return a printable A4 PDF of Code128 barcodes for flagged items."""
    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.include_in_sheet.is_(True))
        .order_by(InventoryItem.name)
    )
    items = result.scalars().all()
    pdf = render_barcode_sheet([(i.barcode, i.name) for i in items])
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=barcode-blatt.pdf"},
    )
```

> Platzierung: `GET /barcode-sheet.pdf` muss vor der dynamischen Route `PUT /{barcode}` stehen ist hier irrelevant (andere HTTP-Methode), aber ein evtl. künftiges `GET /{barcode}` würde kollidieren — daher früh im Router platzieren.

- [ ] **Step 10: Run test to verify it passes**

Run: `cd recipe-assistant/backend && pytest tests/test_barcode_sheet.py -v`
Expected: PASS (alle)

- [ ] **Step 11: Commit**

```bash
git add recipe-assistant/backend/pyproject.toml recipe-assistant/backend/app/services/barcode_sheet.py recipe-assistant/backend/app/routers/inventory.py recipe-assistant/backend/tests/test_barcode_sheet.py
git commit -m "feat: add A4 barcode sheet PDF endpoint (reportlab)"
```

---

## Task 9: Alembic-Migration für `include_in_sheet`

**Files:**
- Create: `recipe-assistant/backend/alembic/versions/010_add_include_in_sheet.py`

- [ ] **Step 1: Write the migration**

```python
# recipe-assistant/backend/alembic/versions/010_add_include_in_sheet.py
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory",
        sa.Column(
            "include_in_sheet",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("inventory", "include_in_sheet")
```

- [ ] **Step 2: Verify migration chain is intact**

Run: `cd recipe-assistant/backend && python -c "import alembic.versions.010_add_include_in_sheet as m; assert m.down_revision == '009'; print('chain ok')"`
Expected: `chain ok`

> Hinweis: Modul-Import via Punkt-Pfad scheitert ggf. an `010` als Zahl-Präfix. Alternative Verifikation: `grep -n "revision\|down_revision" alembic/versions/010_add_include_in_sheet.py` und prüfen, dass `revision="010"`, `down_revision="009"`.

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/alembic/versions/010_add_include_in_sheet.py
git commit -m "feat: alembic migration for include_in_sheet column"
```

---

## Task 10: Frontend — Typen + API-Client + Hook

**Files:**
- Modify: `recipe-assistant/frontend/src/types/index.ts:6-17`
- Modify: `recipe-assistant/frontend/src/api/client.ts`
- Modify: `recipe-assistant/frontend/src/hooks/useInventory.ts`

- [ ] **Step 1: Add include_in_sheet to InventoryItem type**

In `src/types/index.ts`, in `interface InventoryItem` (nach Zeile 14 `image_url: string | null;`) ergänzen:

```typescript
  include_in_sheet: boolean;
```

- [ ] **Step 2: Extend updateItem and add new API functions**

In `src/api/client.ts`, `updateItem` (Zeile 86-94) um `include_in_sheet` erweitern:

```typescript
export const updateItem = (barcode: string, data: {
  quantity?: number;
  storage_location?: string;
  expiration_date?: string;
  include_in_sheet?: boolean;
}) =>
  request<{ message: string }>(`/inventory/${barcode}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
```

Nach `updateItem` (vor `deleteItem`, Zeile 96) einfügen:

```typescript
export const createCustomProduct = (data: {
  name: string;
  category?: string;
  storage_location?: string;
  quantity?: number;
}) =>
  request<InventoryItem>("/inventory/custom", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const barcodeSheetUrl = () => `${BASE}/inventory/barcode-sheet.pdf`;
```

- [ ] **Step 3: Add createCustom to useInventory hook**

In `src/hooks/useInventory.ts`:

Import erweitern (Zeile 3-9):

```typescript
import {
  getInventory,
  updateItem,
  deleteItem,
  addItemByBarcode,
  removeItemByBarcode,
  createCustomProduct,
} from "../api/client";
```

Neue Funktion vor dem `return` (Zeile 70) einfügen:

```typescript
  const createCustom = async (data: Parameters<typeof createCustomProduct>[0]) => {
    const result = await createCustomProduct(data);
    await fetch();
    return result;
  };
```

Und ins return-Objekt aufnehmen:

```typescript
  return { items, loading, error, refetch: fetch, add, remove, update, delete: del, createCustom };
```

- [ ] **Step 4: Typecheck**

Run: `cd recipe-assistant/frontend && npx tsc --noEmit`
Expected: keine Fehler

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/types/index.ts recipe-assistant/frontend/src/api/client.ts recipe-assistant/frontend/src/hooks/useInventory.ts
git commit -m "feat: frontend types/api/hook for custom products and barcode sheet"
```

---

## Task 11: Frontend — InventoryPage (Dialog, „auf PDF"-Spalte, Download)

**Files:**
- Modify: `recipe-assistant/frontend/src/pages/InventoryPage.tsx`

- [ ] **Step 1: Add imports**

In `src/pages/InventoryPage.tsx`:

MUI-Imports (Zeile 3-17) um Dialog-Komponenten und Checkbox erweitern:

```typescript
import {
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
```

Icon und API-Helper (nach Zeile 22):

```typescript
import PrintIcon from "@mui/icons-material/Print";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
```

API-Import (Zeile 26) um `barcodeSheetUrl` ergänzen:

```typescript
import { exportData, importData, relookupBarcode, relookupAllUnknown, backfillImages, barcodeSheetUrl } from "../api/client";
```

- [ ] **Step 2: Add custom-product dialog state and handlers**

Nach den `trackedForm`-States (nach Zeile 69) einfügen:

```typescript
  const [customOpen, setCustomOpen] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customCategory, setCustomCategory] = useState("");
  const [customLocation, setCustomLocation] = useState("");

  const handleCreateCustom = async () => {
    if (!customName.trim()) return;
    try {
      await inventory.createCustom({
        name: customName.trim(),
        category: customCategory.trim() || undefined,
        storage_location: customLocation.trim() || undefined,
      });
      notify(`Eigenes Produkt "${customName.trim()}" angelegt`, "success");
      setCustomOpen(false);
      setCustomName("");
      setCustomCategory("");
      setCustomLocation("");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Anlegen", "error");
    }
  };

  const handleToggleSheet = async (barcode: string, value: boolean) => {
    try {
      await inventory.update(barcode, { include_in_sheet: value });
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };
```

- [ ] **Step 3: Add toolbar buttons**

In der Button-`Box` (nach dem Import-`<input>`, vor dem `relookupAll`-Button, ~Zeile 244) einfügen:

```tsx
        <Button
          variant="outlined"
          size="small"
          startIcon={<AddCircleOutlineIcon />}
          onClick={() => setCustomOpen(true)}
        >
          Eigenes Produkt anlegen
        </Button>
        <Button
          variant="outlined"
          size="small"
          startIcon={<PrintIcon />}
          component="a"
          href={barcodeSheetUrl()}
          target="_blank"
          rel="noopener"
        >
          Barcode-Blatt herunterladen
        </Button>
```

- [ ] **Step 4: Add "auf PDF" column header**

In `<TableHead>`, nach `<TableCell>Ablaufdatum</TableCell>` (Zeile 301) einfügen:

```tsx
              <TableCell>Auf PDF</TableCell>
```

- [ ] **Step 5: Add "auf PDF" checkbox cell**

In `<TableBody>`, in der Zeile nach der Ablaufdatum-`<TableCell>` (nach Zeile 391, vor der Aktionen-Zelle) einfügen:

```tsx
                <TableCell>
                  <Checkbox
                    checked={item.include_in_sheet}
                    onChange={(e) => handleToggleSheet(item.barcode, e.target.checked)}
                  />
                </TableCell>
```

- [ ] **Step 6: Fix empty-state colSpan**

Die Empty-State-Zeile (Zeile 427) `colSpan={8}` auf `colSpan={9}` erhöhen (eine Spalte mehr):

```tsx
                <TableCell colSpan={9} align="center">
```

- [ ] **Step 7: Add the custom-product dialog**

Vor `<TrackedProductForm` (Zeile 435) einfügen:

```tsx
      <Dialog open={customOpen} onClose={() => setCustomOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Eigenes Produkt anlegen</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            label="Name"
            fullWidth
            margin="normal"
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
          />
          <TextField
            label="Kategorie (optional)"
            fullWidth
            margin="normal"
            value={customCategory}
            onChange={(e) => setCustomCategory(e.target.value)}
          />
          <TextField
            label="Lagerort (optional)"
            fullWidth
            margin="normal"
            value={customLocation}
            onChange={(e) => setCustomLocation(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCustomOpen(false)}>Abbrechen</Button>
          <Button variant="contained" onClick={handleCreateCustom} disabled={!customName.trim()}>
            Anlegen
          </Button>
        </DialogActions>
      </Dialog>
```

- [ ] **Step 8: Typecheck and build**

Run: `cd recipe-assistant/frontend && npx tsc --noEmit && npm run build`
Expected: build erfolgreich, keine TS-Fehler

- [ ] **Step 9: Commit**

```bash
git add recipe-assistant/frontend/src/pages/InventoryPage.tsx
git commit -m "feat: inventory page custom-product dialog, sheet toggle, download"
```

---

## Task 12: Voller Backend-Testlauf + Versions-Bump

**Files:**
- Modify: `recipe-assistant/config.json` (Versions-Bump — Projektkonvention)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd recipe-assistant/backend && pytest -v`
Expected: alle Tests grün (inkl. bestehende restock/inventory-Tests)

- [ ] **Step 2: Bump the add-on version**

In `recipe-assistant/config.json` die `version` inkrementieren (Projektregel: Version nach jeder Implementierung erhöhen, vor Push).

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/config.json
git commit -m "chore: bump version for custom products + barcode sheet"
```

---

## Self-Review

**Spec coverage:**
- Eigene Produkte anlegen ohne Lookup, auto-`EIGEN-`-Barcode → Task 1, 4 ✅
- Scan überspringt Lookup bei `EIGEN-`, Fehler bei unbekanntem Code → Task 5 ✅
- Eigene Produkte bei Menge 0 als Zombie behalten; echte (nur geflaggte) wie bisher → Task 6 ✅
- `include_in_sheet`-Spalte + Toggle → Task 2, 3, 7, 9 ✅
- A4-PDF mit Code128 (reportlab), nur geflaggte Items, leere Auswahl ok → Task 8 ✅
- Frontend: Dialog, „auf PDF"-Toggle, Download-Button → Task 10, 11 ✅
- Versions-Bump (Projektregel) → Task 12 ✅

**Placeholder scan:** keine TBD/TODO; jeder Code-Step enthält vollständigen Code. ✅

**Type consistency:** `is_custom_barcode`/`make_custom_barcode`/`CUSTOM_BARCODE_PREFIX` (Task 1) konsistent in Task 4/5/6 verwendet. `include_in_sheet` konsistent in Model (Task 2), Schema (Task 3), Update (Task 7), Response, Frontend-Typ (Task 10), UI (Task 11). `createCustomProduct`/`createCustom`/`barcodeSheetUrl` konsistent zwischen client.ts (Task 10) und Hook/Page (Task 10/11). ✅

**Hinweis Task 5:** Die volle Ersetzung von `add_item_by_barcode` wiederholt den bestehenden Code bewusst (DRY innerhalb der Funktion gewahrt; der Einschub ist nur die `is_custom_barcode`-Wache).
