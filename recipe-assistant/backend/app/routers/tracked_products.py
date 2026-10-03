"""HTTP router for per-product auto-restock rules.

All endpoints require the Picnic feature to be configured (mirrors the
gate in app.routers.picnic). Tracked products can only be created for
products that resolve to a Picnic SKU via get_article_by_gtin.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.inventory import InventoryItem
from app.models.picnic import PicnicProduct
from app.models.tracked_product import TrackedProduct
from app.schemas.tracked_product import (
    PromoteBarcodeRequest,
    PromoteBarcodeResponse,
    ReconcileAdded,
    ReconcileResponse,
    ResolvePreviewRequest,
    ResolvePreviewResponse,
    TrackedProductCreate,
    TrackedProductRead,
    TrackedProductUpdate,
)
from app.services.picnic.catalog import (
    PicnicProductData,
    get_product,
    get_product_by_ean,
    upsert_product,
)
from app.services.picnic.client import (
    PicnicAPIError,
    PicnicClientProtocol,
    PicnicNotConfigured,
    PicnicReauthRequired,
    get_picnic_client,
)
from app.services.picnic.ean_links import linked_barcodes, linked_quantity
from app.services.restock import check_and_enqueue, reconcile_all
from app.services.tracked_products import is_synthetic_barcode, make_synthetic_barcode

router = APIRouter()
log = logging.getLogger(__name__)


def _feature_enabled() -> bool:
    s = get_settings()
    return bool(s.picnic_email and s.picnic_password)


def _require_enabled() -> None:
    if not _feature_enabled():
        raise HTTPException(
            status_code=503,
            detail={"error": "picnic_not_configured"},
        )


async def _resolve_picnic(
    db: AsyncSession,
    client: PicnicClientProtocol,
    barcode: str,
) -> tuple[PicnicProduct | None, str]:
    """Cache-first Picnic lookup by EAN. Returns (row, reason).

    reason ∈ {"cache_hit", "live_lookup", "not_in_picnic_catalog"}.
    On live hit, caches into picnic_products before returning.
    """
    cached = await get_product_by_ean(db, barcode)
    if cached is not None:
        return cached, "cache_hit"

    result = await client.get_article_by_gtin(barcode)
    if result is None:
        return None, "not_in_picnic_catalog"

    row = await upsert_product(
        db,
        PicnicProductData(
            picnic_id=result["id"],
            ean=barcode,
            name=result["name"],
            unit_quantity=result.get("unit_quantity"),
            image_id=result.get("image_id"),
            last_price_cents=result.get("display_price"),
        ),
    )
    return row, "live_lookup"


async def _current_inventory_quantity(db: AsyncSession, barcode: str) -> int:
    row = (
        await db.execute(
            select(InventoryItem).where(InventoryItem.barcode == barcode)
        )
    ).scalar_one_or_none()
    return row.quantity if row is not None else 0


async def _build_read_model(db: AsyncSession, tp: TrackedProduct) -> TrackedProductRead:
    picnic_row = (
        await db.execute(
            select(PicnicProduct).where(PicnicProduct.picnic_id == tp.picnic_id)
        )
    ).scalar_one_or_none()
    current_qty = await linked_quantity(db, tp)
    return TrackedProductRead(
        barcode=tp.barcode,
        picnic_id=tp.picnic_id,
        name=tp.name,
        picnic_name=picnic_row.name if picnic_row else tp.name,
        picnic_image_id=picnic_row.image_id if picnic_row else None,
        picnic_unit_quantity=picnic_row.unit_quantity if picnic_row else None,
        min_quantity=tp.min_quantity,
        target_quantity=tp.target_quantity,
        current_quantity=current_qty,
        below_threshold=current_qty < tp.min_quantity,
        created_at=tp.created_at,
        updated_at=tp.updated_at,
        inventory_barcodes=await linked_barcodes(db, tp),
    )


@router.get("", response_model=list[TrackedProductRead])
async def list_tracked(db: AsyncSession = Depends(get_db)):
    _require_enabled()
    rows = (
        await db.execute(
            select(TrackedProduct).order_by(TrackedProduct.created_at.desc())
        )
    ).scalars().all()
    results: list[TrackedProductRead] = []
    for row in rows:
        results.append(await _build_read_model(db, row))
    # Sort by below_threshold desc so action items float to the top.
    results.sort(key=lambda r: (not r.below_threshold, r.barcode))
    return results


@router.post(
    "/resolve-preview",
    response_model=ResolvePreviewResponse,
)
async def resolve_preview(
    req: ResolvePreviewRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        row, reason = await _resolve_picnic(db, client, req.barcode)
    except PicnicNotConfigured:
        raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})
    if row is not None:
        # Only commit if _resolve_picnic actually upserted (live_lookup path).
        # cache_hit is a pure read; miss returns early with no writes.
        await db.commit()
    if row is None:
        return ResolvePreviewResponse(
            resolved=False,
            picnic_id=None,
            picnic_name=None,
            picnic_image_id=None,
            picnic_unit_quantity=None,
            reason=reason,
        )
    return ResolvePreviewResponse(
        resolved=True,
        picnic_id=row.picnic_id,
        picnic_name=row.name,
        picnic_image_id=row.image_id,
        picnic_unit_quantity=row.unit_quantity,
        reason=reason,
    )


@router.post("", response_model=TrackedProductRead, status_code=201)
async def create_tracked(
    req: TrackedProductCreate,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()

    # Determine the effective barcode: real (user-supplied) or synthetic.
    if req.barcode is not None:
        effective_barcode = req.barcode
    else:
        # Store-browser path: barcode=null, picnic_id required (validated by schema).
        effective_barcode = make_synthetic_barcode(req.picnic_id)

    # Reject duplicate up front before hitting Picnic API.
    existing = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == effective_barcode)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "already_tracked", "barcode": effective_barcode},
        )

    if req.barcode is not None:
        # Classic path: resolve Picnic mapping from barcode via get_article_by_gtin.
        try:
            picnic_row, _reason = await _resolve_picnic(db, client, req.barcode)
        except PicnicNotConfigured:
            raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
        except PicnicReauthRequired:
            raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})

        if picnic_row is None:
            raise HTTPException(
                status_code=422,
                detail={"error": "picnic_product_not_found", "barcode": req.barcode},
            )

        # Prefer the inventory row's name (user-custom) over Picnic's, if present.
        inventory_row = (
            await db.execute(
                select(InventoryItem).where(InventoryItem.barcode == req.barcode)
            )
        ).scalar_one_or_none()
        display_name = inventory_row.name if inventory_row is not None else picnic_row.name
        picnic_id = picnic_row.picnic_id
        current_qty = inventory_row.quantity if inventory_row is not None else 0
    else:
        # Synth path: picnic_id and name come directly from the request.
        display_name = req.name or req.picnic_id
        picnic_id = req.picnic_id
        current_qty = 0  # No inventory item for synth-subscribed products.

    tp = TrackedProduct(
        barcode=effective_barcode,
        picnic_id=picnic_id,
        name=display_name,
        min_quantity=req.min_quantity,
        target_quantity=req.target_quantity,
    )
    db.add(tp)
    await db.flush()

    # Immediate check: if the inventory quantity is already below the new
    # threshold, add directly to the Picnic cart in the same transaction.
    await check_and_enqueue(
        db, barcode=effective_barcode, new_quantity=current_qty, picnic_client=client
    )

    result = await _build_read_model(db, tp)
    await db.commit()
    return result


@router.post("/reconcile", response_model=ReconcileResponse)
async def reconcile(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    """Re-check every rule now (the same run the scheduler does every few hours)."""
    _require_enabled()
    try:
        # Few live GTIN lookups so the request stays quick; the scheduled
        # run links the rest of the inventory.
        summary = await reconcile_all(db, client, lookup_limit=10, lookup_delay_s=0.3)
    except PicnicNotConfigured:
        raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})
    except PicnicAPIError:
        raise
    except Exception:
        log.exception("reconcile failed")
        raise HTTPException(
            status_code=502,
            detail={"error": "Warenkorb oder Bestellungen bei Picnic nicht lesbar"},
        )
    await db.commit()
    return ReconcileResponse(
        checked=summary.checked,
        resolved=summary.resolved,
        added=[ReconcileAdded(name=name, quantity=qty) for name, qty in summary.added],
        failed=summary.failed,
    )


@router.patch("/{barcode}", response_model=TrackedProductRead)
async def update_tracked(
    barcode: str,
    req: TrackedProductUpdate,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()

    tp = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()
    if tp is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})

    new_min = req.min_quantity if req.min_quantity is not None else tp.min_quantity
    new_target = (
        req.target_quantity if req.target_quantity is not None else tp.target_quantity
    )
    if new_target < new_min:
        raise HTTPException(
            status_code=422,
            detail={"error": "target_must_be_gte_min"},
        )

    tp.min_quantity = new_min
    tp.target_quantity = new_target
    await db.flush()
    # updated_at is set server-side and expired by the flush; load it now,
    # _build_read_model reads it synchronously.
    await db.refresh(tp)

    # Re-run the threshold check so a raised min_quantity/target_quantity
    # triggers a Picnic cart addition. Lowered thresholds are no-ops by
    # add-only semantics.
    current_qty = await _current_inventory_quantity(db, barcode)
    await check_and_enqueue(
        db, barcode=barcode, new_quantity=current_qty, picnic_client=client
    )

    result = await _build_read_model(db, tp)
    await db.commit()
    return result


@router.delete("/{barcode}")
async def delete_tracked(barcode: str, db: AsyncSession = Depends(get_db)):
    _require_enabled()
    tp = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()
    if tp is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    await db.delete(tp)
    await db.commit()
    return {"message": "deleted"}


@router.post(
    "/{barcode}/promote-barcode",
    response_model=PromoteBarcodeResponse,
)
async def promote_barcode(
    barcode: str,
    req: PromoteBarcodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Promote a synthetic barcode to a real EAN.

    If ``new_barcode`` already exists as a tracked-product PK, the existing
    real row is deleted and the synth row absorbs its position ("promoted
    synth wins" merge semantics).
    """
    _require_enabled()

    synth_row = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()
    if synth_row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})

    if not is_synthetic_barcode(synth_row.barcode):
        raise HTTPException(
            status_code=400,
            detail={"error": "already_real_barcode"},
        )

    new_barcode = req.new_barcode.strip()
    if is_synthetic_barcode(new_barcode):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_new_barcode"},
        )

    # Check for PK collision with an existing real-barcode row.
    existing_real = (
        await db.execute(
            select(TrackedProduct).where(TrackedProduct.barcode == new_barcode)
        )
    ).scalar_one_or_none()
    merged = existing_real is not None
    if merged:
        await db.delete(existing_real)
        await db.flush()

    # PK change via delete + insert (SQLAlchemy PK mutations are fragile).
    preserved = {
        "picnic_id": synth_row.picnic_id,
        "name": synth_row.name,
        "min_quantity": synth_row.min_quantity,
        "target_quantity": synth_row.target_quantity,
        "created_at": synth_row.created_at,
    }
    await db.delete(synth_row)
    await db.flush()

    promoted = TrackedProduct(barcode=new_barcode, **preserved)
    db.add(promoted)
    await db.flush()

    # Also update the PicnicProduct cache row with the newly-learned EAN.
    picnic_product = await get_product(db, preserved["picnic_id"])
    if picnic_product is not None and picnic_product.ean is None:
        picnic_product.ean = new_barcode

    read_model = await _build_read_model(db, promoted)
    await db.commit()
    return PromoteBarcodeResponse(tracked=read_model, merged=merged)
