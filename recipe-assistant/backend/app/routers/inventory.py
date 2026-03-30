from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
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
