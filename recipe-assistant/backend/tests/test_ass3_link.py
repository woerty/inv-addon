"""The ass3 link: whitelist, expiry, scan-out like the scanner, snapshot
format, poll round trip. HTTP to ass3 goes through httpx.MockTransport."""

import json
import logging
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.picnic import PicnicProduct
from app.models.tracked_product import TrackedProduct
from app.services import ass3_link
from app.services.ass3_link import (
    Ass3Link,
    _Failures,
    backoff_delay,
    build_snapshot,
    cart_payload,
    is_enabled,
    start_ass3_link,
)
from tests.conftest import TestingSessionLocal
from tests.fixtures.picnic.fake_client import FakePicnicClient

URL = "https://ass3.test"


def _settings(*, picnic: bool = True, url: str = URL, token: str = "tok") -> Settings:
    return Settings(
        ass3_url=url,
        ass3_token=token,
        picnic_email="me@example.com" if picnic else "",
        picnic_password="pw" if picnic else "",
    )


class Ass3Stub:
    """Plays ass3: hands out queued commands once, records what is posted."""

    def __init__(self, commands: list[dict] | None = None) -> None:
        self.commands = commands or []
        self.results: list[dict] = []
        self.snapshots: list[dict] = []
        self.auth: set[str | None] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.auth.add(request.headers.get("Authorization"))
        path = request.url.path
        if request.method == "GET" and path == "/api/inventory-link/commands":
            assert request.url.params["wait"] == "50"
            commands, self.commands = self.commands, []
            return httpx.Response(200, json={"commands": commands})
        if request.method == "POST" and path == "/api/inventory-link/results":
            self.results.append(json.loads(request.content))
            return httpx.Response(200, json={})
        if request.method == "POST" and path == "/api/inventory-link/snapshot":
            self.snapshots.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(404)


@pytest.fixture
def fake_picnic() -> FakePicnicClient:
    return FakePicnicClient()


@pytest.fixture
def stub() -> Ass3Stub:
    return Ass3Stub()


@pytest.fixture
async def link(stub, fake_picnic):
    link = Ass3Link(
        _settings(),
        session_factory=TestingSessionLocal,
        picnic_factory=lambda: fake_picnic,
        transport=httpx.MockTransport(stub.handler),
    )
    yield link
    await link.aclose()


def _cmd(action: str, args: dict | None = None, *, expires_in: float = 60, cmd_id: str = "c1") -> dict:
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    return {"id": cmd_id, "action": action, "args": args or {}, "expires_at": expires_at.isoformat()}


async def _seed_milk(quantity: int, *, tracked: bool = True) -> None:
    async with TestingSessionLocal() as db:
        db.add(InventoryItem(barcode="b1", name="Milch", quantity=quantity))
        if tracked:
            db.add(
                TrackedProduct(
                    barcode="b1", picnic_id="s100", name="Ja! Vollmilch 1 L",
                    min_quantity=2, target_quantity=5,
                )
            )
        await db.commit()


async def _row(barcode: str) -> InventoryItem | None:
    async with TestingSessionLocal() as db:
        return (
            await db.execute(select(InventoryItem).where(InventoryItem.barcode == barcode))
        ).scalar_one_or_none()


# ── Switch and backoff ──


def test_link_is_off_without_both_options():
    assert not is_enabled(_settings(url="", token=""))
    assert not is_enabled(_settings(token=""))
    assert not is_enabled(_settings(url=""))
    assert is_enabled(_settings())
    assert start_ass3_link(_settings(url="", token="")) is None


def test_from_ha_options_reads_ass3_options(tmp_path):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"ass3_url": URL, "ass3_token": "tok"}))
    s = Settings.from_ha_options(options_path=options)
    assert (s.ass3_url, s.ass3_token) == (URL, "tok")

    options.write_text(json.dumps({}))
    assert not is_enabled(Settings.from_ha_options(options_path=options))


def test_backoff_doubles_from_5s_and_caps_at_60s():
    assert [backoff_delay(n) for n in range(1, 8)] == [5, 10, 20, 40, 60, 60, 60]
    assert backoff_delay(10_000) == 60


