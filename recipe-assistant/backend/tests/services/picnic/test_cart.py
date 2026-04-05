import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.picnic import PicnicProduct, ShoppingListItem
from app.services.picnic.cart import (
    resolve_shopping_list_status,
    sync_shopping_list_to_cart,
)
from tests.fixtures.picnic.fake_client import FakePicnicClient

TEST_DB = "sqlite+aiosqlite:///./test_cart.db"


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
def client():
    return FakePicnicClient()


@pytest.mark.asyncio
async def test_resolve_status_mapped_via_explicit_picnic_id(session, client):
    """Item added with an explicit picnic_id is mapped without any lookup."""
    session.add(ShoppingListItem(name="Milch", quantity=1, picnic_id="s100"))
    await session.commit()

    items = await resolve_shopping_list_status(session, client)
    assert items[0].picnic_status == "mapped"
    assert items[0].picnic_id == "s100"


@pytest.mark.asyncio
async def test_resolve_status_hits_cached_ean_pairing(session, client):
    """Item with inventory_barcode resolves via picnic_products cache (no live lookup)."""
    session.add(PicnicProduct(picnic_id="s100", ean="4014400900057", name="Ja! Vollmilch 1 L"))
    session.add(ShoppingListItem(name="Milch", quantity=1, inventory_barcode="4014400900057"))
    await session.commit()

    items = await resolve_shopping_list_status(session, client)
    assert items[0].picnic_status == "mapped"
    assert items[0].picnic_id == "s100"
    assert items[0].picnic_name == "Ja! Vollmilch 1 L"
    # Must not have hit the live API since the cache was warm
    assert client.gtin_calls == []


@pytest.mark.asyncio
async def test_resolve_status_uses_live_gtin_lookup_and_caches(session, client):
    """Item with inventory_barcode and no cache entry triggers a live lookup and caches the result."""
    session.add(ShoppingListItem(name="Milch", quantity=1, inventory_barcode="4014400900057"))
    await session.commit()

    items = await resolve_shopping_list_status(session, client)
    assert items[0].picnic_status == "mapped"
    assert items[0].picnic_id == "s100"
    assert "4014400900057" in client.gtin_calls

    # Verify it was cached in picnic_products
    from sqlalchemy import select
    cached = (await session.execute(
        select(PicnicProduct).where(PicnicProduct.ean == "4014400900057")
    )).scalar_one()
    assert cached.picnic_id == "s100"


@pytest.mark.asyncio
async def test_resolve_status_unavailable_when_gtin_lookup_misses(session, client):
    """Item with inventory_barcode that Picnic doesn't carry becomes 'unavailable'."""
    session.add(ShoppingListItem(name="Dr.OetkerHefe", quantity=1, inventory_barcode="9999999999999"))
    await session.commit()

    items = await resolve_shopping_list_status(session, client)
    assert items[0].picnic_status == "unavailable"
    assert items[0].picnic_id is None


@pytest.mark.asyncio
async def test_sync_adds_mapped_items_to_cart(session, client):
    session.add(ShoppingListItem(name="Milch", quantity=2, picnic_id="s100"))
    session.add(ShoppingListItem(name="Nothing", quantity=1, inventory_barcode="9999999999999"))  # unavailable
    await session.commit()

    response = await sync_shopping_list_to_cart(session, client)
    assert response.added_count == 1
    assert response.skipped_count == 1
    assert ("s100", 2) in client.added_products


@pytest.mark.asyncio
async def test_sync_reports_failures_per_item(session, client):
    client.raise_on_add = {"s200": "product_unavailable"}
    session.add(ShoppingListItem(name="Milch", quantity=1, picnic_id="s100"))
    session.add(ShoppingListItem(name="Nudeln", quantity=1, picnic_id="s200"))
    await session.commit()

    response = await sync_shopping_list_to_cart(session, client)
    assert response.added_count == 1
    assert response.failed_count == 1
    failed = next(r for r in response.results if r.status == "failed")
    assert failed.picnic_id == "s200"
    assert "unavailable" in (failed.failure_reason or "").lower()
