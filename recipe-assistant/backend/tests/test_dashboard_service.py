import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.models.picnic import PicnicProduct
from app.services.dashboard import (
    get_pinned_products,
    get_low_stock,
    get_recent_activity,
    get_consumption_trend,
    get_top_consumers,
    get_category_counts,
    get_restock_costs,
    get_storage_location_counts,
    get_product_detail,
)


async def _seed_basics(db: AsyncSession):
    """Seed inventory items and logs for testing."""
    loc = StorageLocation(name="Kühlschrank")
    db.add(loc)
    await db.flush()

    milk = InventoryItem(
        barcode="111", name="Milch", quantity=3, category="Milchprodukte",
        storage_location_id=loc.id, is_pinned=True,
    )
    butter = InventoryItem(
        barcode="222", name="Butter", quantity=1, category="Milchprodukte",
        storage_location_id=loc.id, is_pinned=False,
    )
    bread = InventoryItem(
        barcode="333", name="Brot", quantity=5, category="Backwaren",
        is_pinned=True,
    )
    db.add_all([milk, butter, bread])
    await db.flush()

    # Tracked product for butter: min=2, so it's low stock (quantity=1)
    tp = TrackedProduct(
        barcode="222", picnic_id="p222", name="Butter",
        min_quantity=2, target_quantity=4,
    )
    db.add(tp)

    # Picnic product for cost lookup
    pp = PicnicProduct(picnic_id="p222", name="Butter", last_price_cents=199)
    db.add(pp)
    await db.flush()

    now = datetime.utcnow()
    logs = [
        InventoryLog(barcode="111", action="remove", details="quantity: 4 → 3", timestamp=now - timedelta(days=1)),
        InventoryLog(barcode="111", action="remove", details="quantity: 5 → 4", timestamp=now - timedelta(days=3)),
        InventoryLog(barcode="111", action="scan-out", details="quantity: 6 → 5", timestamp=now - timedelta(days=5)),
        InventoryLog(barcode="222", action="remove", details="quantity: 2 → 1", timestamp=now - timedelta(days=2)),
        InventoryLog(barcode="222", action="restock_auto", details="qty→4, cart delta=3", timestamp=now - timedelta(days=10)),
        InventoryLog(barcode="333", action="add", details="quantity: 4 → 5", timestamp=now - timedelta(days=1)),
    ]
    db.add_all(logs)
    await db.commit()
    return {"loc": loc, "milk": milk, "butter": butter, "bread": bread}


@pytest.fixture
async def db(setup_db) -> AsyncSession:
    from tests.conftest import TestingSessionLocal
    async with TestingSessionLocal() as session:
        yield session


async def test_get_pinned_products(db: AsyncSession):
    await _seed_basics(db)
    result = await get_pinned_products(db)
    assert len(result) == 2
    names = {p.name for p in result}
    assert names == {"Milch", "Brot"}


async def test_get_low_stock(db: AsyncSession):
    await _seed_basics(db)
    result = await get_low_stock(db)
    assert len(result) == 1
    assert result[0].barcode == "222"
    assert result[0].quantity == 1
    assert result[0].min_quantity == 2


async def test_get_recent_activity(db: AsyncSession):
    await _seed_basics(db)
    result = await get_recent_activity(db, limit=3)
    assert len(result) == 3
    # Most recent first
    assert result[0].barcode in ("111", "333")


async def test_get_consumption_trend(db: AsyncSession):
    await _seed_basics(db)
    result = await get_consumption_trend(db, days=30)
    assert len(result.labels) > 0
    assert len(result.series) > 0
    # Milchprodukte should have consumption data
    dairy = next((s for s in result.series if s.category == "Milchprodukte"), None)
    assert dairy is not None
    assert sum(dairy.data) >= 4  # 3 milk removes + 1 butter remove


async def test_get_top_consumers(db: AsyncSession):
    await _seed_basics(db)
    result = await get_top_consumers(db, days=30)
    assert len(result) >= 2
    # Milch should be top (3 consumption events)
    assert result[0].barcode == "111"
    assert result[0].count == 3


async def test_get_category_counts(db: AsyncSession):
    await _seed_basics(db)
    result = await get_category_counts(db)
    assert len(result) >= 2
    cats = {r.category: r.inventory_count for r in result}
    assert cats["Milchprodukte"] == 2
    assert cats["Backwaren"] == 1


async def test_get_restock_costs(db: AsyncSession):
    await _seed_basics(db)
    result = await get_restock_costs(db, days=30)
    # 1 restock_auto for butter, delta=3, price=199 cents
    assert result.total_cents == 3 * 199


async def test_get_storage_location_counts(db: AsyncSession):
    await _seed_basics(db)
    result = await get_storage_location_counts(db)
    assert len(result) >= 1
    kuehl = next((s for s in result if s.name == "Kühlschrank"), None)
    assert kuehl is not None
    assert kuehl.item_count == 2  # milk + butter


async def test_get_product_detail(db: AsyncSession):
    await _seed_basics(db)
    result = await get_product_detail(db, barcode="111", days=30)
    assert result.barcode == "111"
    assert result.current_quantity == 3
    assert result.stats.total_consumed == 3
    assert len(result.history) >= 3
