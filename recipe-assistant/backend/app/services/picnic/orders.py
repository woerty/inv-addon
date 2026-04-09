from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

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
    db: AsyncSession | None = None,
) -> list[dict]:
    """Get unique products from recent deliveries, enriched from DB cache.

    Delivery items lack price/image data. We enrich from the picnic_products
    cache table (populated by search and import) — no extra API calls needed.
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

    products = list(seen.values())[:20]

    # Enrich from DB cache (fast, no API calls)
    if db:
        from sqlalchemy import select
        from app.models.picnic import PicnicProduct

        pids = [p["picnic_id"] for p in products]
        result = await db.execute(
            select(PicnicProduct).where(PicnicProduct.picnic_id.in_(pids))
        )
        cache = {row.picnic_id: row for row in result.scalars().all()}

        for product in products:
            cached = cache.get(product["picnic_id"])
            if cached:
                if not product.get("image_id"):
                    product["image_id"] = cached.image_id
                if not product.get("price_cents"):
                    product["price_cents"] = cached.last_price_cents
                if not product.get("unit_quantity"):
                    product["unit_quantity"] = cached.unit_quantity

    return products
