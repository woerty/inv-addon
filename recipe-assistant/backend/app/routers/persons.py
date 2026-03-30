from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.person import Person
from app.schemas.person import PersonCreate, PersonResponse, PersonUpdate

router = APIRouter()


@router.get("/", response_model=list[PersonResponse])
async def get_persons(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Person).order_by(Person.name))
    return result.scalars().all()


@router.post("/", response_model=PersonResponse, status_code=201)
async def create_person(req: PersonCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Person).where(Person.name == req.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f'Person "{req.name}" existiert bereits.')

    person = Person(name=req.name, preferences=req.preferences)
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.put("/{person_id}", response_model=PersonResponse)
async def update_person(person_id: int, req: PersonUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Person nicht gefunden")

    if req.name is not None:
        person.name = req.name
    if req.preferences is not None:
        person.preferences = req.preferences

    await db.commit()
    await db.refresh(person)
    return person


@router.delete("/{person_id}")
async def delete_person(person_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Person).where(Person.id == person_id))
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Person nicht gefunden")

    await db.delete(person)
    await db.commit()
    return {"message": f'Person "{person.name}" gelöscht.'}
