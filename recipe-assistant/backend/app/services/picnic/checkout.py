"""Delivery-slot selection and order placement.

The slot/checkout endpoints are missing from python-picnic-api2 v1.3.4, so
`PicnicClient` calls them as raw `_post`/`_get` requests. The full ordering flow:

    set_delivery_slot -> checkout_start -> initiate_payment -> poll status

`place_order` orchestrates the last three (the genuinely irreversible writes) so
the HTTP/UI layer only sees success or a clear `PicnicCheckoutError`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.schemas.picnic import (
    DeliverySlot,
    DeliverySlotsResponse,
    OrderPlacedResult,
)
from app.services.picnic.client import PicnicClientProtocol

log = logging.getLogger("picnic.checkout")

# Picnic flags some carts as needing verification (e.g. alcohol); the documented
# resolve value re-runs checkout/start with the age confirmation set.
_AGE_RESOLVE_KEY = "age_verified"

# Terminal checkout statuses. The live status shape was not pinned down (the order
# succeeds — cart clears — before our poll observes a terminal value), so accept a
# generous set of success/failure tokens, checked case-insensitively.
_DONE_STATUSES = {"FINISHED", "COMPLETED", "DONE", "SUCCESS", "PAID"}
_FAILED_STATUSES = {"FAILED", "CANCELLED", "CANCELED", "ERROR", "REJECTED", "DECLINED"}


class PicnicCheckoutError(Exception):
    """Checkout could not be completed (MOV not met, 3DS required, timeout, ...)."""


async def parse_delivery_slots(client: PicnicClientProtocol) -> DeliverySlotsResponse:
    """Fetch available delivery slots plus the cart total for MOV comparison."""
    raw = await client.get_delivery_slots()
    cart = await client.get_cart()

    slots = [
        DeliverySlot(
            slot_id=s["slot_id"],
            window_start=s["window_start"],
            window_end=s["window_end"],
            cut_off_time=s.get("cut_off_time"),
            is_available=s.get("is_available", True),
            selected=s.get("selected", False),
            reserved=s.get("reserved", False),
            minimum_order_value_cents=s.get("minimum_order_value"),
        )
        for s in raw.get("delivery_slots", [])
        if s.get("slot_id")
    ]
    slots.sort(key=lambda s: s.window_start)

    selected_slot_id = (cart.get("selected_slot") or {}).get("slot_id")
    if selected_slot_id is None:
        selected_slot_id = next((s.slot_id for s in slots if s.selected), None)

    total = cart.get("total_price")
    if total is None:
        total = cart.get("checkout_total_price", 0)

    return DeliverySlotsResponse(
        slots=slots,
        selected_slot_id=selected_slot_id,
        cart_total_price_cents=total or 0,
    )


def _resolve_key(result: dict) -> str | None:
    """Pull a resolve key out of a checkout/start response, if present.

    Picnic returns it top-level or nested under ``error`` depending on the issue
    (we never observed the exact shape live, so check both)."""
    return result.get("resolve_key") or (result.get("error") or {}).get("resolve_key")


async def place_order(
    client: PicnicClientProtocol,
    *,
    max_attempts: int = 20,
    interval_s: float = 1.5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> OrderPlacedResult:
    """Place the current cart as an order: checkout -> pay -> poll until FINISHED."""
    cart = await client.get_cart()
    mts = cart.get("mts", 0)

    checkout = await client.checkout_start(mts)
    if "order_id" not in checkout and _resolve_key(checkout):
        # e.g. age verification required; re-run with the confirmation set.
        checkout = await client.checkout_start(mts, resolve_key=_AGE_RESOLVE_KEY)

    order_id = checkout.get("order_id")
    if not order_id:
        message = (checkout.get("error") or {}).get("message") or "Checkout fehlgeschlagen"
        raise PicnicCheckoutError(message)

    payment = await client.initiate_payment(order_id)
    if payment.get("issuer_authentication_url"):
        raise PicnicCheckoutError(
            "Diese Bestellung erfordert eine Zahlungsbestätigung (3-D Secure). "
            "Bitte in der Picnic-App abschließen."
        )

    transaction_id = payment.get("transaction_id") or payment.get("payment_id") or order_id
    for attempt in range(max_attempts):
        raw = await client.get_checkout_status(transaction_id)
        status = (raw.get("checkout_status") or raw.get("status") or "").upper()
        if status in _DONE_STATUSES:
            return OrderPlacedResult(
                order_id=order_id,
                status="FINISHED",
                total_price_cents=checkout.get("total_price"),
            )
        if status in _FAILED_STATUSES:
            raise PicnicCheckoutError("Die Bestellung wurde von Picnic abgelehnt.")
        if attempt < max_attempts - 1:
            await sleep(interval_s)

    # Order was submitted (we have an order_id and payment was accepted without
    # 3DS) but no terminal status arrived in time. Verified live: the cart is in
    # fact cleared and the items land on the order, so reporting failure here
    # would be wrong (and risk a duplicate re-order). Report it as submitted.
    return OrderPlacedResult(
        order_id=order_id,
        status="PROCESSING",
        total_price_cents=checkout.get("total_price"),
    )
