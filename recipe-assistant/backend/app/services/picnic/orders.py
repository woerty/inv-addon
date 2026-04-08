from __future__ import annotations

import logging
from collections import defaultdict

from app.schemas.picnic import (
    PendingOrder,
    PendingOrderItem,
    PendingOrdersResponse,
)
from app.services.picnic.client import PicnicClientProtocol
from app.services.picnic.import_flow import _flatten_delivery_items, _parse_delivery_time

log = logging.getLogger(__name__)

_COMPLETED_STATUSES = {"COMPLETED", "CANCELLED"}


async def parse_pending_orders(
    client: PicnicClientProtocol,
) -> PendingOrdersResponse:
    """Fetch all non-completed deliveries and build a quantity map."""
    summaries = await client.get_deliveries()
    pending = [s for s in summaries if s.get("status", "").upper() not in _COMPLETED_STATUSES]

    orders: list[PendingOrder] = []
    quantity_map: dict[str, int] = defaultdict(int)

    for summary in pending:
        delivery_id = summary["id"]
        try:
            detail = await client.get_delivery(delivery_id)
        except Exception:
            log.warning("Failed to fetch delivery %s, skipping", delivery_id)
            continue

        flat_items = _flatten_delivery_items(detail)
        items: list[PendingOrderItem] = []
        for fi in flat_items:
            quantity_map[fi["picnic_id"]] += fi["quantity"]
            items.append(
                PendingOrderItem(
                    picnic_id=fi["picnic_id"],
                    name=fi["name"],
                    quantity=fi["quantity"],
                    image_id=fi.get("image_id"),
                    price_cents=fi.get("price_cents"),
                )
            )

        orders.append(
            PendingOrder(
                delivery_id=delivery_id,
                status=summary.get("status", "UNKNOWN"),
                delivery_time=_parse_delivery_time(detail),
                total_items=sum(i.quantity for i in items),
                items=items,
            )
        )

    return PendingOrdersResponse(orders=orders, quantity_map=dict(quantity_map))
