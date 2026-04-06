from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.database import get_db
from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.person import Person
from app.models.picnic import PicnicProduct
from app.models.tracked_product import TrackedProduct
from app.schemas.inventory import (
    BarcodeAddRequest,
    BarcodeRemoveRequest,
    InventoryItemResponse,
    InventoryUpdateRequest,
    ScanInRequest,
    ScanOutRequest,
)
from app.services.barcode import lookup_barcode
from app.services.restock import check_and_enqueue

router = APIRouter()


async def _log_action(db: AsyncSession, barcode: str, action: str, details: str | None = None) -> None:
    db.add(InventoryLog(barcode=barcode, action=action, details=details))


async def _resolve_storage_location(db: AsyncSession, name: str | None) -> int | None:
    if not name:
        return None
    result = await db.execute(select(StorageLocation).where(StorageLocation.name == name))
    location = result.scalar_one_or_none()
    if location:
        return location.id
    new_loc = StorageLocation(name=name)
    db.add(new_loc)
    await db.flush()
    return new_loc.id


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
    - Runs restock.check_and_enqueue when the row is kept (may upsert a
      ShoppingListItem in the same transaction); skipped on the delete
      branch because there is no tracked rule to check against.
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
    await check_and_enqueue(
        db, barcode=item.barcode, new_quantity=new_quantity, tracked=tracked
    )
    return False


@router.get("/", response_model=list[InventoryItemResponse])
async def get_inventory(
    search: str | None = None,
    sort_by: str = "name",
    order: str = "asc",
    db: AsyncSession = Depends(get_db),
):
    query = select(InventoryItem).options(selectinload(InventoryItem.storage_location))

    if search:
        query = query.where(
            InventoryItem.name.ilike(f"%{search}%")
            | InventoryItem.category.ilike(f"%{search}%")
        )

    allowed_sort = {"name", "quantity", "category", "added_date", "barcode"}
    if sort_by in allowed_sort:
        col = getattr(InventoryItem, sort_by)
        query = query.order_by(col.desc() if order == "desc" else col.asc())

    result = await db.execute(query)
    items = result.scalars().all()

    # Enrich with Picnic product images (highest priority).
    barcodes = [i.barcode for i in items]
    picnic_image_map: dict[str, str] = {}
    if barcodes:
        pp_rows = (
            await db.execute(
                select(PicnicProduct.ean, PicnicProduct.image_id)
                .where(PicnicProduct.ean.in_(barcodes))
                .where(PicnicProduct.image_id.isnot(None))
            )
        ).all()
        picnic_image_map = {
            row.ean: f"https://storefront-prod.de.picnicinternational.com/static/images/{row.image_id}/small.png"
            for row in pp_rows
        }

    # Build final image_url: Picnic CDN > stored image_url from barcode lookup.
    for item in items:
        picnic_url = picnic_image_map.get(item.barcode)
        if picnic_url:
            item.image_url = picnic_url  # Picnic wins
        # else: item.image_url is already set from the DB column (OFF, etc.)

    return items


@router.post("/relookup/{barcode}")
async def relookup_barcode(barcode: str, db: AsyncSession = Depends(get_db)):
    """Re-lookup a barcode across all providers and update the item."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == barcode)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"Kein Artikel mit Barcode {barcode} gefunden")

    product = await lookup_barcode(barcode)
    if product["name"] == "Unbekanntes Produkt":
        return {"message": "Kein Ergebnis bei allen Providern gefunden.", "updated": False}

    old_name = item.name
    item.name = product["name"]
    item.category = product["category"]
    if product.get("image_url") and not item.image_url:
        item.image_url = product["image_url"]
    await _log_action(db, barcode, "update", f"re-lookup: {old_name} → {product['name']}")
    await db.commit()
    return {"message": f'Aktualisiert: "{product["name"]}"', "updated": True}


@router.post("/relookup-all")
async def relookup_all_unknown(db: AsyncSession = Depends(get_db)):
    """Re-lookup all items named 'Unbekanntes Produkt'."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.name == "Unbekanntes Produkt")
    )
    items = result.scalars().all()
    if not items:
        return {"message": "Keine unbekannten Produkte gefunden.", "updated": 0}

    updated = 0
    for item in items:
        product = await lookup_barcode(item.barcode)
        if product["name"] != "Unbekanntes Produkt":
            item.name = product["name"]
            item.category = product["category"]
            if product.get("image_url") and not item.image_url:
                item.image_url = product["image_url"]
            updated += 1

    await db.commit()
    return {"message": f"{updated} von {len(items)} Produkten aktualisiert.", "updated": updated}


