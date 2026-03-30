import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_inventory_empty(client: AsyncClient):
    response = await client.get("/api/inventory/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_add_item_by_barcode(client: AsyncClient):
    response = await client.post(
        "/api/inventory/barcode",
        json={"barcode": "4014400900057", "storage_location": None},
    )
    assert response.status_code == 201
    data = response.json()
    assert "message" in data


@pytest.mark.asyncio
async def test_add_duplicate_barcode_increments_quantity(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "1234567890123"})
    await client.post("/api/inventory/barcode", json={"barcode": "1234567890123"})
    response = await client.get("/api/inventory/")
    items = response.json()
    matching = [i for i in items if i["barcode"] == "1234567890123"]
    assert len(matching) == 1
    assert matching[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_update_item_quantity(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "1111111111111"})
    response = await client.put("/api/inventory/1111111111111", json={"quantity": 5})
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "1111111111111"]
    assert matching[0]["quantity"] == 5


@pytest.mark.asyncio
async def test_update_quantity_to_zero_deletes(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "2222222222222"})
    response = await client.put("/api/inventory/2222222222222", json={"quantity": 0})
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "2222222222222"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "3333333333333"})
    response = await client.delete("/api/inventory/3333333333333")
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "3333333333333"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_remove_decrements_quantity(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "4444444444444"})
    await client.post("/api/inventory/barcode", json={"barcode": "4444444444444"})
    response = await client.post("/api/inventory/remove", json={"barcode": "4444444444444"})
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "4444444444444"]
    assert matching[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_remove_last_item_deletes(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "5555555555555"})
    response = await client.post("/api/inventory/remove", json={"barcode": "5555555555555"})
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "5555555555555"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client: AsyncClient):
    response = await client.delete("/api/inventory/9999999999999")
    assert response.status_code == 404
