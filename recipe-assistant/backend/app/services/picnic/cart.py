from __future__ import annotations

import logging

from app.schemas.picnic import (
    CartItemResponse,
    CartResponse,
)
from app.services.picnic.client import PicnicClientProtocol

log = logging.getLogger("picnic.cart")


def _parse_cart_quantities(raw: dict) -> dict[str, int]:
    """Parse raw cart response into a picnic_id -> total quantity map."""
    quantities: dict[str, int] = {}
    for line in raw.get("items", []):
        inner = line.get("items", [])
        if inner:
            product = inner[0]
            picnic_id = product.get("id", line.get("id", ""))
            qty_raw = product.get("decorators", [])
            quantity = 1
            for d in qty_raw:
                if d.get("type") == "QUANTITY":
                    quantity = d.get("quantity", 1)
                    break
        else:
            picnic_id = line.get("id", "")
            quantity = line.get("quantity", line.get("count", 1))
        if picnic_id:
            quantities[picnic_id] = quantities.get(picnic_id, 0) + quantity
    return quantities


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
