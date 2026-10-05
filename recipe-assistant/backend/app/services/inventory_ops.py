"""Inventory decrements shared by the HTTP routes and the ass3 link.

The scanner's scan-out and an ass3 "aufgebraucht" must take the same path
(zombie rows for tracked products, restock check, log entry), so the logic
lives here instead of in the router.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem
from app.models.log import InventoryLog
from app.services.custom_products import is_custom_barcode
from app.services.picnic.client import PicnicClientProtocol
from app.services.picnic.ean_links import rule_for_barcode
from app.services.restock import check_and_enqueue


async def log_action(db: AsyncSession, barcode: str, action: str, details: str | None = None) -> None:
    db.add(InventoryLog(barcode=barcode, action=action, details=details))


async def apply_decrement(
    db: AsyncSession,
    item: InventoryItem,
    new_quantity: int,
    *,
    action: str,
    log_details: str,
    picnic_client: PicnicClientProtocol | None = None,
    restock: bool = True,
) -> bool:
    """Apply a quantity decrement plus tracking-aware rules.

    - Sets item.quantity = new_quantity.
    - If new_quantity == 0 and the product has a TrackedProduct rule (on
      this barcode or on another EAN of the same Picnic product), the row
      is kept (zombie); otherwise it is deleted.
    - Runs restock.check_and_enqueue when the row is kept (adds directly
      to the Picnic cart if picnic_client is provided); skipped on the
      delete branch because there is no tracked rule to check against.
      restock=False skips it too, for a caller that decrements several
      times in a row and checks once on the last one.
    - Writes an InventoryLog entry with the given action and details.

    Returns True if the inventory row was deleted, False if it was kept.
    Caller must still commit the transaction.
    """
    tracked = await rule_for_barcode(db, item.barcode)

    if new_quantity <= 0 and tracked is None and not is_custom_barcode(item.barcode):
        await log_action(db, item.barcode, action, log_details)
        await db.delete(item)
        return True

    item.quantity = new_quantity
    await log_action(db, item.barcode, action, log_details)
    if restock:
        await check_and_enqueue(
            db,
            barcode=item.barcode,
            new_quantity=new_quantity,
            tracked=tracked,
            picnic_client=picnic_client,
        )
    return False


@dataclass(frozen=True)
class ScanOutResult:
    barcode: str
    name: str
    remaining_quantity: int
    deleted: bool


async def scan_out_one(
    db: AsyncSession,
    barcode: str,
    *,
    picnic_client: PicnicClientProtocol | None,
    restock: bool = True,
) -> ScanOutResult | None:
    """One scan-out: take one unit of `barcode` out of the inventory.

    Returns None if no inventory row has this barcode. The caller commits.
    """
    item = (
        await db.execute(select(InventoryItem).where(InventoryItem.barcode == barcode))
    ).scalar_one_or_none()
    if item is None:
        return None

    name = item.name
    old_qty = item.quantity
    new_qty = old_qty - 1
    deleted = await apply_decrement(
        db,
        item,
        new_qty,
        action="scan-out",
        log_details=(
            f"quantity: {old_qty} → {new_qty}"
            if new_qty > 0
            else "removed last item"
        ),
        picnic_client=picnic_client,
        restock=restock,
    )
    return ScanOutResult(
        barcode=barcode,
        name=name,
        remaining_quantity=max(new_qty, 0),
        deleted=deleted,
    )
