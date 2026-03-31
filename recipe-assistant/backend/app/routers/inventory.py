from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.person import Person
from app.schemas.inventory import (
    BarcodeAddRequest,
    BarcodeRemoveRequest,
    InventoryItemResponse,
    InventoryUpdateRequest,
)
from app.services.barcode import lookup_barcode

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
    return result.scalars().all()


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

    if item.quantity > 1:
        old_qty = item.quantity
        item.quantity -= 1
        await _log_action(db, req.barcode, "remove", f"quantity: {old_qty} → {item.quantity}")
        await db.commit()
        return {"message": f"Produkt um 1 reduziert. Verbleibend: {item.quantity}"}

    await _log_action(db, req.barcode, "delete", "removed last item")
    await db.delete(item)
    await db.commit()
    return {"message": f"Produkt mit Barcode {req.barcode} wurde entfernt."}


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
        if req.quantity == 0:
            await _log_action(db, barcode, "delete", "quantity set to 0")
            await db.delete(item)
            await db.commit()
            return {"message": f"Artikel mit Barcode {barcode} wurde gelöscht."}
        old_qty = item.quantity
        item.quantity = req.quantity
        await _log_action(db, barcode, "update", f"quantity: {old_qty} → {req.quantity}")

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
