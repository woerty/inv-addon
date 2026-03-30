from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.inventory import StorageLocation
from app.schemas.inventory import StorageLocationCreate, StorageLocationResponse

router = APIRouter()


@router.get("/", response_model=list[StorageLocationResponse])
async def get_storage_locations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StorageLocation).order_by(StorageLocation.name))
    return result.scalars().all()


@router.post("/", response_model=StorageLocationResponse, status_code=201)
async def create_storage_location(
    req: StorageLocationCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StorageLocation).where(StorageLocation.name == req.location_name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f'Lagerort "{req.location_name}" existiert bereits.')

    location = StorageLocation(name=req.location_name)
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location


@router.delete("/{location_id}")
async def delete_storage_location(
    location_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StorageLocation).where(StorageLocation.id == location_id)
    )
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Lagerort nicht gefunden")

    await db.delete(location)
    await db.commit()
    return {"message": f'Lagerort "{location.name}" gelöscht.'}