def test_repeated_failure_is_logged_once(caplog):
    failures = _Failures("command poll")
    request = httpx.Request("GET", URL)
    down = httpx.ConnectError("refused", request=request)
    with caplog.at_level(logging.INFO, logger="ass3_link"):
        delays = [failures.failed(down) for _ in range(3)]
        failures.failed(ass3_link.Unauthorized(403))
        failures.succeeded()
    assert delays == [5, 10, 20]
    messages = [r.getMessage() for r in caplog.records]
    assert sum("unreachable" in m for m in messages) == 1
    assert sum("rejected the token (403)" in m for m in messages) == 1
    assert any("works again after 4" in m for m in messages)


# ── Whitelist ──


async def test_unknown_action_is_refused(link):
    result = await link.execute(_cmd("checkout"))
    assert result == {"id": "c1", "ok": False, "error": "unknown_action"}


@pytest.mark.parametrize(
    "action,args",
    [
        ("scan_out", {"barcode": "b1", "count": 0}),
        ("scan_out", {"barcode": "b1", "count": 21}),
        ("scan_out", {"barcode": "b1", "count": "2"}),
        ("scan_out", {"barcode": "b1", "count": True}),
        ("scan_out", {"barcode": "b1"}),
        ("scan_out", {"count": 1}),
        ("scan_out", {"barcode": "", "count": 1}),
        ("scan_out", {"barcode": "b1", "count": 1, "extra": 1}),
        ("cart_add", {"picnic_id": "s100", "count": 0}),
        ("cart_remove", {"picnic_id": "s100", "count": 21}),
        ("picnic_search", {"q": "  "}),
        ("picnic_search", {"q": "x" * 101}),
        ("refresh", {"force": True}),
    ],
)
async def test_bad_args_are_refused(link, action, args):
    await _seed_milk(3)
    result = await link.execute(_cmd(action, args))
    assert result == {"id": "c1", "ok": False, "error": "bad_args"}
    assert (await _row("b1")).quantity == 3


async def test_expired_command_is_not_executed(link):
    await _seed_milk(3)
    result = await link.execute(_cmd("scan_out", {"barcode": "b1", "count": 1}, expires_in=-1))
    assert result == {"id": "c1", "ok": False, "error": "expired"}
    assert (await _row("b1")).quantity == 3


async def test_command_without_expiry_is_refused(link):
    await _seed_milk(3)
    command = {"id": "c1", "action": "scan_out", "args": {"barcode": "b1", "count": 1}}
    assert (await link.execute(command))["error"] == "bad_args"
    assert (await _row("b1")).quantity == 3


# ── scan_out ──


async def test_scan_out_decrements_logs_and_restocks_like_the_scanner(link, fake_picnic):
    await _seed_milk(3)  # rule: min 2, target 5

    result = await link.execute(_cmd("scan_out", {"barcode": "b1", "count": 2}))

    assert result == {
        "id": "c1", "ok": True,
        "data": {"barcode": "b1", "name": "Milch", "quantity": 1, "removed": 2},
    }
    assert (await _row("b1")).quantity == 1
    async with TestingSessionLocal() as db:
        logs = (await db.execute(select(InventoryLog).order_by(InventoryLog.id))).scalars().all()
    assert [(log.action, log.details) for log in logs] == [
        ("scan-out", "quantity: 3 → 2"),
        ("scan-out", "quantity: 2 → 1"),
        ("restock_auto", "qty→1, cart delta=4"),
    ]
    # Restock check ran (once, on the last unit): 5 - 1 = 4 into the cart.
    assert fake_picnic.added_products == [("s100", 4)]


async def test_scan_out_stops_when_the_item_is_gone(link):
    await _seed_milk(2, tracked=False)
    result = await link.execute(_cmd("scan_out", {"barcode": "b1", "count": 5}))
    assert result["data"] == {"barcode": "b1", "name": "Milch", "quantity": 0, "removed": 2}
    assert await _row("b1") is None  # untracked: deleted like the scanner does


async def test_scan_out_of_an_empty_tracked_row_removes_nothing(link):
    await _seed_milk(0)
    result = await link.execute(_cmd("scan_out", {"barcode": "b1", "count": 1}))
    assert result["data"] == {"barcode": "b1", "name": "Milch", "quantity": 0, "removed": 0}
    assert (await _row("b1")).quantity == 0


