"""Link scanned EANs to Picnic products, and tracked rules to inventory rows.

A tracked rule names one barcode, but the same Picnic product is often sold
under several EANs (private labels change EANs between producers), and rules
subscribed from the Picnic store carry only a ``picnic:<id>`` placeholder.
Matching through picnic_id lets every pack of the product count.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem
from app.models.picnic import PicnicEanLink
from app.models.tracked_product import TrackedProduct
from app.services.custom_products import is_custom_barcode
from app.services.picnic.catalog import get_product_by_ean
from app.services.picnic.client import PicnicClientProtocol
from app.services.tracked_products import is_synthetic_barcode


# "Not on Picnic" can change when Picnic lists the product later.
MISS_RECHECK_AFTER = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _linkable(ean: str) -> bool:
    return not (is_custom_barcode(ean) or is_synthetic_barcode(ean))


def _is_settled(link: PicnicEanLink) -> bool:
    return link.picnic_id is not None or link.checked_at > _now() - MISS_RECHECK_AFTER


async def _store(db: AsyncSession, ean: str, picnic_id: str | None) -> None:
    link = await db.get(PicnicEanLink, ean)
    if link is None:
        db.add(PicnicEanLink(ean=ean, picnic_id=picnic_id, checked_at=_now()))
    else:
        link.picnic_id = picnic_id
        link.checked_at = _now()
    await db.flush()


async def stored_picnic_id(db: AsyncSession, ean: str) -> tuple[bool, str | None]:
    """(known, picnic_id) from a settled link or the catalog's EAN pairing.

    Read-only and never asks Picnic: request paths (decrements, imports) use
    this, so a bulk import or a slow Picnic can't turn into a burst of live
    lookups. Live linking happens only in the throttled reconcile.
    """
    if not _linkable(ean):
        return True, None
    link = await db.get(PicnicEanLink, ean)
    if link is not None and _is_settled(link):
        return True, link.picnic_id
    cached = await get_product_by_ean(db, ean)
    if cached is not None:
        return True, cached.picnic_id
    return False, None


async def link_ean(db: AsyncSession, client: PicnicClientProtocol, ean: str) -> str | None:
    """Store the link for `ean`, asking Picnic only if nothing is known.

    Lookup errors propagate and nothing is stored, so a throttled or failing
    Picnic never records "not on Picnic".
    """
    known, picnic_id = await stored_picnic_id(db, ean)
    if not known:
        picnic_id = await client.gtin_picnic_id(ean)
    if _linkable(ean):
        await _store(db, ean, picnic_id)
    return picnic_id


async def unresolved_inventory(db: AsyncSession) -> list[tuple[str, str]]:
    """(barcode, name) of inventory rows without a settled link."""
    rows = (
        await db.execute(
            select(InventoryItem.barcode, InventoryItem.name, PicnicEanLink)
            .outerjoin(PicnicEanLink, PicnicEanLink.ean == InventoryItem.barcode)
            .order_by(InventoryItem.id)
        )
    ).all()
    return [
        (barcode, name)
        for barcode, name, link in rows
        if _linkable(barcode) and (link is None or not _is_settled(link))
    ]


async def rule_for_barcode(db: AsyncSession, barcode: str) -> TrackedProduct | None:
    """The rule tracking `barcode`: by its own barcode, else by its Picnic product."""
    rule = await db.get(TrackedProduct, barcode)
    if rule is not None:
        return rule
    _known, picnic_id = await stored_picnic_id(db, barcode)
    if picnic_id is None:
        return None
    rules = (
        await db.execute(
            select(TrackedProduct)
            .where(TrackedProduct.picnic_id == picnic_id)
            .order_by(TrackedProduct.created_at)
        )
    ).scalars().all()
    # Prefer a rule on a real barcode over a picnic: placeholder.
    return next((r for r in rules if not is_synthetic_barcode(r.barcode)), rules[0] if rules else None)


def _linked_rows_filter(rule: TrackedProduct):
    linked_eans = select(PicnicEanLink.ean).where(PicnicEanLink.picnic_id == rule.picnic_id)
    return or_(InventoryItem.barcode == rule.barcode, InventoryItem.barcode.in_(linked_eans))


async def linked_barcodes(db: AsyncSession, rule: TrackedProduct) -> list[str]:
    """Inventory barcodes counted towards `rule`."""
    return list(
        (
            await db.execute(
                select(InventoryItem.barcode)
                .where(_linked_rows_filter(rule))
                .order_by(InventoryItem.barcode)
            )
        ).scalars()
    )


async def linked_quantity(
    db: AsyncSession, rule: TrackedProduct, *, exclude_barcode: str | None = None
) -> int:
    """Stock of `rule`'s product across every linked inventory row."""
    query = select(func.coalesce(func.sum(InventoryItem.quantity), 0)).where(
        _linked_rows_filter(rule)
    )
    if exclude_barcode is not None:
        query = query.where(InventoryItem.barcode != exclude_barcode)
    return int(await db.scalar(query))
