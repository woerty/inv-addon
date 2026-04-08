"""Auto-restock service: checks inventory decrements against tracked-product
thresholds and adds directly to the Picnic cart when consumption drops below
`min_quantity`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.services.picnic.cart import _parse_cart_quantities
from app.services.picnic.client import PicnicClientProtocol

log = logging.getLogger("restock")


@dataclass(frozen=True)
class RestockResult:
    barcode: str
    added_quantity: int


async def check_and_enqueue(
    db: AsyncSession,
    barcode: str,
    new_quantity: int,
    *,
    tracked: TrackedProduct | None = None,
    picnic_client: PicnicClientProtocol | None = None,
) -> RestockResult | None:
    """Check if `new_quantity` crossed the threshold for `barcode` and
    add the deficit directly to the Picnic cart.

    If no picnic_client is provided, or the TrackedProduct has no picnic_id,
    a warning is logged and None is returned.

    The caller owns the transaction; this function does not commit.

    If the caller already has the TrackedProduct row (e.g. they queried
    it to make a delete decision), pass it via the `tracked` kwarg to
    avoid a duplicate SELECT. Otherwise the function queries it itself.

    Returns None if no tracked rule exists, new_quantity >= min_quantity,
    no picnic_id/client, or the cart already has enough. Returns
    RestockResult(...) if items were added to the Picnic cart.
    """
    if tracked is None:
        result = await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
        tracked = result.scalar_one_or_none()

    if tracked is None:
        return None

    if new_quantity >= tracked.min_quantity:
        return None

    if not tracked.picnic_id or picnic_client is None:
        log.warning("Cannot restock %s: no picnic_id or no client", barcode)
        return None

    needed = tracked.target_quantity - new_quantity
    if needed <= 0:
        return None

    # Check what's already in cart to avoid over-ordering (dedup)
    already_in_cart = 0
    try:
        raw_cart = await picnic_client.get_cart()
        cart_quantities = _parse_cart_quantities(raw_cart)
        already_in_cart = cart_quantities.get(tracked.picnic_id, 0)
    except Exception:
        log.warning("Failed to fetch cart for restock dedup, proceeding anyway")

    delta = needed - already_in_cart
    if delta <= 0:
        log.info(
            "Restock skip %s: need %d, already %d in cart",
            barcode,
            needed,
            already_in_cart,
        )
        return None

    try:
        await picnic_client.add_product(tracked.picnic_id, count=delta)
    except Exception:
        log.exception("Failed to add %s to Picnic cart", tracked.picnic_id)
        return None

    # Log the action
    db.add(
        InventoryLog(
            barcode=barcode,
            action="restock_auto",
            details=f"qty→{new_quantity}, cart delta={delta}",
        )
    )

    log.info(
        "Restock %s: added %d to Picnic cart (was %d in cart, need %d)",
        barcode,
        delta,
        already_in_cart,
        needed,
    )
    return RestockResult(barcode=barcode, added_quantity=delta)
