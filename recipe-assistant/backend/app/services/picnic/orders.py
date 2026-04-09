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


async def get_recently_ordered_products(
    client: PicnicClientProtocol,
) -> list[dict]:
    """Get unique products from recent deliveries, enriched via get_article().

    Delivery items lack price/image data, so we fetch each product's catalog
    entry to get display_price and image_id.
    """
    summaries = await client.get_deliveries()
    seen: dict[str, dict] = {}  # picnic_id -> product info

    for summary in summaries[:5]:  # last 5 deliveries
        delivery_id = summary.get("delivery_id") or summary.get("id")
        if not delivery_id:
            continue
        try:
            detail = await client.get_delivery(delivery_id)
        except Exception:
            continue

        flat_items = _flatten_delivery_items(detail)
        for fi in flat_items:
            pid = fi["picnic_id"]
            if pid not in seen:
                seen[pid] = {
                    "picnic_id": pid,
                    "name": fi["name"],
                    "unit_quantity": fi.get("unit_quantity"),
                    "image_id": fi.get("image_id"),
                    "price_cents": fi.get("price_cents"),
                }

    # Limit to 20 most recent unique products
    import asyncio
    products = list(seen.values())[:20]

    # Enrich in parallel — delivery items lack price/image
    async def _enrich(product: dict) -> None:
        if product.get("price_cents") and product.get("image_id"):
            return
        try:
            article = await client.get_article(product["picnic_id"])
            if not product.get("image_id"):
                product["image_id"] = article.get("image_id")
            if not product.get("price_cents"):
                product["price_cents"] = article.get("display_price")
            if not product.get("unit_quantity"):
                product["unit_quantity"] = article.get("unit_quantity")
        except Exception:
            log.debug("Could not enrich product %s", product["picnic_id"])

    await asyncio.gather(*[_enrich(p) for p in products])
    return products