async def test_scan_out_unknown_barcode_is_not_found(link):
    result = await link.execute(_cmd("scan_out", {"barcode": "nope", "count": 1}))
    assert result == {"id": "c1", "ok": False, "error": "not_found"}


# ── Picnic commands ──


async def test_picnic_search_maps_hits(link):
    result = await link.execute(_cmd("picnic_search", {"q": "Milch"}))
    assert result["ok"]
    assert result["data"]["results"][0] == {
        "picnic_id": "s100",
        "name": "Ja! Vollmilch 1 L",
        "unit_quantity": "1 L",
        "price_cents": 99,
        "image_url": "https://storefront-prod.de.picnicinternational.com/static/images/img-100/small.png",
    }
    assert len(result["data"]["results"]) == 2


async def test_picnic_commands_without_picnic_configured(stub, fake_picnic):
    link = Ass3Link(
        _settings(picnic=False),
        session_factory=TestingSessionLocal,
        picnic_factory=lambda: fake_picnic,
        transport=httpx.MockTransport(stub.handler),
    )
    result = await link.execute(_cmd("cart_add", {"picnic_id": "s100", "count": 1}))
    await link.aclose()
    assert result == {"id": "c1", "ok": False, "error": "picnic_not_configured"}
    assert fake_picnic.added_products == []


async def test_picnic_commands_are_rate_limited(link, monkeypatch):
    monkeypatch.setattr(ass3_link, "PICNIC_COMMANDS_PER_WINDOW", 2)
    results = [await link.execute(_cmd("picnic_search", {"q": "milch"})) for _ in range(3)]
    assert [r["ok"] for r in results] == [True, True, False]
    assert results[2]["error"] == "rate_limited"


async def test_cart_change_with_unreadable_cart_says_it_changed(link, fake_picnic):
    async def broken_cart():
        raise RuntimeError("429")

    fake_picnic.get_cart = broken_cart
    result = await link.execute(_cmd("cart_add", {"picnic_id": "s100", "count": 1}))
    assert result == {"id": "c1", "ok": False, "error": "cart_changed_but_unreadable"}
    assert fake_picnic.added_products == [("s100", 1)]


async def test_picnic_rejection_is_reported(link, fake_picnic):
    from app.services.picnic.client import PicnicAPIError

    async def rejected(picnic_id, count=1):
        raise PicnicAPIError("PRODUCT_NOT_AVAILABLE", "Nicht verfuegbar")

    fake_picnic.remove_product = rejected
    result = await link.execute(_cmd("cart_remove", {"picnic_id": "s100", "count": 1}))
    assert result == {"id": "c1", "ok": False, "error": "picnic_rejected: Nicht verfuegbar"}


def test_cart_payload_reads_items_total_and_selected_slot():
    raw = {
        "items": [
            {
                "id": "line-1",
                "items": [
                    {
                        "id": "s100", "name": "Ja! Vollmilch 1 L", "price": 99,
                        "decorators": [{"type": "QUANTITY", "quantity": 2}],
                    }
                ],
            }
        ],
        "selected_slot": {"slot_id": "slot-2"},
        "delivery_slots": [
            {"slot_id": "slot-1", "window_start": "2026-10-06T08:00:00+02:00", "window_end": "2026-10-06T09:00:00+02:00"},
            {"slot_id": "slot-2", "window_start": "2026-10-06T18:00:00+02:00", "window_end": "2026-10-06T19:00:00+02:00"},
        ],
    }
    assert cart_payload(raw) == {
        "items": [{"picnic_id": "s100", "name": "Ja! Vollmilch 1 L", "count": 2, "price_cents": 99}],
        "total_cents": 198,
        "slot": {"start": "2026-10-06T18:00:00+02:00", "end": "2026-10-06T19:00:00+02:00"},
    }
    assert cart_payload({"items": []})["slot"] is None


# ── Snapshot ──


