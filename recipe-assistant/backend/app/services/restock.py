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
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import InventoryLog
from app.models.picnic import PicnicDeliveryImport
from app.models.tracked_product import TrackedProduct
from app.services.picnic.cart import _parse_cart_quantities
from app.services.picnic.client import PicnicClientProtocol
from app.services.picnic.ean_links import (
    link_ean,
    linked_quantity,
    rule_for_barcode,
    stored_picnic_id,
    unresolved_inventory,
)
from app.services.picnic.import_flow import _flatten_delivery_items, _parse_delivery_time
from app.services.picnic.matching import normalize_name

log = logging.getLogger("restock")

# Reading the cart and adding the deficit must not interleave between a
# decrement and a reconcile run, or both add the same deficit. One uvicorn
# worker, so process-local locks are enough.
restock_lock = asyncio.Lock()
# One reconcile at a time (scheduler vs. "Jetzt prüfen"); it is also the
# only writer of picnic_ean_links, so links never race on insert.
reconcile_lock = asyncio.Lock()

# A delivered order stays "on its way" until it is booked into the
# inventory. Deliveries are scanned in shortly after arrival rather than
# imported, so an import record can't be the signal; a day is.
JUST_DELIVERED = timedelta(hours=24)

# A still-unlinked inventory row whose name scores this high against a rule
# probably is that product; topping the rule up without it would overshoot.
# Real pairs scored 92-100 on live data, unrelated products <= 54.
LIKELY_SAME_PRODUCT = 85


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
    #: Rules left alone this run because a row that looks like their product
    #: is not linked yet.
    skipped: list[str] = field(default_factory=list)


async def _incoming(db: AsyncSession, client: PicnicClientProtocol) -> dict[str, int]:
    """Quantities on their way home, by picnic_id: open deliveries plus those
    delivered within JUST_DELIVERED and not imported. Raises if any of them
    can't be read -- an undercount here means a duplicate order."""
    imported = set((await db.execute(select(PicnicDeliveryImport.delivery_id))).scalars())
    cutoff = datetime.now(UTC) - JUST_DELIVERED
    incoming: dict[str, int] = defaultdict(int)
    for summary in await client.get_deliveries():
        status = (summary.get("status") or "").upper()
        delivery_id = summary.get("delivery_id") or summary.get("id")
        if status == "CANCELLED" or not delivery_id:
            continue
        if status == "COMPLETED":
            delivered_at = _parse_delivery_time(summary)
            if delivered_at is not None and delivered_at.tzinfo is None:
                delivered_at = delivered_at.replace(tzinfo=UTC)
            if delivery_id in imported or delivered_at is None or delivered_at < cutoff:
                continue
        detail = await client.get_delivery(delivery_id)
        for item in _flatten_delivery_items(detail):
            incoming[item["picnic_id"]] += item["quantity"]
    return dict(incoming)


async def _cart_and_incoming(
    db: AsyncSession, client: PicnicClientProtocol
) -> tuple[dict[str, int], dict[str, int]]:
    """Quantities already in the cart and already on the way, by picnic_id."""
    cart = _parse_cart_quantities(await client.get_cart())
    return cart, await _incoming(db, client)


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
    stored Picnic link (no live lookup on this path; the reconcile links new
    EANs). Stock counts `new_quantity` plus every other linked row. If the
    cart or what's on its way can't be read, nothing is added: a blind add
    could double up, and the next reconcile run retries.

    The caller owns the transaction; this function does not commit. Pass
    `tracked` if the caller already loaded the rule.

    Returns RestockResult if items were added to the Picnic cart, else None.
    """
    if tracked is None:
        tracked = await rule_for_barcode(db, barcode)
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
            cart, incoming = await _cart_and_incoming(db, picnic_client)
        except Exception:
            log.warning(
                "Restock %s skipped: cart or deliveries unreadable, reconcile retries",
                barcode,
                exc_info=True,
            )
            return None
        already_in_cart = cart.get(tracked.picnic_id, 0)
        on_order = incoming.get(tracked.picnic_id, 0)

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


def _likeness(name: str, rule_name: str) -> float:
    return fuzz.token_set_ratio(normalize_name(name), normalize_name(rule_name))


async def _link_inventory(
    db: AsyncSession,
    client: PicnicClientProtocol,
    rules: list[TrackedProduct],
    *,
    lookup_limit: int,
    lookup_delay_s: float,
) -> int:
    """Link unlinked inventory EANs; returns how many map to a Picnic product.

    A GTIN lookup costs Picnic requests and a few hundred in a row got the
    account briefly blocked (2026-10-03), so live lookups are spaced, capped
    per run and stop at the first failure. Rows whose name resembles a
    tracked product go first. Each link is committed on its own, so a later
    failure in the run doesn't lose it.
    """
    def best_likeness(name: str) -> float:
        return max((_likeness(name, r.name) for r in rules), default=0.0)

    pending = sorted(await unresolved_inventory(db), key=lambda row: -best_likeness(row[1]))
    linked = lookups = 0
    lookups_stopped = False
    for ean, _name in pending:
        known, _ = await stored_picnic_id(db, ean)
        if not known:
            if lookups_stopped or lookups >= lookup_limit:
                continue  # catalog-known rows further down cost nothing
            lookups += 1
        try:
            picnic_id = await link_ean(db, client, ean)
        except Exception:
            # Raised before anything was written; nothing to roll back.
            log.warning("GTIN lookup for %s failed, no more lookups this run", ean, exc_info=True)
            lookups_stopped = True
            continue
        await db.commit()
        if picnic_id is not None:
            linked += 1
        if not known and lookup_delay_s:
            await asyncio.sleep(lookup_delay_s)
    return linked


def _likely_unlinked(rule: TrackedProduct, unlinked: list[tuple[str, str]]) -> bool:
    return any(_likeness(name, rule.name) >= LIKELY_SAME_PRODUCT for _ean, name in unlinked)


async def reconcile_all(
    db: AsyncSession,
    client: PicnicClientProtocol,
    *,
    lookup_limit: int = 100,
    lookup_delay_s: float = 1.0,
) -> ReconcileSummary:
    """Link unlinked inventory EANs, then top up every rule below its minimum.

    Commits each new EAN link immediately; the restock part is left to the
    caller's commit. Raises if the cart or the deliveries can't be read --
    nothing is added blind. A refused add is reported in `failed` and not
    logged as a restock; a rule with a likely-unlinked row is `skipped`.
    """
    async with reconcile_lock:
        summary = ReconcileSummary()
        rules = list(
            (
                await db.execute(select(TrackedProduct).order_by(TrackedProduct.created_at))
            ).scalars().all()
        )
        summary.checked = len(rules)
        if not rules:
            return summary  # nothing to restock, don't spend lookups
        summary.resolved = await _link_inventory(
            db, client, rules, lookup_limit=lookup_limit, lookup_delay_s=lookup_delay_s
        )

        unlinked = await unresolved_inventory(db)
        async with restock_lock:
            cart, incoming = await _cart_and_incoming(db, client)
            for rule in rules:
                current = await linked_quantity(db, rule)
                if current >= rule.min_quantity:
                    continue
                if _likely_unlinked(rule, unlinked):
                    summary.skipped.append(rule.name)
                    continue
                delta = (
                    rule.target_quantity
                    - current
                    - cart.get(rule.picnic_id, 0)
                    - incoming.get(rule.picnic_id, 0)
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
        "Reconcile: %d rules, %d EANs linked, added %s, failed %s, skipped %s",
        summary.checked, summary.resolved, summary.added, summary.failed, summary.skipped,
    )
    return summary
