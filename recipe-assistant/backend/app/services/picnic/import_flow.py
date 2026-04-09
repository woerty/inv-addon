from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem, StorageLocation
from app.models.picnic import (
    PicnicDeliveryImport,
    PicnicProduct,
)
from app.schemas.picnic import (
    ImportCandidate,
    ImportCommitResponse,
    ImportDecision,
    ImportDelivery,
    ImportFetchResponse,
    MatchSuggestion,
)
from app.services.picnic.catalog import PicnicProductData, upsert_product
from app.services.picnic.client import PicnicClientProtocol
from app.services.picnic.matching import (
    MatchCandidate,
    compute_match_suggestions,
)


def _flatten_delivery_items(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """python-picnic-api2 delivery detail is nested: orders[].items[].items[].

    Flatten to a list of line items with {picnic_id, name, unit_quantity, image_id, quantity}.
    """
    out: list[dict[str, Any]] = []
    for order in detail.get("orders", []):
        for line in order.get("items", []):
            inner = line.get("items", [])
            if not inner:
                continue
            product = inner[0]
            if not isinstance(product, dict) or "id" not in product:
                continue
            qty = 1
            for deco in line.get("decorators", []):
                if isinstance(deco, dict) and "quantity" in deco:
                    qty = deco["quantity"]
                    break
            out.append(
                {
                    "picnic_id": product["id"],
                    "name": product.get("name", ""),
                    "unit_quantity": product.get("unit_quantity"),
                    "image_id": product.get("image_id"),
                    "price_cents": product.get("display_price"),
                    "quantity": qty,
                }
            )
    return out


def _parse_delivery_time(detail: dict[str, Any]) -> datetime | None:
    dt = detail.get("delivery_time", {})
    start = dt.get("start")
    if not start:
        return None
    try:
        return datetime.fromisoformat(start)
    except ValueError:
        return None


async def _already_imported(session: AsyncSession, delivery_id: str) -> bool:
    result = await session.execute(
        select(PicnicDeliveryImport).where(PicnicDeliveryImport.delivery_id == delivery_id)
    )
    return result.scalar_one_or_none() is not None


async def _load_inventory_match_candidates(session: AsyncSession) -> list[MatchCandidate]:
    result = await session.execute(select(InventoryItem))
    return [MatchCandidate(barcode=it.barcode, name=it.name) for it in result.scalars().all()]


async def _suggestions_for_item(
    session: AsyncSession,
    picnic_id: str,
    picnic_name: str,
    picnic_unit_quantity: str | None,
    candidates: list[MatchCandidate],
) -> list[MatchSuggestion]:
    # Step 1: deterministic hit via cached ean on picnic_products
    cached = (await session.execute(
        select(PicnicProduct).where(PicnicProduct.picnic_id == picnic_id)
    )).scalar_one_or_none()
    if cached and cached.ean:
        inv = (await session.execute(
            select(InventoryItem).where(InventoryItem.barcode == cached.ean)
        )).scalar_one_or_none()
        if inv:
            return [
                MatchSuggestion(
                    inventory_barcode=inv.barcode,
                    inventory_name=inv.name,
                    score=100.0,
                    reason="known mapping",
                )
            ]

    # Step 2: fuzzy name match fallback
    fuzz_results = compute_match_suggestions(picnic_name, picnic_unit_quantity, candidates)
    return [
        MatchSuggestion(
            inventory_barcode=r.inventory_barcode,
            inventory_name=r.inventory_name,
            score=r.score,
            reason=r.reason,
        )
        for r in fuzz_results
    ]


async def fetch_import_candidates(
    session: AsyncSession,
    client: PicnicClientProtocol,
) -> ImportFetchResponse:
    """Fetch delivered-but-not-yet-imported Picnic orders with match suggestions."""
    summary = await client.get_deliveries()

    deliveries_out: list[ImportDelivery] = []
    candidates = await _load_inventory_match_candidates(session)

    for delivery_stub in summary:
        delivery_id = delivery_stub.get("delivery_id")
        if not delivery_id:
            continue
        if await _already_imported(session, delivery_id):
            continue

        detail = await client.get_delivery(delivery_id)
        items_flat = _flatten_delivery_items(detail)
        if not items_flat:
            continue

        # Cache picnic products as we go (opportunistic; ean=None preserves any
        # existing ean learned from prior cart-sync or scan).
        for item in items_flat:
            await upsert_product(
                session,
                PicnicProductData(
                    picnic_id=item["picnic_id"],
                    ean=None,
                    name=item["name"],
                    unit_quantity=item.get("unit_quantity"),
                    image_id=item.get("image_id"),
                    last_price_cents=item.get("price_cents"),
                ),
            )

        import_items: list[ImportCandidate] = []
        for item in items_flat:
            suggestions = await _suggestions_for_item(
                session,
                item["picnic_id"],
                item["name"],
                item.get("unit_quantity"),
                candidates,
            )
            best = suggestions[0].score if suggestions else 0.0
            import_items.append(
                ImportCandidate(
                    picnic_id=item["picnic_id"],
                    picnic_name=item["name"],
                    picnic_image_id=item.get("image_id"),
                    picnic_unit_quantity=item.get("unit_quantity"),
                    ordered_quantity=item["quantity"],
                    match_suggestions=suggestions,
                    best_confidence=best,
                )
            )

        deliveries_out.append(
            ImportDelivery(
                delivery_id=delivery_id,
                delivered_at=_parse_delivery_time(detail),
                items=import_items,
            )
        )

    await session.flush()  # persist catalog upserts
    return ImportFetchResponse(deliveries=deliveries_out)


async def commit_import_decisions(
    session: AsyncSession,
    client: PicnicClientProtocol,
    delivery_id: str,
    decisions: list[ImportDecision],
) -> ImportCommitResponse:
    """Apply user decisions transactionally.

    - match_existing: increment inventory quantity + cache ean on picnic_products
    - create_new:     create InventoryItem with synthetic or scanned barcode,
                      cache ean on picnic_products if scanned
    - skip:           no-op
    """
    if await _already_imported(session, delivery_id):
        raise ValueError(f"delivery {delivery_id} already imported")

    # Fetch delivery detail fresh to get quantities (we don't trust the client)
    detail = await client.get_delivery(delivery_id)
    flat = {it["picnic_id"]: it for it in _flatten_delivery_items(detail)}

    imported = 0
    created = 0
    skipped = 0
    promoted = 0

    for decision in decisions:
        line = flat.get(decision.picnic_id)
        if line is None:
            skipped += 1
            continue

        qty = line["quantity"]

        if decision.action == "skip":
            skipped += 1
            continue

        if decision.action == "match_existing":
            # Schema validator already guarantees target_barcode is set for this action.
            result = await session.execute(
                select(InventoryItem).where(InventoryItem.barcode == decision.target_barcode)
            )
            item = result.scalar_one_or_none()
            if item is None:
                raise ValueError(
                    f"match_existing target barcode {decision.target_barcode!r} "
                    f"not found in inventory"
                )
            item.quantity += qty

            # Cache the pairing on picnic_products so future resolutions are deterministic.
            await _cache_ean_pairing(
                session,
                picnic_id=decision.picnic_id,
                ean=decision.target_barcode,
                picnic_name=line["name"],
                unit_quantity=line.get("unit_quantity"),
                image_id=line.get("image_id"),
                price_cents=line.get("price_cents"),
            )
            imported += 1
            continue

        if decision.action == "create_new":
            if decision.scanned_ean:
                # Scanned real EAN - either merge into existing or create with real EAN
                existing = (await session.execute(
                    select(InventoryItem).where(InventoryItem.barcode == decision.scanned_ean)
                )).scalar_one_or_none()

                if existing:
                    existing.quantity += qty
                    if decision.storage_location:
                        existing.storage_location_id = await _resolve_location(session, decision.storage_location)
                    if decision.expiration_date:
                        existing.expiration_date = decision.expiration_date
                    promoted += 1
                else:
                    session.add(InventoryItem(
                        barcode=decision.scanned_ean,
                        name=line["name"],
                        quantity=qty,
                        category="Unbekannt",
                        storage_location_id=await _resolve_location(session, decision.storage_location),
                        expiration_date=decision.expiration_date,
                    ))
                    created += 1

                await _cache_ean_pairing(
                    session,
                    picnic_id=decision.picnic_id,
                    ean=decision.scanned_ean,
                    picnic_name=line["name"],
                    unit_quantity=line.get("unit_quantity"),
                    image_id=line.get("image_id"),
                    price_cents=line.get("price_cents"),
                )
            else:
                synthetic = f"picnic:{decision.picnic_id}"
                existing_syn = (await session.execute(
                    select(InventoryItem).where(InventoryItem.barcode == synthetic)
                )).scalar_one_or_none()
                if existing_syn:
                    existing_syn.quantity += qty
                else:
                    session.add(InventoryItem(
                        barcode=synthetic,
                        name=line["name"],
                        quantity=qty,
                        category="Unbekannt",
                        storage_location_id=await _resolve_location(session, decision.storage_location),
                        expiration_date=decision.expiration_date,
                    ))
                    created += 1
            continue

        # Unreachable via HTTP (Pydantic Literal blocks it), but defensive for internal callers.
        raise ValueError(f"unknown ImportDecision.action: {decision.action!r}")

    session.add(
        PicnicDeliveryImport(delivery_id=delivery_id, item_count=len(decisions))
    )
    await session.flush()

    return ImportCommitResponse(
        imported=imported,
        created=created,
        skipped=skipped,
        promoted=promoted,
    )


async def _resolve_location(session: AsyncSession, name: str | None) -> int | None:
    """Resolve storage location name -> id, creating the location if missing."""
    if not name:
        return None
    result = await session.execute(select(StorageLocation).where(StorageLocation.name == name))
    loc = result.scalar_one_or_none()
    if loc:
        return loc.id
    new_loc = StorageLocation(name=name)
    session.add(new_loc)
    await session.flush()
    return new_loc.id


async def _cache_ean_pairing(
    session: AsyncSession,
    *,
    picnic_id: str,
    ean: str,
    picnic_name: str,
    unit_quantity: str | None,
    image_id: str | None,
    price_cents: int | None,
) -> None:
    """Upsert picnic_products with the learned ean. If the row exists with a
    different (older) ean, overwrite - the latest user action wins."""
    await upsert_product(
        session,
        PicnicProductData(
            picnic_id=picnic_id,
            ean=ean,
            name=picnic_name,
            unit_quantity=unit_quantity,
            image_id=image_id,
            last_price_cents=price_cents,
        ),
    )
