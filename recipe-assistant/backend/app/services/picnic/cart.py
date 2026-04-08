from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.picnic import PicnicProduct, ShoppingListItem
from app.schemas.picnic import (
    CartItemResponse,
    CartResponse,
    CartSyncItemResult,
    CartSyncResponse,
    ShoppingListItemResponse,
)
from app.services.picnic.catalog import (
    PicnicProductData,
    get_product,
    get_product_by_ean,
    upsert_product,
)
from app.services.picnic.client import PicnicClientProtocol

log = logging.getLogger("picnic.cart")


@dataclass(frozen=True)
class Resolution:
    picnic_id: str | None
    picnic_name: str | None


async def _resolve(
    session: AsyncSession,
    client: PicnicClientProtocol,
    item: ShoppingListItem,
) -> Resolution:
    """Three-step resolution:

    1. If the shopping list row has an explicit picnic_id, fetch its name from
       the cache and return immediately.
    2. If the row has an inventory_barcode and the picnic_products cache already
       has an entry for that EAN, use it.
    3. Otherwise, if the row has an inventory_barcode, call get_article_by_gtin
       live, cache the result (or the absence of a hit), and return.
    """
    if item.picnic_id:
        cached = await get_product(session, item.picnic_id)
        return Resolution(picnic_id=item.picnic_id, picnic_name=cached.name if cached else None)

    if item.inventory_barcode:
        cached = await get_product_by_ean(session, item.inventory_barcode)
        if cached:
            return Resolution(picnic_id=cached.picnic_id, picnic_name=cached.name)

        result = await client.get_article_by_gtin(item.inventory_barcode)
        if result and result.get("id") and result.get("name"):
            await upsert_product(
                session,
                PicnicProductData(
                    picnic_id=result["id"],
                    ean=item.inventory_barcode,
                    name=result["name"],
                    unit_quantity=None,
                    image_id=None,
                    last_price_cents=None,
                ),
            )
            return Resolution(picnic_id=result["id"], picnic_name=result["name"])

    return Resolution(picnic_id=None, picnic_name=None)


async def resolve_shopping_list_status(
    session: AsyncSession,
    client: PicnicClientProtocol,
) -> list[ShoppingListItemResponse]:
    """Return all shopping list items with their Picnic resolution status.

    This may trigger live get_article_by_gtin calls for uncached items. Results
    are cached in picnic_products for future calls.

    The caller owns the commit; this function only flushes so cache upserts
    are visible within the transaction.
    """
    result = await session.execute(select(ShoppingListItem).order_by(ShoppingListItem.added_at))
    items = result.scalars().all()

    out: list[ShoppingListItemResponse] = []
    for item in items:
        resolution = await _resolve(session, client, item)
        status: Literal["mapped", "unavailable"] = (
            "mapped" if resolution.picnic_id else "unavailable"
        )
        out.append(
            ShoppingListItemResponse(
                id=item.id,
                inventory_barcode=item.inventory_barcode,
                picnic_id=resolution.picnic_id,
                picnic_name=resolution.picnic_name,
                name=item.name,
                quantity=item.quantity,
                picnic_status=status,
                added_at=item.added_at,
            )
        )

    await session.flush()  # persist any cache upserts from live lookups
    return out


async def sync_shopping_list_to_cart(
    session: AsyncSession,
    client: PicnicClientProtocol,
) -> CartSyncResponse:
    """Push every mapped shopping list item into the real Picnic cart.

    Per-item tracking; does NOT roll back on partial failure. Items that succeed
    stay in the Picnic cart; items that failed are reported.

    The caller owns the commit; this function only flushes so cache upserts
    from any tier-3 lookups are visible within the transaction.
    """
    # Re-resolves each item (not memoized from a prior resolve_shopping_list_status
    # call): the shopping list may have been edited between the two requests, and
    # cached resolutions make tier-2 hits essentially free.
    db_items = (await session.execute(select(ShoppingListItem))).scalars().all()

    results: list[CartSyncItemResult] = []
    added_count = 0
    failed_count = 0
    skipped_count = 0

    for item in db_items:
        resolution = await _resolve(session, client, item)
        if not resolution.picnic_id:
            results.append(
                CartSyncItemResult(
                    shopping_list_id=item.id,
                    picnic_id=None,
                    status="skipped_unmapped",
                    failure_reason="nicht bei Picnic verfügbar",
                )
            )
            skipped_count += 1
            continue

        try:
            await client.add_product(resolution.picnic_id, count=item.quantity)
            results.append(
                CartSyncItemResult(
                    shopping_list_id=item.id,
                    picnic_id=resolution.picnic_id,
                    status="added",
                    failure_reason=None,
                )
            )
            added_count += 1
        except Exception as e:
            # Broad catch so one failed item doesn't abort the batch, but log
            # so programming bugs don't disguise themselves as Picnic errors.
            log.warning(
                "add_product failed for picnic_id=%s: %s",
                resolution.picnic_id,
                e,
            )
            reason = str(e) or "http_error"
            if "unavailable" in reason.lower():
                reason = "product_unavailable"
            results.append(
                CartSyncItemResult(
                    shopping_list_id=item.id,
                    picnic_id=resolution.picnic_id,
                    status="failed",
                    failure_reason=reason,
                )
            )
            failed_count += 1

    await session.flush()

    return CartSyncResponse(
        results=results,
        added_count=added_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
    )


async def parse_cart_response(
    client: PicnicClientProtocol,
) -> CartResponse:
    """Fetch cart from Picnic and return structured response."""
    raw = await client.get_cart()
    items: list[CartItemResponse] = []
    total_price = 0

    for line in raw.get("items", []):
        inner = line.get("items", [])
        if inner:
            product = inner[0]
            picnic_id = product.get("id", line.get("id", ""))
            name = product.get("name", line.get("name", "unknown"))
            qty_raw = product.get("decorators", [])
            quantity = 1
            for d in qty_raw:
                if d.get("type") == "QUANTITY":
                    quantity = d.get("quantity", 1)
                    break
            unit_quantity = product.get("unit_quantity")
            image_id = product.get("image_id")
            price_cents = product.get("display_price")
        else:
            picnic_id = line.get("id", "")
            name = line.get("name", "unknown")
            quantity = line.get("quantity", line.get("count", 1))
            unit_quantity = line.get("unit_quantity")
            image_id = line.get("image_id")
            price_cents = line.get("display_price")

        item_total = (price_cents or 0) * quantity
        total_price += item_total
        items.append(
            CartItemResponse(
                picnic_id=picnic_id,
                name=name,
                quantity=quantity,
                unit_quantity=unit_quantity,
                image_id=image_id,
                price_cents=price_cents,
                total_price_cents=item_total,
            )
        )

    return CartResponse(
        items=items,
        total_items=sum(i.quantity for i in items),
        total_price_cents=total_price,
    )
