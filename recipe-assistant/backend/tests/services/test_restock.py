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