@router.post("/barcode", status_code=201)
async def add_item_by_barcode(
    req: BarcodeAddRequest,
    db: AsyncSession = Depends(get_db),
):
    product = await lookup_barcode(req.barcode)
    location_id = await _resolve_storage_location(db, req.storage_location)

    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == req.barcode)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity += 1
        await _log_action(db, req.barcode, "add", f"quantity: {existing.quantity - 1} → {existing.quantity}")
        await db.commit()
        return {"message": f'Produkt "{existing.name}" existierte bereits. Menge um 1 erhöht.'}

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


@router.post("/remove")
async def remove_item_by_barcode(
    req: BarcodeRemoveRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == req.barcode)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"Kein Artikel mit Barcode {req.barcode} gefunden")

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


def _check_scanner_token(
    provided: str | None, configured: str
) -> JSONResponse | None:
    """Return a 401 JSONResponse if the token check fails, else None.

    Matches the scanner API contract's optional shared-secret auth:
    - Empty `configured` → auth is disabled, always passes.
    - Non-empty `configured` → header must match, constant-time comparison.
    """
    if not configured:
        return None
    if not provided or not hmac.compare_digest(provided, configured):
        return JSONResponse(
            status_code=401,
            content={
                "status": "unauthorized",
                "error": "Invalid or missing X-Scanner-Token",
            },
        )
    return None


@router.post("/scan-out")
async def scan_out(
    req: ScanOutRequest,
    x_scanner_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """Decrement inventory by one for a scanned barcode.

    Contract: docs/superpowers/specs/2026-04-05-scanner-api-design.md.
    All response bodies are flat JSON (no FastAPI {"detail": ...} wrapper)
    so remote terminal clients can branch on the `status` field directly.
    """
    auth_fail = _check_scanner_token(x_scanner_token, settings.scanner_token)
    if auth_fail is not None:
        return auth_fail

    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == req.barcode)
    )
    item = result.scalar_one_or_none()
    if not item:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "barcode": req.barcode,
                "error": "Kein Artikel mit diesem Barcode im Inventar",
            },
        )

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


@router.post("/scan-in")
async def scan_in(
    req: ScanInRequest,
    x_scanner_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """Add-by-barcode for scanner clients with structured response.

    Contract: docs/superpowers/specs/2026-04-05-scanner-api-design.md.
    Parallels /scan-out: flat JSON, same auth model. Takes a
    storage_location_id (int, references storage_locations.id) rather
    than a name — scanner clients pick from a cached list, so a typo
    should 400 instead of silently creating a new location.
    """
    auth_fail = _check_scanner_token(x_scanner_token, settings.scanner_token)
    if auth_fail is not None:
        return auth_fail

    # Validate storage_location_id up front so we never mutate state on
    # an invalid request. Unknown id → 400, no side effects.
    requested_location: StorageLocation | None = None
    if req.storage_location_id is not None:
        result = await db.execute(
            select(StorageLocation).where(StorageLocation.id == req.storage_location_id)
        )
        requested_location = result.scalar_one_or_none()
        if requested_location is None:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "invalid_storage_location",
                    "storage_location_id": req.storage_location_id,
                    "error": f"Lagerort mit ID {req.storage_location_id} existiert nicht",
                },
            )

    # Look up existing inventory row (with storage_location eager-loaded
    # so we can echo it in the response without a lazy load).
    result = await db.execute(
        select(InventoryItem)
        .options(selectinload(InventoryItem.storage_location))
        .where(InventoryItem.barcode == req.barcode)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Increment quantity. Existing storage_location is NEVER modified
        # by scan-in — prevents surprise migration from stale scanner-side
        # selection. Response echoes the item's CURRENT location, which
        # may differ from the requested one.
        existing.quantity += 1
        new_qty = existing.quantity
        item_name = existing.name
        loc_data: dict | None = None
        if existing.storage_location is not None:
            loc_data = {
                "id": existing.storage_location.id,
                "name": existing.storage_location.name,
            }
        await _log_action(db, req.barcode, "scan-in", f"qty → {new_qty}")
        await db.commit()
        return {
            "status": "ok",
            "barcode": req.barcode,
            "name": item_name,
            "quantity": new_qty,
            "storage_location": loc_data,
            "created": False,
        }

    # New item — resolve product details via the normal lookup pipeline.
    # Unknown barcodes become "Unbekanntes Produkt" and still return 200;
    # the user can clean them up later via the web UI.
    product = await lookup_barcode(req.barcode)
    item = InventoryItem(
        barcode=req.barcode,
        name=product["name"],
        quantity=1,
        category=product["category"],
        image_url=product.get("image_url"),
        storage_location_id=requested_location.id if requested_location else None,
    )
    db.add(item)
    await _log_action(db, req.barcode, "scan-in", "new item")
    await db.commit()

    loc_response: dict | None = None
    if requested_location is not None:
        loc_response = {"id": requested_location.id, "name": requested_location.name}
    return {
        "status": "ok",
        "barcode": req.barcode,
        "name": product["name"],
        "quantity": 1,
        "storage_location": loc_response,
        "created": True,
    }


@router.put("/{barcode}")
async def update_item(
    barcode: str,
    req: InventoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == barcode)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"Kein Artikel mit Barcode {barcode} gefunden")

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

    if req.storage_location is not None:
        item.storage_location_id = await _resolve_storage_location(db, req.storage_location)

    if req.expiration_date is not None:
        item.expiration_date = req.expiration_date

    await db.commit()
    return {"message": f"Artikel mit Barcode {barcode} aktualisiert."}


