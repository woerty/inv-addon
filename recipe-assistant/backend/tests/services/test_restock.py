from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem
from app.models.log import InventoryLog
from app.models.picnic import PicnicEanLink
from app.models.tracked_product import TrackedProduct
from app.services.restock import check_and_enqueue, reconcile_all
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


def _seed_pending_delivery(client: FakePicnicClient, picnic_id: str, qty: int) -> None:
    """Inject a non-completed delivery containing `qty` of `picnic_id`."""
    client.deliveries_summary = [
        {
            # Real Picnic /deliveries/summary returns "delivery_id", not "id".
            "delivery_id": "del-pending-1",
            "status": "DELIVERING",
            "delivery_time": {
                "start": "2026-06-01T10:00:00+00:00",
                "end": "2026-06-01T10:30:00+00:00",
            },
        }
    ]
    client.delivery_details = {
        "del-pending-1": {
            "delivery_id": "del-pending-1",
            "status": "DELIVERING",
            "delivery_time": {
                "start": "2026-06-01T10:00:00+00:00",
                "end": "2026-06-01T10:30:00+00:00",
            },
            "orders": [
                {
                    "items": [
                        {
                            "id": "order-line-1",
                            "items": [
                                {"id": picnic_id, "name": "x", "image_id": None}
                            ],
                            "decorators": [{"quantity": qty}],
                        }
                    ]
                }
            ],
        }
    }


async def test_below_threshold_deducts_on_order_quantity(db: AsyncSession):
    """Items already on the way home shouldn't trigger another order."""
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()
    _seed_pending_delivery(client, "s100", qty=3)

    result = await check_and_enqueue(
        db, barcode="b1", new_quantity=0, picnic_client=client
    )

    assert result is not None
    # needed=5, on_order=3, cart=0 → delta=2
    assert result.added_quantity == 2
    assert client.added_products == [("s100", 2)]


async def test_below_threshold_skips_when_full_amount_on_order(db: AsyncSession):
    """If the full target quantity is already in a pending delivery, skip."""
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()
    _seed_pending_delivery(client, "s100", qty=5)

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


# ── Matching through the Picnic product ──────────────────────────────────


async def test_decrement_of_another_ean_restocks_the_rule(db: AsyncSession):
    """The Schlagsahne case: rule on one EAN, packs at home scan as another."""
    await _seed_tracked(db, barcode="rule-ean", picnic_id="s100", min_quantity=2, target_quantity=3)
    db.add(InventoryItem(barcode="pack-ean", name="Sahne", quantity=1))
    db.add(PicnicEanLink(ean="pack-ean", picnic_id="s100"))
    await db.flush()
    client = FakePicnicClient()

    result = await check_and_enqueue(db, barcode="pack-ean", new_quantity=1, picnic_client=client)

    assert result is not None
    assert client.added_products == [("s100", 2)]


async def test_other_linked_rows_count_towards_the_threshold(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    db.add(InventoryItem(barcode="other-ean", name="Milch", quantity=3))
    db.add(PicnicEanLink(ean="other-ean", picnic_id="s100"))
    await db.flush()
    client = FakePicnicClient()

    assert await check_and_enqueue(db, barcode="b1", new_quantity=0, picnic_client=client) is None
    assert client.added_products == []


async def test_unreadable_cart_skips_instead_of_guessing(db: AsyncSession):
    """Adding blind could double up; the periodic reconcile retries."""
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)

    class CartDown(FakePicnicClient):
        async def get_cart(self):
            raise RuntimeError("picnic down")

    client = CartDown()
    assert await check_and_enqueue(db, barcode="b1", new_quantity=0, picnic_client=client) is None
    assert client.added_products == []


async def test_unreadable_pending_orders_skips(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)

    class OrdersDown(FakePicnicClient):
        async def get_deliveries(self):
            raise RuntimeError("picnic down")

    client = OrdersDown()
    assert await check_and_enqueue(db, barcode="b1", new_quantity=0, picnic_client=client) is None
    assert client.added_products == []


# ── reconcile_all: re-check every rule, not only on a decrement ──────────


