"""Auto-restock service: keeps tracked products topped up in the Picnic cart.

Two entry points:
- check_and_enqueue runs on every inventory decrement for the affected rule.
- reconcile_all re-checks every rule (periodically, and on demand), which
  catches what a decrement never triggers: rules whose product is scanned
  under another EAN than the rule's, adds Picnic refused, rules created or
  linked while already below their minimum.

A rule's stock is the sum over every inventory row of its Picnic product
(see app.services.picnic.ean_links), not just the row of the rule's barcode.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.services.picnic.cart import _parse_cart_quantities
from app.services.picnic.client import PicnicClientProtocol
from app.services.picnic.ean_links import (
    known_picnic_id,
    linked_quantity,
    resolve_ean,
    rule_for_barcode,
    unresolved_inventory,
)
from app.services.picnic.matching import normalize_name
from app.services.picnic.orders import parse_pending_orders

log = logging.getLogger("restock")

# Reading the cart and adding the deficit must not interleave between a
# decrement and a reconcile run, or both add the same deficit. One uvicorn
# worker, so a process-local lock is enough.
restock_lock = asyncio.Lock()


@dataclass(frozen=True)
class RestockResult:
    barcode: str
    added_quantity: int


@dataclass
class ReconcileSummary:
    checked: int = 0
    resolved: int = 0
    added: list[tuple[str, int]] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


async def _cart_and_orders(client: PicnicClientProtocol) -> tuple[dict[str, int], dict[str, int]]:
    """Quantities already in the cart and already on the way, by picnic_id."""
    cart = _parse_cart_quantities(await client.get_cart())
    pending = await parse_pending_orders(client)
    return cart, dict(pending.quantity_map)


def _log_restock(db: AsyncSession, rule: TrackedProduct, current: int, delta: int) -> None:
    # Logged under the rule's barcode: the dashboard prices restocks by
    # joining log.barcode to TrackedProduct.barcode.
    db.add(
        InventoryLog(
            barcode=rule.barcode,
            action="restock_auto",
            details=f"qty→{current}, cart delta={delta}",
        )
    )


async def check_and_enqueue(
    db: AsyncSession,
    barcode: str,
    new_quantity: int,
    *,
    tracked: TrackedProduct | None = None,
    picnic_client: PicnicClientProtocol | None = None,
) -> RestockResult | None:
    """After `barcode` dropped to `new_quantity`, top up its rule in the cart.

    The rule is found by barcode or, failing that, through the barcode's
    Picnic product. Stock counts `new_quantity` plus every other linked row.
    If the cart or the pending orders can't be read, nothing is added: a
    blind add could double up, and the next reconcile run retries.

    The caller owns the transaction; this function does not commit. Pass
    `tracked` if the caller already loaded the rule.

    Returns RestockResult if items were added to the Picnic cart, else None.
    """
    if tracked is None:
        tracked = await rule_for_barcode(db, picnic_client, barcode)
    if tracked is None:
        return None

    current = new_quantity + await linked_quantity(db, tracked, exclude_barcode=barcode)
    if current >= tracked.min_quantity:
        return None

    if not tracked.picnic_id or picnic_client is None:
        log.warning("Cannot restock %s: no picnic_id or no client", barcode)
        return None

    needed = tracked.target_quantity - current
    if needed <= 0:
        return None

    async with restock_lock:
        try:
            cart, on_order_map = await _cart_and_orders(picnic_client)
        except Exception:
            log.warning(
                "Restock %s skipped: cart or pending orders unreadable, reconcile retries",
                barcode,
                exc_info=True,
            )
            return None
        already_in_cart = cart.get(tracked.picnic_id, 0)
        on_order = on_order_map.get(tracked.picnic_id, 0)

        delta = needed - already_in_cart - on_order
        if delta <= 0:
            log.info(
                "Restock skip %s: need %d, already %d in cart, %d on order",
                barcode, needed, already_in_cart, on_order,
            )
            return None

        try:
            await picnic_client.add_product(tracked.picnic_id, count=delta)
        except Exception:
            log.exception("Failed to add %s to Picnic cart", tracked.picnic_id)
            return None

    _log_restock(db, tracked, current, delta)
    log.info(
        "Restock %s: added %d to Picnic cart (was %d in cart, %d on order, need %d)",
        barcode, delta, already_in_cart, on_order, needed,
    )
    return RestockResult(barcode=barcode, added_quantity=delta)


async def _link_inventory(
    db: AsyncSession,
    client: PicnicClientProtocol,
    rules: list[TrackedProduct],
    *,
    lookup_limit: int,
    lookup_delay_s: float,
) -> int:
    """Link unlinked inventory EANs; returns how many map to a Picnic product.

    A GTIN lookup costs Picnic several requests and a few hundred in a row got
    the account briefly blocked (2026-10-03), so live lookups are spaced and
    capped per run. Rows whose name resembles a tracked product go first.
    """
    rule_names = [normalize_name(r.name) for r in rules]

    def likeness(name: str) -> float:
        own = normalize_name(name)
        return max((fuzz.token_set_ratio(own, r) for r in rule_names), default=0.0)

    pending = sorted(await unresolved_inventory(db), key=lambda row: -likeness(row[1]))
    linked = lookups = 0
    for ean, _name in pending:
        known, picnic_id = await known_picnic_id(db, ean)
        if not known:
            if lookups >= lookup_limit:
                continue  # catalog-known rows further down cost nothing
            lookups += 1
            picnic_id = await resolve_ean(db, client, ean)
            if lookup_delay_s:
                await asyncio.sleep(lookup_delay_s)
        if picnic_id is not None:
            linked += 1
    return linked


async def reconcile_all(
    db: AsyncSession,
    client: PicnicClientProtocol,
    *,
    lookup_limit: int = 100,
    lookup_delay_s: float = 1.0,
) -> ReconcileSummary:
    """Link unlinked inventory EANs, then top up every rule below its minimum.

    Raises if the cart or the pending orders can't be read -- nothing is
    added blind. A refused add is reported in `failed` and not logged as a
    restock. The caller owns the transaction.
    """
    summary = ReconcileSummary()
    rules = list(
        (
            await db.execute(select(TrackedProduct).order_by(TrackedProduct.created_at))
        ).scalars().all()
    )
    summary.checked = len(rules)
    summary.resolved = await _link_inventory(
        db, client, rules, lookup_limit=lookup_limit, lookup_delay_s=lookup_delay_s
    )
    if not rules:
        return summary

    async with restock_lock:
        cart, on_order_map = await _cart_and_orders(client)
        for rule in rules:
            current = await linked_quantity(db, rule)
            if current >= rule.min_quantity:
                continue
            delta = (
                rule.target_quantity
                - current
                - cart.get(rule.picnic_id, 0)
                - on_order_map.get(rule.picnic_id, 0)
            )
            if delta <= 0:
                continue
            try:
                await client.add_product(rule.picnic_id, count=delta)
            except Exception:
                log.exception("Reconcile: failed to add %s to Picnic cart", rule.picnic_id)
                summary.failed.append(rule.name)
                continue
            # Two rules can share a product (placeholder + real barcode).
            cart[rule.picnic_id] = cart.get(rule.picnic_id, 0) + delta
            _log_restock(db, rule, current, delta)
            summary.added.append((rule.name, delta))

    log.info(
        "Reconcile: %d rules, %d EANs linked, added %s, failed %s",
        summary.checked, summary.resolved, summary.added, summary.failed,
    )
    return summary