async def test_snapshot_payload_shape():
    async with TestingSessionLocal() as db:
        fridge = StorageLocation(name="Kühlschrank")
        db.add(fridge)
        await db.flush()
        db.add(
            InventoryItem(
                barcode="4014400900057", name="Milch", quantity=2, category="Milchprodukte",
                storage_location_id=fridge.id, expiration_date=date(2026, 10, 8),
                image_url="https://off.example/milk.jpg",
            )
        )
        db.add(InventoryItem(barcode="EIGEN-1", name="Marmelade", quantity=1, category="Eigene Produkte"))
        db.add(PicnicProduct(picnic_id="s100", ean="4014400900057", name="Ja! Vollmilch 1 L", image_id="img-100"))
        db.add(
            TrackedProduct(
                barcode="4014400900057", picnic_id="s100", name="Ja! Vollmilch 1 L",
                min_quantity=2, target_quantity=6,
            )
        )
        await db.commit()

        snapshot = await build_snapshot(db)

    assert set(snapshot) == {"at", "inventory", "rules"}
    assert datetime.fromisoformat(snapshot["at"]).tzinfo is not None
    assert snapshot["inventory"] == [
        {
            "barcode": "EIGEN-1", "name": "Marmelade", "quantity": 1, "category": "Eigene Produkte",
            "location": None, "expiration_date": None, "image_url": None,
        },
        {
            "barcode": "4014400900057", "name": "Milch", "quantity": 2, "category": "Milchprodukte",
            "location": "Kühlschrank", "expiration_date": "2026-10-08",
            "image_url": "https://storefront-prod.de.picnicinternational.com/static/images/img-100/small.png",
        },
    ]
    assert snapshot["rules"] == [
        {
            "barcode": "4014400900057", "name": "Ja! Vollmilch 1 L",
            "min_quantity": 2, "restock_quantity": 6, "picnic_id": "s100", "current": 2,
        }
    ]


async def test_snapshot_rule_current_counts_linked_eans_like_restock():
    """Stock on other EANs of the rule's Picnic product counts, through the
    stored links -- also for a rule on a picnic: placeholder barcode."""
    from app.models.picnic import PicnicEanLink
    from app.services.picnic.ean_links import linked_quantity

    async with TestingSessionLocal() as db:
        # Placeholder rule, stock on two linked EANs.
        db.add(TrackedProduct(barcode="picnic:s100", picnic_id="s100", name="Sahne", min_quantity=3, target_quantity=6))
        db.add(InventoryItem(barcode="4000000000011", name="Sahne A", quantity=2))
        db.add(InventoryItem(barcode="4000000000012", name="Sahne B", quantity=3))
        db.add(PicnicEanLink(ean="4000000000011", picnic_id="s100"))
        db.add(PicnicEanLink(ean="4000000000012", picnic_id="s100"))
        # Rule on a real barcode with a row, plus a linked second EAN.
        db.add(TrackedProduct(barcode="4000000000021", picnic_id="s200", name="Milch", min_quantity=2, target_quantity=4))
        db.add(InventoryItem(barcode="4000000000021", name="Milch", quantity=1))
        db.add(InventoryItem(barcode="4000000000022", name="Milch neu", quantity=4))
        db.add(PicnicEanLink(ean="4000000000022", picnic_id="s200"))
        # Not linked to anything: counts for no rule.
        db.add(InventoryItem(barcode="4000000000031", name="Sahne C", quantity=7))
        await db.commit()

        snapshot = await build_snapshot(db)
        rules = (await db.execute(select(TrackedProduct))).scalars().all()
        restock_view = {r.barcode: await linked_quantity(db, r) for r in rules}

    current = {r["barcode"]: r["current"] for r in snapshot["rules"]}
    assert current == {"picnic:s100": 5, "4000000000021": 5}
    assert current == restock_view


async def test_refresh_pushes_cart_and_orders(link, stub, fake_picnic):
    fake_picnic.deliveries_summary = [{"delivery_id": "del-1", "status": "CURRENT"}]

    result = await link.execute(_cmd("refresh"))

    assert result == {"id": "c1", "ok": True, "data": {}}
    [snapshot] = stub.snapshots
    assert set(snapshot) == {"at", "inventory", "rules", "cart", "orders"}
    assert snapshot["cart"] == {"items": [], "total_cents": 0, "slot": None}
    assert snapshot["orders"] == [
        {
            "id": "del-1", "status": "CURRENT",
            "slot_start": "2026-04-04T10:00:00+00:00", "slot_end": "2026-04-04T10:30:00+00:00",
            "items_count": 3, "total_cents": 347,
        }
    ]