async def test_reconcile_fills_a_rule_that_never_saw_a_decrement(db: AsyncSession):
    await _seed_tracked(db, barcode="picnic:s100", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()

    summary = await reconcile_all(db, client, lookup_delay_s=0)

    assert client.added_products == [("s100", 5)]
    assert summary.added == [("Ja! Vollmilch 1 L", 5)]
    assert summary.checked == 1


async def test_reconcile_links_inventory_first_and_counts_it(db: AsyncSession):
    """4014400900057 resolves to s100 via GTIN; its 4 packs satisfy min 2."""
    await _seed_tracked(db, barcode="picnic:s100", picnic_id="s100", min_quantity=2, target_quantity=5)
    db.add(InventoryItem(barcode="4014400900057", name="Milch", quantity=4))
    await db.flush()
    client = FakePicnicClient()

    summary = await reconcile_all(db, client, lookup_delay_s=0)

    assert client.gtin_calls == ["4014400900057"]
    assert summary.resolved == 1
    assert client.added_products == []


async def test_reconcile_deducts_cart_and_skips_satisfied_rules(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    await _seed_tracked(db, barcode="b2", picnic_id="s200", name="Spaghetti", min_quantity=1, target_quantity=2)
    db.add(InventoryItem(barcode="b2", name="Spaghetti", quantity=3))
    await db.flush()
    client = FakePicnicClient()
    client.cart_items = {"s100": 2}

    summary = await reconcile_all(db, client, lookup_delay_s=0)

    assert client.added_products == [("s100", 3)]
    assert summary.checked == 2


async def test_reconcile_reports_a_refused_add_without_logging_it(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
    client = FakePicnicClient()
    client.raise_on_add = {"s100": "Client version is required"}

    summary = await reconcile_all(db, client, lookup_delay_s=0)

    assert summary.failed == ["Ja! Vollmilch 1 L"]
    logs = (await db.execute(select(InventoryLog))).scalars().all()
    assert not [log for log in logs if log.action == "restock_auto"]


async def test_reconcile_aborts_when_the_cart_is_unreadable(db: AsyncSession):
    await _seed_tracked(db, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)

    class CartDown(FakePicnicClient):
        async def get_cart(self):
            raise RuntimeError("picnic down")

    client = CartDown()
    with pytest.raises(RuntimeError):
        await reconcile_all(db, client, lookup_delay_s=0)
    assert client.added_products == []



# ── Scheduled run ─────────────────────────────────────────────────────────


async def test_scheduled_run_commits_its_restocks():
    from app.services.restock_schedule import run_reconcile_once

    async with TestingSessionLocal() as session:
        await _seed_tracked(session, barcode="b1", picnic_id="s100", min_quantity=2, target_quantity=5)
        await session.commit()
    client = FakePicnicClient()

    summary = await run_reconcile_once(TestingSessionLocal, lambda: client)

    assert summary is not None and summary.added == [("Ja! Vollmilch 1 L", 5)]
    async with TestingSessionLocal() as session:
        logs = (await session.execute(select(InventoryLog))).scalars().all()
    assert [log.action for log in logs] == ["restock_auto"]


async def test_scheduled_run_survives_picnic_being_down():
    from app.services.restock_schedule import run_reconcile_once

    async with TestingSessionLocal() as session:
        await _seed_tracked(session, barcode="b1", picnic_id="s100")
        await session.commit()

    class CartDown(FakePicnicClient):
        async def get_cart(self):
            raise RuntimeError("picnic down")

    assert await run_reconcile_once(TestingSessionLocal, CartDown) is None


async def test_reconcile_looks_up_rule_lookalikes_first_within_the_limit(db: AsyncSession):
    """Bulk GTIN lookups get throttled by Picnic, so a run only does a few;
    the rows that look like a tracked product go first."""
    await _seed_tracked(db, barcode="picnic:s100", picnic_id="s100", name="Ja! Vollmilch 1 L")
    db.add_all([
        InventoryItem(barcode="8000270013122", name="Barilla Spaghetti", quantity=1),
        InventoryItem(barcode="4014400900057", name="Vollmilch", quantity=4),
    ])
    await db.flush()
    client = FakePicnicClient()

    summary = await reconcile_all(db, client, lookup_limit=1, lookup_delay_s=0)

    assert client.gtin_calls == ["4014400900057"]
    assert summary.resolved == 1
    assert client.added_products == []  # the 4 linked packs satisfy min 2


async def test_catalog_known_eans_do_not_count_against_the_limit(db: AsyncSession):
    from app.models.picnic import PicnicProduct

    await _seed_tracked(db, barcode="picnic:s100", picnic_id="s100")
    db.add_all([
        PicnicProduct(picnic_id="s100", ean="4014400900057", name="Ja! Vollmilch 1 L"),
        InventoryItem(barcode="4014400900057", name="Milch", quantity=4),
        InventoryItem(barcode="8000270013122", name="Spaghetti", quantity=1),
    ])
    await db.flush()
    client = FakePicnicClient()

    summary = await reconcile_all(db, client, lookup_limit=1, lookup_delay_s=0)

    assert client.gtin_calls == ["8000270013122"]
    assert summary.resolved == 2

