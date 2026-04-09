from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.models.picnic import PicnicProduct


async def _seed(client: AsyncClient):
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as db:
        loc = StorageLocation(name="Kühlschrank")
        db.add(loc)
        await db.flush()

        milk = InventoryItem(
            barcode="111", name="Milch", quantity=3, category="Milchprodukte",
            storage_location_id=loc.id, is_pinned=True,
        )
        butter = InventoryItem(
            barcode="222", name="Butter", quantity=1, category="Milchprodukte",
            is_pinned=False,
        )
        db.add_all([milk, butter])

        tp = TrackedProduct(
            barcode="222", picnic_id="p222", name="Butter",
            min_quantity=2, target_quantity=4,
        )
        pp = PicnicProduct(picnic_id="p222", name="Butter", last_price_cents=199)
        db.add_all([tp, pp])

        now = datetime.now(UTC)
        logs = [
            InventoryLog(barcode="111", action="remove", details="quantity: 4 \u2192 3", timestamp=now - timedelta(hours=2)),
            InventoryLog(barcode="222", action="restock_auto", details="qty\u21924, cart delta=2", timestamp=now - timedelta(days=3)),
        ]
        db.add_all(logs)
        await db.commit()


async def test_dashboard_summary(client: AsyncClient):
    await _seed(client)
    resp = await client.get("/api/dashboard/summary?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "pinned_products" in data
    assert "low_stock" in data
    assert "recent_activity" in data
    assert "consumption_trend" in data
    assert "top_consumers" in data
    assert "categories" in data
    assert "restock_costs" in data
    assert "storage_locations" in data
    assert len(data["pinned_products"]) == 1
    assert data["pinned_products"][0]["name"] == "Milch"
    assert len(data["low_stock"]) == 1
    assert data["low_stock"][0]["barcode"] == "222"


async def test_dashboard_product_detail(client: AsyncClient):
    await _seed(client)
    resp = await client.get("/api/dashboard/product/111?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["barcode"] == "111"
    assert data["current_quantity"] == 3
    assert data["stats"]["total_consumed"] == 1


async def test_dashboard_product_not_found(client: AsyncClient):
    resp = await client.get("/api/dashboard/product/nonexistent?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_quantity"] == 0


async def test_dashboard_pin_toggle(client: AsyncClient):
    await _seed(client)
    resp = await client.patch("/api/dashboard/pin/222")
    assert resp.status_code == 200
    assert resp.json()["is_pinned"] is True

    resp = await client.patch("/api/dashboard/pin/222")
    assert resp.status_code == 200
    assert resp.json()["is_pinned"] is False
