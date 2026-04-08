from __future__ import annotations

from tests.fixtures.picnic.fake_client import FakePicnicClient
from app.services.picnic.orders import parse_pending_orders


def _make_delivery(delivery_id: str, status: str, items: list[dict]) -> dict:
    return {
        "id": delivery_id,
        "status": status,
        "delivery_time": {"start": "2026-04-10T14:00:00+02:00"},
        "orders": [{"items": items}],
    }


def _make_item(picnic_id: str, name: str, qty: int) -> dict:
    """Returns a line dict (not a product dict) as expected by _flatten_delivery_items."""
    return {
        "id": f"line-{picnic_id}",
        "items": [
            {
                "id": picnic_id,
                "name": name,
                "unit_quantity": "1 stuk",
                "image_id": "img1",
                "display_price": 199,
            }
        ],
        "decorators": [{"quantity": qty}],
    }


async def test_parse_pending_orders_filters_completed():
    deliveries = [
        {"id": "d1", "status": "CURRENT"},
        {"id": "d2", "status": "COMPLETED"},
        {"id": "d3", "status": "PENDING"},
    ]
    client = FakePicnicClient()
    client.deliveries_summary = deliveries
    client.delivery_details = {
        "d1": _make_delivery("d1", "CURRENT", [_make_item("s100", "Milch", 2)]),
        "d3": _make_delivery("d3", "PENDING", [_make_item("s100", "Milch", 1), _make_item("s200", "Brot", 3)]),
    }
    result = await parse_pending_orders(client)
    assert len(result.orders) == 2
    assert result.quantity_map == {"s100": 3, "s200": 3}


async def test_parse_pending_orders_empty_when_all_completed():
    client = FakePicnicClient()
    client.deliveries_summary = [{"id": "d1", "status": "COMPLETED"}]
    result = await parse_pending_orders(client)
    assert len(result.orders) == 0
    assert result.quantity_map == {}
