"""Integration tests for the restock trigger firing through inventory
decrement paths. Covers scan-out, /remove, and PUT /{barcode} (manual
quantity edit). Each test seeds a TrackedProduct directly in the DB
because the /api/tracked-products/* router is added in a later task.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.inventory import InventoryItem
from app.models.picnic import ShoppingListItem
from app.models.tracked_product import TrackedProduct
from tests.conftest import TestingSessionLocal


async def _seed(*, barcode: str, quantity: int, tracked: bool = True) -> None:
    async with TestingSessionLocal() as session:
        session.add(InventoryItem(barcode=barcode, name="Milch", quantity=quantity))
        if tracked:
            session.add(
                TrackedProduct(
                    barcode=barcode,
                    picnic_id="s100",
                    name="Ja! Vollmilch 1 L",
                    min_quantity=2,
                    target_quantity=5,
                )
            )
        await session.commit()


async def _shopping_list_entries(barcode: str) -> list[ShoppingListItem]:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(ShoppingListItem).where(
                ShoppingListItem.inventory_barcode == barcode
            )
        )
        return list(result.scalars().all())


async def _inventory_row(barcode: str) -> InventoryItem | None:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(InventoryItem).where(InventoryItem.barcode == barcode)
        )
        return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_scan_out_below_threshold_seeds_shopping_list(client: AsyncClient):
    await _seed(barcode="b1", quantity=3)

    response = await client.post("/api/inventory/scan-out", json={"barcode": "b1"})
    assert response.status_code == 200
    assert response.json()["remaining_quantity"] == 2

    # qty=2 == min_quantity; should NOT fire
    assert await _shopping_list_entries("b1") == []

    response = await client.post("/api/inventory/scan-out", json={"barcode": "b1"})
    assert response.json()["remaining_quantity"] == 1
    entries = await _shopping_list_entries("b1")
    assert len(entries) == 1
    assert entries[0].quantity == 4  # target=5 - current=1


@pytest.mark.asyncio
async def test_scan_out_last_item_keeps_zombie_row_when_tracked(client: AsyncClient):
    await _seed(barcode="b1", quantity=1)

    response = await client.post("/api/inventory/scan-out", json={"barcode": "b1"})
    assert response.status_code == 200
    assert response.json()["remaining_quantity"] == 0
    assert response.json()["deleted"] is False  # new rule: tracked → keep row

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 0

    entries = await _shopping_list_entries("b1")
    assert len(entries) == 1
    assert entries[0].quantity == 5  # full target, since new_qty=0


@pytest.mark.asyncio
async def test_scan_out_last_item_still_deletes_when_not_tracked(client: AsyncClient):
    await _seed(barcode="b2", quantity=1, tracked=False)

    response = await client.post("/api/inventory/scan-out", json={"barcode": "b2"})
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    assert await _inventory_row("b2") is None
    assert await _shopping_list_entries("b2") == []


@pytest.mark.asyncio
async def test_repeated_scan_out_raises_quantity_no_duplicates(client: AsyncClient):
    await _seed(barcode="b1", quantity=3)

    await client.post("/api/inventory/scan-out", json={"barcode": "b1"})  # 3→2, no fire
    await client.post("/api/inventory/scan-out", json={"barcode": "b1"})  # 2→1, fires, needed=4
    await client.post("/api/inventory/scan-out", json={"barcode": "b1"})  # 1→0, fires, needed=5

    entries = await _shopping_list_entries("b1")
    assert len(entries) == 1
    assert entries[0].quantity == 5


@pytest.mark.asyncio
async def test_remove_endpoint_fires_trigger(client: AsyncClient):
    await _seed(barcode="b1", quantity=2)  # qty=2 == min, still ok

    response = await client.post("/api/inventory/remove", json={"barcode": "b1"})
    assert response.status_code == 200

    entries = await _shopping_list_entries("b1")
    assert len(entries) == 1
    assert entries[0].quantity == 4  # target=5 - current=1


@pytest.mark.asyncio
async def test_remove_last_item_keeps_zombie_when_tracked(client: AsyncClient):
    await _seed(barcode="b1", quantity=1)

    response = await client.post("/api/inventory/remove", json={"barcode": "b1"})
    assert response.status_code == 200

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 0
    entries = await _shopping_list_entries("b1")
    assert entries[0].quantity == 5


@pytest.mark.asyncio
async def test_put_quantity_edit_below_threshold_fires(client: AsyncClient):
    await _seed(barcode="b1", quantity=5)

    response = await client.put("/api/inventory/b1", json={"quantity": 1})
    assert response.status_code == 200

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 1
    entries = await _shopping_list_entries("b1")
    assert entries[0].quantity == 4


@pytest.mark.asyncio
async def test_put_quantity_to_zero_keeps_zombie_when_tracked(client: AsyncClient):
    await _seed(barcode="b1", quantity=5)

    response = await client.put("/api/inventory/b1", json={"quantity": 0})
    assert response.status_code == 200

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 0
    entries = await _shopping_list_entries("b1")
    assert entries[0].quantity == 5


@pytest.mark.asyncio
async def test_put_quantity_increase_does_not_fire(client: AsyncClient):
    await _seed(barcode="b1", quantity=3)

    response = await client.put("/api/inventory/b1", json={"quantity": 10})
    assert response.status_code == 200

    assert await _shopping_list_entries("b1") == []


@pytest.mark.asyncio
async def test_scan_in_into_zombie_does_not_prune_shopping_list(client: AsyncClient):
    await _seed(barcode="b1", quantity=1)
    # Trigger a zombie
    await client.post("/api/inventory/scan-out", json={"barcode": "b1"})
    entries_before = await _shopping_list_entries("b1")
    assert entries_before[0].quantity == 5

    # Scan back in — inventory row revives, shopping list unchanged
    response = await client.post(
        "/api/inventory/scan-in", json={"barcode": "b1", "storage_location_id": None}
    )
    assert response.status_code == 200

    row = await _inventory_row("b1")
    assert row is not None
    assert row.quantity == 1  # zombie revived, not recreated
    entries_after = await _shopping_list_entries("b1")
    assert len(entries_after) == 1
    assert entries_after[0].quantity == 5  # unchanged, add-only semantics
