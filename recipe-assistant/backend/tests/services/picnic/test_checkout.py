import pytest

from app.services.picnic.checkout import (
    PicnicCheckoutError,
    parse_delivery_slots,
    place_order,
)
from tests.fixtures.picnic.fake_client import FakePicnicClient

SAMPLE_SLOTS = {
    "delivery_slots": [
        {
            "slot_id": "slot-b",
            "window_start": "2026-06-09T11:55:00.000+02:00",
            "window_end": "2026-06-09T13:45:00.000+02:00",
            "cut_off_time": "2026-06-08T13:00:00.000+02:00",
            "is_available": True,
            "selected": False,
            "reserved": False,
            "minimum_order_value": 4500,
        },
        {
            "slot_id": "slot-a",
            "window_start": "2026-06-08T15:45:00.000+02:00",
            "window_end": "2026-06-08T17:35:00.000+02:00",
            "cut_off_time": "2026-06-07T23:00:00.000+02:00",
            "is_available": True,
            "selected": True,
            "reserved": True,
            "minimum_order_value": 4500,
        },
    ]
}


async def _no_sleep(_seconds: float) -> None:
    return None


# ── parse_delivery_slots ──────────────────────────────────────────────


async def test_parse_delivery_slots_sorts_and_maps():
    client = FakePicnicClient()
    client.delivery_slots_raw = SAMPLE_SLOTS
    client.cart = {
        "items": [],
        "total_price": 1099,
        "selected_slot": {"slot_id": "slot-a", "state": "ACTIVE"},
    }
    result = await parse_delivery_slots(client)

    # Sorted by window_start ascending (raw order was b, a).
    assert [s.slot_id for s in result.slots] == ["slot-a", "slot-b"]
    first = result.slots[0]
    assert first.selected is True
    assert first.reserved is True
    assert first.minimum_order_value_cents == 4500
    assert result.selected_slot_id == "slot-a"
    assert result.cart_total_price_cents == 1099


async def test_parse_delivery_slots_empty():
    client = FakePicnicClient()
    client.delivery_slots_raw = {"delivery_slots": []}
    client.cart = {"items": [], "total_price": 0}
    result = await parse_delivery_slots(client)
    assert result.slots == []
    assert result.selected_slot_id is None
    assert result.cart_total_price_cents == 0


# ── place_order ───────────────────────────────────────────────────────


async def test_place_order_happy_path():
    client = FakePicnicClient()
    client.cart = {"items": [], "total_price": 5000, "mts": 777}
    client.checkout_start_results = [{"order_id": "ord-1", "total_price": 5000}]
    client.initiate_payment_result = {"transaction_id": "tx-1", "payment_id": "p1"}
    client.status_sequence = ["PENDING", "FINISHED"]

    result = await place_order(client, sleep=_no_sleep)

    assert result.order_id == "ord-1"
    assert result.status == "FINISHED"
    assert result.total_price_cents == 5000
    assert client.checkout_start_calls == [(777, None)]
    assert client.initiate_payment_calls == ["ord-1"]


async def test_place_order_retries_with_resolve_key():
    client = FakePicnicClient()
    client.cart = {"mts": 1}
    client.checkout_start_results = [
        {"error": {"code": "VERIFICATION_REQUIRED"}, "resolve_key": "age_verification"},
        {"order_id": "ord-2"},
    ]
    client.status_sequence = ["FINISHED"]

    result = await place_order(client, sleep=_no_sleep)

    assert result.order_id == "ord-2"
    # Second call carries the resolve key.
    assert client.checkout_start_calls == [(1, None), (1, "age_verified")]


async def test_place_order_checkout_error_raises():
    client = FakePicnicClient()
    client.cart = {"mts": 1}
    client.checkout_start_results = [
        {"error": {"code": "MIN_ORDER_VALUE", "message": "Mindestbestellwert nicht erreicht"}}
    ]

    with pytest.raises(PicnicCheckoutError):
        await place_order(client, sleep=_no_sleep)
    # Payment must never be attempted when checkout/start failed.
    assert client.initiate_payment_calls == []


async def test_place_order_3ds_raises():
    client = FakePicnicClient()
    client.cart = {"mts": 1}
    client.checkout_start_results = [{"order_id": "ord-3"}]
    client.initiate_payment_result = {
        "issuer_authentication_url": "https://3ds.example/auth",
        "transaction_id": "tx",
    }

    with pytest.raises(PicnicCheckoutError):
        await place_order(client, sleep=_no_sleep)


async def test_place_order_poll_timeout_returns_processing():
    """If the order was submitted (order_id + payment accepted) but no terminal
    status arrives, report it as submitted/PROCESSING — never as a failure, since
    the order has in fact been placed (verified live: the cart is cleared)."""
    client = FakePicnicClient()
    client.cart = {"mts": 1}
    client.checkout_start_results = [{"order_id": "ord-4"}]
    client.initiate_payment_result = {"transaction_id": "tx-4"}
    client.status_sequence = ["PENDING"]  # never reaches a terminal status

    result = await place_order(client, sleep=_no_sleep, max_attempts=3)
    assert result.order_id == "ord-4"
    assert result.status == "PROCESSING"


async def test_place_order_finished_via_alternate_status_field():
    """Accept a terminal status reported under "status" (not just "checkout_status")
    and case-insensitively — the live status shape was not pinned down."""
    client = FakePicnicClient()
    client.cart = {"mts": 1}
    client.checkout_start_results = [{"order_id": "ord-5"}]
    client.initiate_payment_result = {"transaction_id": "tx-5"}
    client.status_responses = [{"status": "completed"}]

    result = await place_order(client, sleep=_no_sleep)
    assert result.status == "FINISHED"


async def test_place_order_failed_status_raises():
    client = FakePicnicClient()
    client.cart = {"mts": 1}
    client.checkout_start_results = [{"order_id": "ord-6"}]
    client.initiate_payment_result = {"transaction_id": "tx-6"}
    client.status_sequence = ["FAILED"]

    with pytest.raises(PicnicCheckoutError):
        await place_order(client, sleep=_no_sleep)