@router.delete("/{barcode}")
async def delete_item(
    barcode: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == barcode)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"Kein Artikel mit Barcode {barcode} gefunden")

    await _log_action(db, barcode, "delete")
    await db.delete(item)
    await db.commit()
    return {"message": f"Artikel mit Barcode {barcode} wurde gelöscht."}


@router.get("/export")
async def export_data(db: AsyncSession = Depends(get_db)):
    """Export all inventory data as JSON for backup."""
    items_result = await db.execute(
        select(InventoryItem).options(selectinload(InventoryItem.storage_location))
    )
    items = items_result.scalars().all()

    locations_result = await db.execute(select(StorageLocation))
    locations = locations_result.scalars().all()

    persons_result = await db.execute(select(Person))
    persons = persons_result.scalars().all()

    export = {
        "version": "2.0",
        "inventory": [
            {
                "barcode": item.barcode,
                "name": item.name,
                "quantity": item.quantity,
                "category": item.category,
                "storage_location": item.storage_location.name if item.storage_location else None,
                "expiration_date": item.expiration_date.isoformat() if item.expiration_date else None,
            }
            for item in items
        ],
        "storage_locations": [loc.name for loc in locations],
        "persons": [
            {"name": p.name, "preferences": p.preferences}
            for p in persons
        ],
    }
    return JSONResponse(content=export)


@router.post("/import")
async def import_data(db: AsyncSession = Depends(get_db), file: UploadFile = ...):
    """Import inventory data from JSON backup. Merges with existing data."""
    import json

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Ungültige JSON Datei")

    imported_count = 0

    # Import storage locations
    for loc_name in data.get("storage_locations", []):
        result = await db.execute(select(StorageLocation).where(StorageLocation.name == loc_name))
        if not result.scalar_one_or_none():
            db.add(StorageLocation(name=loc_name))

    await db.flush()

    # Import persons
    for person_data in data.get("persons", []):
        result = await db.execute(select(Person).where(Person.name == person_data["name"]))
        existing = result.scalar_one_or_none()
        if existing:
            existing.preferences = person_data.get("preferences", "")
        else:
            db.add(Person(name=person_data["name"], preferences=person_data.get("preferences", "")))

    # Import inventory items
    for item_data in data.get("inventory", []):
        from datetime import date

        result = await db.execute(
            select(InventoryItem).where(InventoryItem.barcode == item_data["barcode"])
        )
        existing = result.scalar_one_or_none()

        location_id = None
        if item_data.get("storage_location"):
            loc_result = await db.execute(
                select(StorageLocation).where(StorageLocation.name == item_data["storage_location"])
            )
            loc = loc_result.scalar_one_or_none()
            if loc:
                location_id = loc.id

        exp_date = None
        if item_data.get("expiration_date"):
            exp_date = date.fromisoformat(item_data["expiration_date"])

        if existing:
            existing.quantity = item_data.get("quantity", existing.quantity)
            existing.name = item_data.get("name", existing.name)
            existing.category = item_data.get("category", existing.category)
            existing.storage_location_id = location_id
            existing.expiration_date = exp_date
        else:
            db.add(InventoryItem(
                barcode=item_data["barcode"],
                name=item_data.get("name", "Unbekannt"),
                quantity=item_data.get("quantity", 1),
                category=item_data.get("category", "Unbekannt"),
                storage_location_id=location_id,
                expiration_date=exp_date,
            ))
        imported_count += 1

    await db.commit()
    return {"message": f"{imported_count} Artikel importiert."}