async def test_snapshot_leaves_picnic_out_when_not_logged_in(link, stub, fake_picnic):
    from app.services.picnic.client import PicnicReauthRequired

    async def reauth():
        raise PicnicReauthRequired("2FA")

    fake_picnic.get_cart = reauth
    await link.push_snapshot(picnic=True)
    assert set(stub.snapshots[0]) == {"at", "inventory", "rules"}


async def test_fingerprint_changes_with_inventory(link):
    before = await link._fingerprint()
    await _seed_milk(3)
    assert await link._fingerprint() != before


# ── Poll round trip ──


async def test_poll_runs_commands_in_order_and_posts_results(link, stub, fake_picnic):
    await _seed_milk(3)
    stub.commands = [
        _cmd("scan_out", {"barcode": "b1", "count": 1}, cmd_id="c1"),
        _cmd("cart_add", {"picnic_id": "s200", "count": 2}, cmd_id="c2"),
        _cmd("checkout", cmd_id="c3"),
    ]

    await link.poll_once()

    assert stub.auth == {"Bearer tok"}
    assert [(r["id"], r["ok"]) for r in stub.results] == [("c1", True), ("c2", True), ("c3", False)]
    assert stub.results[1]["data"]["items"] == [
        {"picnic_id": "s200", "name": "s200", "count": 2, "price_cents": None}
    ]
    assert fake_picnic.added_products == [("s200", 2)]
    # The cart change is pushed right away, with the cart.
    [snapshot] = stub.snapshots
    assert snapshot["cart"]["items"][0]["picnic_id"] == "s200"
    assert snapshot["inventory"][0]["quantity"] == 2


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_token_raises_unauthorized(fake_picnic, status):
    link = Ass3Link(
        _settings(),
        session_factory=TestingSessionLocal,
        picnic_factory=lambda: fake_picnic,
        transport=httpx.MockTransport(lambda request: httpx.Response(status)),
    )
    with pytest.raises(ass3_link.Unauthorized) as raised:
        await link.poll_once()
    await link.aclose()
    assert "token" in ass3_link._describe(raised.value)
    assert str(status) in ass3_link._describe(raised.value)


async def test_run_pushes_at_startup_and_survives_failures(monkeypatch):
    """Both loops: the startup snapshot carries cart and orders, a failed
    push keeps them for the retry, a 503 on the poll only backs off, an
    inventory change is pushed without asking Picnic again."""
    import asyncio

    real_sleep = asyncio.sleep
    waits: list[float] = []

    async def fast_sleep(seconds):
        waits.append(seconds)
        await real_sleep(0.01)

    monkeypatch.setattr(ass3_link.asyncio, "sleep", fast_sleep)
    calls = {"commands": 0, "snapshot": 0}
    snapshots: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        await real_sleep(0.005)
        if request.url.path.endswith("/commands"):
            calls["commands"] += 1
            if calls["commands"] <= 2:
                return httpx.Response(503)
            return httpx.Response(200, json={"commands": []})
        calls["snapshot"] += 1
        if calls["snapshot"] == 1:
            raise httpx.ConnectError("down", request=request)
        snapshots.append(json.loads(request.content))
        return httpx.Response(200, json={})

    fake = FakePicnicClient()
    link = Ass3Link(
        _settings(),
        session_factory=TestingSessionLocal,
        picnic_factory=lambda: fake,
        transport=httpx.MockTransport(handler),
    )

    async def until(condition):
        for _ in range(300):
            if condition():
                return
            await real_sleep(0.01)
        raise AssertionError("timed out")

    task = asyncio.create_task(link.run())
    try:
        await until(lambda: snapshots)
        await _seed_milk(3)
        await until(lambda: any(s["inventory"] for s in snapshots))
        await until(lambda: calls["commands"] > 3)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert set(snapshots[0]) == {"at", "inventory", "rules", "cart", "orders"}
    assert set(snapshots[-1]) == {"at", "inventory", "rules"}
    # Poll: 5 s, then doubled to 10 s; push: 5 s once.
    assert sorted(w for w in waits if w in (5, 10, 20)) == [5, 5, 10]
    assert link._http.is_closed
