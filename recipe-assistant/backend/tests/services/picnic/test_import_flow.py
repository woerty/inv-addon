import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.inventory import InventoryItem
from app.models.picnic import (
    PicnicDeliveryImport,
    PicnicProduct,
    ShoppingListItem,
)
from app.services.picnic.import_flow import (
    fetch_import_candidates,
    commit_import_decisions,
)
from app.schemas.picnic import ImportDecision
from tests.fixtures.picnic.fake_client import FakePicnicClient

TEST_DB = "sqlite+aiosqlite:///./test_import_flow.db"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def fake_client() -> FakePicnicClient:
    return FakePicnicClient()


@pytest.mark.asyncio
async def test_fetch_returns_candidates_with_fuzzy_match_suggestions(session, fake_client):
    # Pre-existing inventory with a Vollmilch that should fuzzy-match "Ja! Vollmilch 1L"
    session.add(
        InventoryItem(barcode="4014400900057", name="Vollmilch 3,5%", quantity=1, category="Milch")
    )
    await session.commit()

    response = await fetch_import_candidates(session, fake_client)

    assert len(response.deliveries) == 1
    delivery = response.deliveries[0]
    assert delivery.delivery_id == "del-1"
    assert len(delivery.items) == 2
    milk_item = next(i for i in delivery.items if i.picnic_id == "s100")
    assert milk_item.ordered_quantity == 2
    assert milk_item.best_confidence >= 92
    top = milk_item.match_suggestions[0]
    assert top.inventory_barcode == "4014400900057"


@pytest.mark.asyncio
async def test_fetch_skips_already_imported_deliveries(session, fake_client):
    session.add(PicnicDeliveryImport(delivery_id="del-1", item_count=2))
    await session.commit()

    response = await fetch_import_candidates(session, fake_client)
    assert response.deliveries == []


@pytest.mark.asyncio
async def test_fetch_uses_cached_ean_pairing_for_deterministic_match(session, fake_client):
    """When picnic_products has an ean column set (learned from prior cart-sync
    or scan), the import flow short-circuits fuzzy matching for that SKU."""
    # Prior state: picnic_id s100 is already in cache with ean "999"
    session.add(PicnicProduct(picnic_id="s100", ean="999", name="Ja! Vollmilch 1 L"))
    session.add(InventoryItem(barcode="999", name="Milk (ancient mislabel)", quantity=1, category="x"))
    await session.commit()

    response = await fetch_import_candidates(session, fake_client)
    milk_item = next(i for i in response.deliveries[0].items if i.picnic_id == "s100")
    assert milk_item.best_confidence == 100.0
    assert milk_item.match_suggestions[0].inventory_barcode == "999"
    assert "known mapping" in milk_item.match_suggestions[0].reason


@pytest.mark.asyncio
async def test_commit_match_existing_increments_quantity_and_caches_ean(session, fake_client):
    session.add(InventoryItem(barcode="4014400900057", name="Vollmilch 3,5%", quantity=3, category="Milch"))
    await session.commit()

    result = await commit_import_decisions(
        session,
        fake_client,
        delivery_id="del-1",
        decisions=[
            ImportDecision(
                picnic_id="s100",
                action="match_existing",
                target_barcode="4014400900057",
            ),
            ImportDecision(picnic_id="s200", action="skip"),
        ],
    )
    await session.commit()

    from sqlalchemy import select
    row = (await session.execute(
        select(InventoryItem).where(InventoryItem.barcode == "4014400900057")
    )).scalar_one()
    assert row.quantity == 5  # was 3, delivery had 2

    # The match action should have cached the ean on picnic_products.s100
    cached = (await session.execute(
        select(PicnicProduct).where(PicnicProduct.picnic_id == "s100")
    )).scalar_one()
    assert cached.ean == "4014400900057"

    # Dedup record written
    imp = (await session.execute(
        select(PicnicDeliveryImport).where(PicnicDeliveryImport.delivery_id == "del-1")
    )).scalar_one()
    assert imp.item_count == 2  # both decisions counted (match + skip)

    assert result.imported == 1
    assert result.skipped == 1


@pytest.mark.asyncio
async def test_commit_create_new_with_synthetic_barcode(session, fake_client):
    await commit_import_decisions(
        session,
        fake_client,
        delivery_id="del-1",
        decisions=[
            ImportDecision(
                picnic_id="s100",
                action="create_new",
                storage_location="Küche",
            ),
            ImportDecision(picnic_id="s200", action="skip"),
        ],
    )
    await session.commit()

    from sqlalchemy import select
    row = (await session.execute(
        select(InventoryItem).where(InventoryItem.barcode == "picnic:s100")
    )).scalar_one()
    assert row.name == "Ja! Vollmilch 1 L"
    assert row.quantity == 2


@pytest.mark.asyncio
async def test_commit_scanned_ean_during_create_promotes_and_caches(session, fake_client):
    await commit_import_decisions(
        session,
        fake_client,
        delivery_id="del-1",
        decisions=[
            ImportDecision(
                picnic_id="s100",
                action="create_new",
                scanned_ean="4014400900057",
                storage_location="Küche",
            ),
            ImportDecision(picnic_id="s200", action="skip"),
        ],
    )
    await session.commit()

    from sqlalchemy import select
    row = (await session.execute(
        select(InventoryItem).where(InventoryItem.barcode == "4014400900057")
    )).scalar_one()
    assert row.quantity == 2

    cached = (await session.execute(
        select(PicnicProduct).where(PicnicProduct.picnic_id == "s100")
    )).scalar_one()
    assert cached.ean == "4014400900057"


@pytest.mark.asyncio
async def test_commit_idempotent_on_already_imported_delivery(session, fake_client):
    session.add(PicnicDeliveryImport(delivery_id="del-1", item_count=2))
    await session.commit()

    with pytest.raises(ValueError, match="already imported"):
        await commit_import_decisions(
            session,
            fake_client,
            delivery_id="del-1",
            decisions=[],
        )
