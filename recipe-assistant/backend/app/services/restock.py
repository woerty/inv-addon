"""Auto-restock service: checks inventory decrements against tracked-product
thresholds and seeds the shopping list when consumption drops below `min_quantity`.

Add-only semantics: we only add or raise shopping list quantities, never
remove or reduce. Rationale documented in
docs/superpowers/specs/2026-04-05-auto-restock-design.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import InventoryLog
from app.models.picnic import ShoppingListItem
from app.models.tracked_product import TrackedProduct

log = logging.getLogger("restock")


@dataclass(frozen=True)
class RestockResult:
    barcode: str
    added_quantity: int
    shopping_list_item_id: int


async def check_and_enqueue(
    db: AsyncSession,
    barcode: str,
    new_quantity: int,
) -> RestockResult | None:
    """Check if `new_quantity` crossed the threshold for `barcode` and
    upsert the shopping list accordingly.

    MUST be called by the caller AFTER decrementing inventory, BEFORE
    db.commit(). Runs in the caller's transaction — either both writes
    land or neither. This function does not commit.

    Returns None if no tracked rule exists or if new_quantity >= min_quantity.
    Returns RestockResult(...) if the shopping list was upserted.
    """
    tracked = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()
    if tracked is None:
        return None
    if new_quantity >= tracked.min_quantity:
        return None

    needed = tracked.target_quantity - new_quantity
    # Defensive: target > min > 0 and new_quantity < min, so needed > 0. If
    # something upstream bypassed the check constraints, fail loudly.
    if needed <= 0:
        raise ValueError(
            f"tracked_products row for {barcode} is inconsistent: "
            f"target={tracked.target_quantity} new_qty={new_quantity}"
        )

    # Dedup against any existing shopping list entry for this barcode. Pick
    # the most recent one if multiple somehow exist; raise its quantity if
    # smaller, leave it alone if larger.
    existing = (
        await db.execute(
            select(ShoppingListItem)
            .where(ShoppingListItem.inventory_barcode == barcode)
            .order_by(ShoppingListItem.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.quantity < needed:
            existing.quantity = needed
        item_id = existing.id
    else:
        new_item = ShoppingListItem(
            inventory_barcode=barcode,
            picnic_id=tracked.picnic_id,
            name=tracked.name,
            quantity=needed,
        )
        db.add(new_item)
        await db.flush()
        item_id = new_item.id

    db.add(
        InventoryLog(
            barcode=barcode,
            action="restock_auto",
            details=f"qty→{new_quantity}, list qty={needed}",
        )
    )

    log.info(
        "restock_auto barcode=%s new_qty=%d needed=%d item_id=%s",
        barcode,
        new_quantity,
        needed,
        item_id,
    )
    return RestockResult(
        barcode=barcode,
        added_quantity=needed,
        shopping_list_item_id=item_id,
    )
