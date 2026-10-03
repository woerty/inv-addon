"""Linking scanned EANs to Picnic products.

Private-label goods are sold under several EANs: the tracked Schlagsahne
rule sat on 4311596460540 while the packs at home scan as 4311501490426 --
both resolve to the same Picnic product, so restock never saw a decrement.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem
from app.models.picnic import PicnicEanLink, PicnicProduct
from app.models.tracked_product import TrackedProduct
from app.services.picnic.ean_links import (
    link_ean,
    linked_quantity,
    rule_for_barcode,
    stored_picnic_id,
)
from tests.conftest import TestingSessionLocal
from tests.fixtures.picnic.fake_client import FakePicnicClient

RULE_EAN = "4311596460540"
PACK_EAN = "4311501490426"


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestingSessionLocal() as session:
        yield session


def _client() -> FakePicnicClient:
    client = FakePicnicClient()
    client.gtin_lookup[PACK_EAN] = {"id": "s1028032", "name": "Schlagsahne"}
    return client


async def _rule(db: AsyncSession, barcode: str = RULE_EAN) -> TrackedProduct:
    rule = TrackedProduct(
        barcode=barcode, picnic_id="s1028032", name="Schlagsahne",
        min_quantity=2, target_quantity=3,
    )
    db.add(rule)
    await db.flush()
    return rule


async def test_live_lookup_is_stored_and_reused(db: AsyncSession):
    client = _client()

    assert await link_ean(db, client, PACK_EAN) == "s1028032"
    assert await link_ean(db, client, PACK_EAN) == "s1028032"

    assert client.gtin_calls == [PACK_EAN]
    assert (await db.get(PicnicEanLink, PACK_EAN)).picnic_id == "s1028032"


async def test_catalog_pairing_answers_without_a_live_call(db: AsyncSession):
    db.add(PicnicProduct(picnic_id="s1028032", ean=RULE_EAN, name="Schlagsahne"))
    await db.flush()
    client = _client()

    assert await stored_picnic_id(db, RULE_EAN) == (True, "s1028032")
    assert await link_ean(db, client, RULE_EAN) == "s1028032"
    assert client.gtin_calls == []


async def test_stored_lookup_never_writes(db: AsyncSession):
    """Request paths use it; only the reconcile may write links."""
    db.add(PicnicProduct(picnic_id="s1028032", ean=RULE_EAN, name="Schlagsahne"))
    await db.flush()

    await stored_picnic_id(db, RULE_EAN)

    assert await db.get(PicnicEanLink, RULE_EAN) is None


async def test_a_miss_is_remembered_for_a_while(db: AsyncSession):
    client = _client()

    assert await link_ean(db, client, "4337256386500") is None
    assert await link_ean(db, client, "4337256386500") is None
    assert client.gtin_calls == ["4337256386500"]


async def test_an_old_miss_is_looked_up_again(db: AsyncSession):
    db.add(PicnicEanLink(
        ean=PACK_EAN, picnic_id=None,
        checked_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=31),
    ))
    await db.flush()

    assert await link_ean(db, _client(), PACK_EAN) == "s1028032"


async def test_lookup_failure_raises_and_stores_nothing(db: AsyncSession):
    """A throttled Picnic must never be recorded as "not on Picnic"."""
    class Failing(FakePicnicClient):
        async def gtin_picnic_id(self, ean):
            raise RuntimeError("HTTP_429")

    with pytest.raises(RuntimeError):
        await link_ean(db, Failing(), PACK_EAN)
    assert await db.get(PicnicEanLink, PACK_EAN) is None


async def test_custom_and_synthetic_barcodes_are_never_looked_up(db: AsyncSession):
    client = _client()

    assert await link_ean(db, client, "EIGEN-0001") is None
    assert await link_ean(db, client, "picnic:s1028032") is None
    assert client.gtin_calls == []


async def test_rule_is_found_through_another_ean_of_the_same_product(db: AsyncSession):
    rule = await _rule(db)
    db.add(PicnicEanLink(ean=PACK_EAN, picnic_id="s1028032"))
    await db.flush()

    assert await rule_for_barcode(db, RULE_EAN) is rule
    assert await rule_for_barcode(db, PACK_EAN) is rule
    assert await rule_for_barcode(db, "4014400900057") is None


async def test_unlinked_ean_finds_no_rule_until_linked(db: AsyncSession):
    """No live lookup on request paths: the reconcile links it first."""
    await _rule(db, barcode="picnic:s1028032")

    assert await rule_for_barcode(db, PACK_EAN) is None


async def test_linked_quantity_sums_every_ean_of_the_product(db: AsyncSession):
    rule = await _rule(db, barcode="picnic:s1028032")
    db.add_all([
        InventoryItem(barcode=PACK_EAN, name="E/Schlagsahne", quantity=3),
        InventoryItem(barcode=RULE_EAN, name="Schlagsahne", quantity=1),
        InventoryItem(barcode="4014400900057", name="Milch", quantity=7),
    ])
    db.add_all([
        PicnicEanLink(ean=PACK_EAN, picnic_id="s1028032"),
        PicnicEanLink(ean=RULE_EAN, picnic_id="s1028032"),
        PicnicEanLink(ean="4014400900057", picnic_id="s100"),
    ])
    await db.flush()

    assert await linked_quantity(db, rule) == 4
    assert await linked_quantity(db, rule, exclude_barcode=PACK_EAN) == 1
