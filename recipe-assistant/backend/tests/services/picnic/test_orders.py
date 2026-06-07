from __future__ import annotations

from tests.fixtures.picnic.fake_client import FakePicnicClient
from app.services.picnic.orders import parse_pending_orders


def _make_delivery(delivery_id: str, status: str, items: list[dict]) -> dict:
    order: dict = {"type": "ORDER", "id": f"order-{delivery_id}", "items": items}
    line_total = sum(line.get("price", 0) for line in items)
    if line_total:
        order["total_price"] = line_total
    return {
        "delivery_id": delivery_id,
        "status": status,
        "delivery_time": {"start": "2026-04-10T14:00:00+02:00"},
        "orders": [order],
    }


def _make_item(
    picnic_id: str,
    name: str,
    qty: int,
    unit_price: int = 199,
    promo_total: int | None = None,
    promo_text: str | None = None,
) -> dict:
    """Returns an ORDER_LINE dict as expected by _flatten_delivery_items.

    Mirrors real Picnic shape: the line carries the line total; the article
    carries a sentinel price (ignored) plus image_ids and a QUANTITY decorator.
    Offers are LINE-level PRICE/PROMO decorators.
    """
    line: dict = {
        "type": "ORDER_LINE",
        "id": f"line-{picnic_id}",
        "price": unit_price * qty,
        "display_price": unit_price * qty,
        "items": [
            {
                "type": "ORDER_ARTICLE",
                "id": picnic_id,
                "name": name,
                "unit_quantity": "1 stuk",
                "image_ids": ["img1"],
                "price": 432199,
                "decorators": [
                    {"type": "IMMUTABLE"},
                    {"type": "QUANTITY", "quantity": qty},
                ],
            }
        ],
    }
    decos = []
    if promo_total is not None:
        decos.append({"type": "PRICE", "display_price": promo_total})
    if promo_text is not None:
        decos.append({"type": "PROMO", "text": promo_text})
    if decos:
        line["decorators"] = decos
    return line


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


async def test_parse_pending_orders_computes_total_price():
    client = FakePicnicClient()
    client.deliveries_summary = [{"id": "d1", "status": "CURRENT"}]
    client.delivery_details = {
        "d1": _make_delivery(
            "d1", "CURRENT", [_make_item("s100", "Milch", 2), _make_item("s200", "Brot", 1)]
        ),
    }
    result = await parse_pending_orders(client)
    order = result.orders[0]
    # _make_item carries 199 per unit; total = 199*2 + 199*1
    assert order.total_price_cents == 597


async def test_parse_pending_orders_total_none_without_prices():
    client = FakePicnicClient()
    client.deliveries_summary = [{"id": "d1", "status": "CURRENT"}]
    line = {"id": "line-s1", "items": [{"id": "s1", "name": "X"}], "decorators": [{"quantity": 1}]}
    client.delivery_details = {"d1": _make_delivery("d1", "CURRENT", [line])}
    result = await parse_pending_orders(client)
    assert result.orders[0].total_price_cents is None


async def test_parse_pending_orders_merges_duplicate_lines():
    """Same product on multiple order lines should collapse into one item with
    the summed quantity (Picnic returns one line per unit for some products)."""
    client = FakePicnicClient()
    client.deliveries_summary = [{"id": "d1", "status": "CURRENT"}]
    client.delivery_details = {
        "d1": _make_delivery(
            "d1",
            "CURRENT",
            [
                _make_item("s100", "Dr. Oetker Bistro Baguette", 1),
                _make_item("s100", "Dr. Oetker Bistro Baguette", 1),
                _make_item("s200", "Milch", 1),
            ],
        ),
    }
    result = await parse_pending_orders(client)
    order = result.orders[0]
    assert len(order.items) == 2
    baguette = next(i for i in order.items if i.picnic_id == "s100")
    assert baguette.quantity == 2
    assert result.quantity_map == {"s100": 2, "s200": 1}


async def test_parse_pending_orders_unit_price_from_line_not_article():
    """Unit price = line total / qty; the article's sentinel price is ignored."""
    client = FakePicnicClient()
    client.deliveries_summary = [{"delivery_id": "d1", "status": "CURRENT"}]
    # qty 2, line total 458 -> unit price 229; article carries sentinel 432199.
    client.delivery_details = {
        "d1": _make_delivery("d1", "CURRENT", [_make_item("s100", "Schoko", 2, unit_price=229)]),
    }
    result = await parse_pending_orders(client)
    item = result.orders[0].items[0]
    assert item.price_cents == 229
    assert item.quantity == 2


async def test_parse_pending_orders_total_uses_order_total_with_discount():
    """Delivery total comes from order.total_price (incl. discount), not the
    sum of line prices."""
    client = FakePicnicClient()
    client.deliveries_summary = [{"delivery_id": "d1", "status": "CURRENT"}]
    detail = _make_delivery("d1", "CURRENT", [_make_item("s100", "A", 2, unit_price=229)])
    # Lines sum to 458; pretend a 58c order-level discount -> authoritative 400.
    detail["orders"][0]["total_price"] = 400
    client.delivery_details = {"d1": detail}
    result = await parse_pending_orders(client)
    assert result.orders[0].total_price_cents == 400


async def test_parse_pending_orders_delivery_time_falls_back_to_slot():
    """A CURRENT order has no delivery_time, only a reserved slot window."""
    client = FakePicnicClient()
    client.deliveries_summary = [{"delivery_id": "d1", "status": "CURRENT"}]
    detail = _make_delivery("d1", "CURRENT", [_make_item("s100", "A", 1)])
    del detail["delivery_time"]
    detail["slot"] = {"window_start": "2026-06-08T15:45:00.000+02:00"}
    client.delivery_details = {"d1": detail}
    result = await parse_pending_orders(client)
    assert result.orders[0].delivery_time is not None
    assert result.orders[0].delivery_time.hour == 15


async def test_parse_pending_orders_extracts_promo():
    """LINE-level PRICE/PROMO decorators surface as per-unit promo price + text."""
    client = FakePicnicClient()
    client.deliveries_summary = [{"delivery_id": "d1", "status": "CURRENT"}]
    # qty 2, regular line 458 (unit 229); promo line total 366 (unit 183).
    item = _make_item("s100", "Baguette", 2, unit_price=229,
                      promo_total=366, promo_text="-40% auf 2. Artikel")
    client.delivery_details = {"d1": _make_delivery("d1", "CURRENT", [item])}
    result = await parse_pending_orders(client)
    it = result.orders[0].items[0]
    assert it.price_cents == 229
    assert it.promo_price_cents == 183
    assert it.promo_text == "-40% auf 2. Artikel"


async def test_parse_pending_orders_ignores_non_discount_price_decorator():
    """A PRICE decorator that doesn't undercut the regular price is not a promo."""
    client = FakePicnicClient()
    client.deliveries_summary = [{"delivery_id": "d1", "status": "CURRENT"}]
    item = _make_item("s100", "X", 1, unit_price=199, promo_total=199)
    client.delivery_details = {"d1": _make_delivery("d1", "CURRENT", [item])}
    result = await parse_pending_orders(client)
    assert result.orders[0].items[0].promo_price_cents is None


async def test_parse_pending_orders_empty_when_all_completed():
    client = FakePicnicClient()
    client.deliveries_summary = [{"id": "d1", "status": "COMPLETED"}]
    result = await parse_pending_orders(client)
    assert len(result.orders) == 0
    assert result.quantity_map == {}
