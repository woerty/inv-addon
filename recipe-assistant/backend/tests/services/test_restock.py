from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.services.restock import check_and_enqueue
from tests.conftest import TestingSessionLocal
from tests.fixtures.picnic.fake_client import FakePicnicClient


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    # Test isolation is handled by the autouse setup_db fixture in
    # conftest.py, which drops/recreates all tables between tests.
    async with TestingSessionLocal() as session:
        yield session


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


async def test_no_tracked_rule_returns_none(db: AsyncSession):
    result = await check_and_enqueue(db, barcode="no-such", new_quantity=0)
    assert result is None


async def test_quantity_at_or_above_min_returns_none(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", min_quantity=2, target_quantity=5)
    result = await check_and_enqueue(db, barcode="b1", new_quantity=2)
    assert result is None


async def test_no_picnic_client_returns_none(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", min_quantity=2, target_quantity=5)
    result = await check_and_enqueue(
        db, barcode="b1", new_quantity=1, picnic_client=None
    )
    assert result is None


async def test_below_threshold_adds_to_picnic_cart(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()

    result = await check_and_enqueue(
        db, barcode="b1", new_quantity=1, picnic_client=client
    )

    assert result is not None
    assert result.barcode == "b1"
    assert result.added_quantity == 4  # target=5 - current=1
    assert client.added_products == [("s100", 4)]


async def test_below_threshold_with_zero_fills_to_target(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()

    result = await check_and_enqueue(
        db, barcode="b1", new_quantity=0, picnic_client=client
    )

    assert result is not None
    assert result.added_quantity == 5
    assert client.added_products == [("s100", 5)]


async def test_below_threshold_deducts_cart_quantity(db: AsyncSession):
    """If 1 item is already in the cart, only add the delta."""
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()
    client.cart_items["s100"] = 1  # 1 already in cart

    result = await check_and_enqueue(
        db, barcode="b1", new_quantity=0, picnic_client=client
    )

    assert result is not None
    # needed=5, already_in_cart=1, delta=4
    assert result.added_quantity == 4
    assert client.added_products == [("s100", 4)]


async def test_below_threshold_skips_if_enough_in_cart(db: AsyncSession):
    """Returns None if the cart already has enough."""
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()
    client.cart_items["s100"] = 5  # already at target

    result = await check_and_enqueue(
        db, barcode="b1", new_quantity=0, picnic_client=client
    )

    assert result is None
    assert client.added_products == []


async def test_restock_writes_inventory_log(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()

    await check_and_enqueue(db, barcode="b1", new_quantity=1, picnic_client=client)

    logs = (
        await db.execute(
            select(InventoryLog).where(InventoryLog.barcode == "b1")
        )
    ).scalars().all()
    assert any(log.action == "restock_auto" for log in logs)
