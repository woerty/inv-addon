import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.picnic import PicnicProduct
from app.services.picnic.catalog import (
    PicnicProductData,
    get_product,
    upsert_product,
)

TEST_DB = "sqlite+aiosqlite:///./test_catalog.db"


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


@pytest.mark.asyncio
async def test_upsert_product_creates(session: AsyncSession):
    data = PicnicProductData(
        picnic_id="s1",
        ean="4014400900057",
        name="Ja! Vollmilch 1 L",
        unit_quantity="1 L",
        image_id="img-1",
        last_price_cents=99,
    )
    await upsert_product(session, data)
    await session.commit()

    row = await get_product(session, "s1")
    assert row is not None
    assert row.name == "Ja! Vollmilch 1 L"
    assert row.ean == "4014400900057"
    assert row.last_price_cents == 99


@pytest.mark.asyncio
async def test_upsert_product_updates_existing_preserves_ean(session: AsyncSession):
    """Updating a row without passing ean must not clobber a previously learned ean."""
    data1 = PicnicProductData(picnic_id="s1", ean="4014400900057", name="Old Name",
                              unit_quantity=None, image_id=None, last_price_cents=100)
    await upsert_product(session, data1)
    await session.commit()

    # Second call without ean (e.g. seen in a delivery without reverse-lookup)
    data2 = PicnicProductData(picnic_id="s1", ean=None, name="New Name",
                              unit_quantity=None, image_id=None, last_price_cents=120)
    await upsert_product(session, data2)
    await session.commit()

    row = await get_product(session, "s1")
    assert row.name == "New Name"
    assert row.last_price_cents == 120
    assert row.ean == "4014400900057"  # preserved!


@pytest.mark.asyncio
async def test_upsert_product_updates_ean_when_provided(session: AsyncSession):
    """If the caller provides a new ean, it wins."""
    data1 = PicnicProductData(picnic_id="s1", ean=None, name="Vollmilch",
                              unit_quantity=None, image_id=None, last_price_cents=100)
    await upsert_product(session, data1)
    await session.commit()

    data2 = PicnicProductData(picnic_id="s1", ean="4014400900057", name="Vollmilch",
                              unit_quantity=None, image_id=None, last_price_cents=100)
    await upsert_product(session, data2)
    await session.commit()

    row = await get_product(session, "s1")
    assert row.ean == "4014400900057"


@pytest.mark.asyncio
async def test_get_by_ean(session: AsyncSession):
    from app.services.picnic.catalog import get_product_by_ean
    data = PicnicProductData(picnic_id="s1", ean="4014400900057", name="Vollmilch",
                             unit_quantity=None, image_id=None, last_price_cents=100)
    await upsert_product(session, data)
    await session.commit()

    row = await get_product_by_ean(session, "4014400900057")
    assert row is not None
    assert row.picnic_id == "s1"


@pytest.mark.asyncio
async def test_get_by_ean_multiple_picks_most_recent(session: AsyncSession):
    """Same EAN, different pack sizes → most recently seen wins."""
    import asyncio
    from app.services.picnic.catalog import get_product_by_ean
    await upsert_product(session, PicnicProductData(
        picnic_id="s1", ean="4014400900057", name="Vollmilch 500ml",
        unit_quantity="500 ml", image_id=None, last_price_cents=50))
    await session.commit()
    await asyncio.sleep(0.05)  # ensure last_seen differs
    await upsert_product(session, PicnicProductData(
        picnic_id="s2", ean="4014400900057", name="Vollmilch 1L",
        unit_quantity="1 L", image_id=None, last_price_cents=100))
    await session.commit()

    row = await get_product_by_ean(session, "4014400900057")
    assert row.picnic_id == "s2"


@pytest.mark.asyncio
async def test_get_product_missing_returns_none(session: AsyncSession):
    row = await get_product(session, "does-not-exist")
    assert row is None
