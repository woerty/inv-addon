"""HTTP façade for the Picnic grocery integration.

All business logic lives in app.services.picnic.*. This module's jobs are:
  - Validate requests (via Pydantic schemas)
  - Own the database transaction boundary (commit after each mutating call;
    services only flush)
  - Map service exceptions to HTTP status codes:
      PicnicNotConfigured      -> 503 {"error": "picnic_not_configured"}
      PicnicReauthRequired     -> 503 {"error": "picnic_reauth_required"}
      PicnicLoginNotInProgress -> 409 {"error": "no_login_in_progress"}
      PicnicLoginInvalidCode   -> 400 {"error": "invalid_2fa_code"}
      ValueError               -> 409 (already imported / missing target barcode)
      other unexpected         -> 500 (logged via log.exception, handled by FastAPI)

Tests swap the Picnic client by overriding the get_picnic_client dependency:
    app.dependency_overrides[get_picnic_client] = lambda: FakePicnicClient()
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.picnic import PicnicProduct
from app.schemas.picnic import (
    CartModifyRequest,
    CartResponse,
    CategoriesResponse,
    Category,
    CategoryItem,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportFetchResponse,
    PendingOrdersResponse,
    PicnicLoginSendCodeRequest,
    PicnicLoginSendCodeResponse,
    PicnicLoginStartResponse,
    PicnicLoginVerifyRequest,
    PicnicLoginVerifyResponse,
    PicnicProductCacheEntry,
    PicnicSearchResponse,
    PicnicSearchResult,
    PicnicStatusResponse,
    ProductDetailResponse,
    SubCategory,
)
from app.services.picnic.cart import (
    _parse_cart_quantities,
    parse_cart_response,
)
from app.services.picnic.catalog import PicnicProductData, get_product, upsert_product
from app.services.picnic.orders import parse_pending_orders
from app.services.picnic.client import (
    PicnicClientProtocol,
    PicnicNotConfigured,
    PicnicReauthRequired,
    get_picnic_client,
)
from app.services.picnic.import_flow import (
    commit_import_decisions,
    fetch_import_candidates,
)
from app.services.picnic.login import (
    PicnicLoginInvalidCode,
    PicnicLoginNotInProgress,
    PicnicLoginSession,
    get_login_session,
)

log = logging.getLogger("picnic.router")

router = APIRouter()

MAX_SEARCH_RESULTS = 50


def _feature_enabled() -> bool:
    s = get_settings()
    return bool(s.picnic_email and s.picnic_password)


def _require_enabled():
    if not _feature_enabled():
        raise HTTPException(
            status_code=503,
            detail={"error": "picnic_not_configured"},
        )


@router.get("/status", response_model=PicnicStatusResponse)
async def status(client: PicnicClientProtocol = Depends(get_picnic_client)):
    if not _feature_enabled():
        return PicnicStatusResponse(enabled=False, needs_login=False, account=None)
    try:
        user = await client.get_user()
        return PicnicStatusResponse(
            enabled=True,
            needs_login=False,
            account={
                "first_name": user.get("firstname"),
                "last_name": user.get("lastname"),
                "email": user.get("contact_email"),
            },
        )
    except PicnicNotConfigured:
        return PicnicStatusResponse(enabled=False, needs_login=False, account=None)
    except PicnicReauthRequired:
        # Feature is configured but the cached token is gone and 2FA is required.
        # Frontend renders a login screen instead of the normal Picnic UI.
        return PicnicStatusResponse(enabled=False, needs_login=True, account=None)
    except Exception as e:
        # Broad catch so any upstream surprise becomes a clean 503, but log
        # with traceback so programming bugs aren't silently disguised as
        # auth failures.
        log.exception("picnic /status probe failed unexpectedly")
        raise HTTPException(status_code=503, detail={"error": "picnic_auth_failed", "detail": str(e)})


@router.post("/login/start", response_model=PicnicLoginStartResponse)
async def login_start(
    session: PicnicLoginSession = Depends(get_login_session),
):
    _require_enabled()
    try:
        result = await session.start()
        return PicnicLoginStartResponse(status=result)
    except PicnicNotConfigured:
        raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
    except Exception as e:
        log.exception("picnic login start failed")
        raise HTTPException(
            status_code=503,
            detail={"error": "picnic_login_failed", "detail": str(e)},
        )


@router.post("/login/send-code", response_model=PicnicLoginSendCodeResponse)
async def login_send_code(
    req: PicnicLoginSendCodeRequest,
    session: PicnicLoginSession = Depends(get_login_session),
):
    _require_enabled()
    try:
        await session.send_code(req.channel)
        return PicnicLoginSendCodeResponse()
    except PicnicLoginNotInProgress:
        raise HTTPException(
            status_code=409,
            detail={"error": "no_login_in_progress"},
        )
    except Exception as e:
        log.exception("picnic login send-code failed")
        raise HTTPException(
            status_code=503,
            detail={"error": "picnic_send_code_failed", "detail": str(e)},
        )


@router.post("/login/verify", response_model=PicnicLoginVerifyResponse)
async def login_verify(
    req: PicnicLoginVerifyRequest,
    session: PicnicLoginSession = Depends(get_login_session),
):
    _require_enabled()
    try:
        await session.verify(req.code)
        return PicnicLoginVerifyResponse()
    except PicnicLoginNotInProgress:
        raise HTTPException(
            status_code=409,
            detail={"error": "no_login_in_progress"},
        )
    except PicnicLoginInvalidCode:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_2fa_code"},
        )
    except Exception as e:
        log.exception("picnic login verify failed")
        raise HTTPException(
            status_code=503,
            detail={"error": "picnic_verify_failed", "detail": str(e)},
        )


@router.post("/import/fetch", response_model=ImportFetchResponse)
async def import_fetch(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        response = await fetch_import_candidates(db, client)
        await db.commit()
        return response
    except PicnicNotConfigured:
        raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})


@router.post("/import/commit", response_model=ImportCommitResponse)
async def import_commit(
    req: ImportCommitRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        response = await commit_import_decisions(db, client, req.delivery_id, req.decisions)
        await db.commit()
        return response
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})


@router.get("/search", response_model=PicnicSearchResponse)
async def search(
    q: str,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    """Free-text Picnic catalog search. Optional fallback for the rare case
    where an inventory item has no EAN or get_article_by_gtin missed.

    Capped at MAX_SEARCH_RESULTS entries per request to bound catalog upsert
    cost. Short queries (<2 chars) are rejected to avoid cheap abuse.
    """
    _require_enabled()
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail={"error": "query_too_short"})
    raw = await client.search(q)
    # python-picnic-api2 returns list of groups; flatten items
    results: list[PicnicSearchResult] = []
    for group in raw:
        if len(results) >= MAX_SEARCH_RESULTS:
            break
        for item in group.get("items", []):
            if len(results) >= MAX_SEARCH_RESULTS:
                break
            pid = item.get("id")
            if not pid:
                continue
            name = item.get("name", "")
            await upsert_product(
                db,
                PicnicProductData(
                    picnic_id=pid,
                    ean=None,
                    name=name,
                    unit_quantity=item.get("unit_quantity"),
                    image_id=item.get("image_id"),
                    last_price_cents=item.get("display_price"),
                ),
            )
            results.append(
                PicnicSearchResult(
                    picnic_id=pid,
                    name=name,
                    unit_quantity=item.get("unit_quantity"),
                    image_id=item.get("image_id"),
                    price_cents=item.get("display_price"),
                )
            )
    await db.commit()
    return PicnicSearchResponse(results=results)


@router.get("/cache", response_model=list[PicnicProductCacheEntry])
async def list_cache(db: AsyncSession = Depends(get_db)):
    """Admin/debug: list cached picnic_products entries (shows ean pairings)."""
    _require_enabled()
    result = await db.execute(select(PicnicProduct).order_by(PicnicProduct.last_seen.desc()))
    return result.scalars().all()


@router.get("/debug/raw-delivery")
async def debug_raw_delivery(
    client: PicnicClientProtocol = Depends(get_picnic_client),
):
    """Temporary debug: return raw delivery detail for first delivery."""
    deliveries = await client.get_deliveries()
    if not deliveries:
        return {"deliveries": [], "detail": None}
    first = deliveries[0]
    detail = await client.get_delivery(first["id"])
    # Extract first product line for inspection
    sample_line = None
    for order in detail.get("orders", []):
        for line in order.get("items", []):
            sample_line = line
            break
        if sample_line:
            break
    return {"delivery_summary": first, "sample_line": sample_line}


@router.get("/debug/raw-categories")
async def debug_raw_categories(
    client: PicnicClientProtocol = Depends(get_picnic_client),
):
    """Temporary debug: return raw category data."""
    raw = await client.get_categories(depth=1)
    # Return first 3 groups with truncated items
    result = []
    for group in raw[:3]:
        g = {"id": group.get("id"), "name": group.get("name"), "type": group.get("type"),
             "image_id": group.get("image_id"), "keys": list(group.keys())}
        items = group.get("items", [])[:2]
        g["sample_items"] = [
            {"id": i.get("id"), "name": i.get("name"), "type": i.get("type"),
             "image_id": i.get("image_id"), "keys": list(i.keys()),
             "sub_items_count": len(i.get("items", [])),
             "sub_items_sample": [{"id": si.get("id"), "name": si.get("name"), "type": si.get("type"), "keys": list(si.keys())} for si in i.get("items", [])[:2]] if i.get("items") else None}
            for i in items if isinstance(i, dict)
        ]
        result.append(g)
    return {"total_groups": len(raw), "sample": result}


@router.delete("/cache/{picnic_id}")
async def clear_cache_entry(picnic_id: str, db: AsyncSession = Depends(get_db)):
    """Admin/debug: clear a cache entry so the next lookup refetches from Picnic."""
    _require_enabled()
    result = await db.execute(select(PicnicProduct).where(PicnicProduct.picnic_id == picnic_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(row)
    await db.commit()
    return {"message": "deleted"}


# ── Cart endpoints ────────────────────────────────────────────────────────────

@router.get("/cart", response_model=CartResponse)
async def get_cart(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    return await parse_cart_response(client)


@router.post("/cart/add", response_model=CartResponse)
async def cart_add(
    body: CartModifyRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    await client.add_product(body.picnic_id, count=body.count)
    return await parse_cart_response(client)


@router.post("/cart/remove", response_model=CartResponse)
async def cart_remove(
    body: CartModifyRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    await client.remove_product(body.picnic_id, count=body.count)
    return await parse_cart_response(client)


@router.post("/cart/clear", response_model=CartResponse)
async def cart_clear(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    await client.clear_cart()
    return await parse_cart_response(client)


# ── Pending orders ────────────────────────────────────────────────────────────

@router.get("/orders/pending", response_model=PendingOrdersResponse)
async def get_pending_orders(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    try:
        return await parse_pending_orders(client)
    except PicnicNotConfigured:
        raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})
    except Exception:
        log.exception("Failed to fetch pending orders")
        return PendingOrdersResponse(orders=[], quantity_map={})


@router.get("/orders/recent-products")
async def get_recent_products(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    from app.services.picnic.orders import get_recently_ordered_products

    try:
        products = await get_recently_ordered_products(client)
    except Exception:
        log.exception("Failed to fetch recent products")
        products = []
    return {"products": products}


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories", response_model=CategoriesResponse)
async def get_categories(
    depth: int = 2,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    try:
        raw = await client.get_categories(depth=depth)
    except PicnicNotConfigured:
        raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})
    except Exception:
        log.exception("Failed to fetch categories")
        return CategoriesResponse(categories=[])

    categories: list[Category] = []
    for group in raw:
        if not isinstance(group, dict):
            continue
        children: list[SubCategory] = []
        for sub in group.get("items", []):
            if not isinstance(sub, dict):
                continue
            sub_type = sub.get("type", "")
            # Accept both CATEGORY sub-groups and direct product listings
            if sub_type == "CATEGORY" or "items" in sub:
                items: list[CategoryItem] = []
                for product in sub.get("items", []):
                    if not isinstance(product, dict):
                        continue
                    pid = product.get("id")
                    if not pid:
                        continue
                    items.append(
                        CategoryItem(
                            picnic_id=pid,
                            name=product.get("name", ""),
                            unit_quantity=product.get("unit_quantity"),
                            image_id=product.get("image_id"),
                            price_cents=product.get("display_price"),
                        )
                    )
                children.append(
                    SubCategory(
                        id=sub.get("id", ""),
                        name=sub.get("name", ""),
                        image_id=sub.get("image_id"),
                        items=items,
                    )
                )
            elif sub.get("id"):
                # Leaf product directly under the group (no sub-category nesting)
                children.append(
                    SubCategory(
                        id=sub.get("id", ""),
                        name=sub.get("name", ""),
                        image_id=sub.get("image_id"),
                        items=[],
                    )
                )
        categories.append(
            Category(
                id=group.get("id", ""),
                name=group.get("name", ""),
                image_id=group.get("image_id"),
                children=children,
            )
        )
    return CategoriesResponse(categories=categories)


# ── Product detail ────────────────────────────────────────────────────────────

@router.get("/products/{picnic_id}", response_model=ProductDetailResponse)
async def get_product_detail(
    picnic_id: str,
    db: AsyncSession = Depends(get_db),
    client: PicnicClientProtocol = Depends(get_picnic_client),
    _: None = Depends(_require_enabled),
):
    from app.models.inventory import InventoryItem
    from app.models.tracked_product import TrackedProduct

    try:
        article = await client.get_article(picnic_id)
    except Exception:
        article = {}

    # Check cart quantity
    cart_quantities = {}
    try:
        raw_cart = await client.get_cart()
        cart_quantities = _parse_cart_quantities(raw_cart)
    except Exception:
        pass

    # Check pending order quantity
    on_order = 0
    try:
        pending = await parse_pending_orders(client)
        on_order = pending.quantity_map.get(picnic_id, 0)
    except Exception:
        pass

    # Check inventory via EAN match
    inventory_quantity = 0
    cached = await get_product(db, picnic_id)
    if cached and cached.ean:
        result = await db.execute(
            select(InventoryItem.quantity).where(InventoryItem.barcode == cached.ean)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            inventory_quantity = row

    # Check subscription
    is_subscribed = False
    tp_result = await db.execute(
        select(TrackedProduct).where(TrackedProduct.picnic_id == picnic_id)
    )
    is_subscribed = tp_result.scalar_one_or_none() is not None

    name = article.get("name", cached.name if cached else "Unknown")
    unit_quantity = article.get("unit_quantity", cached.unit_quantity if cached else None)
    image_id = article.get("image_id", cached.image_id if cached else None)
    price_cents = article.get("display_price", cached.last_price_cents if cached else None)

    return ProductDetailResponse(
        picnic_id=picnic_id,
        name=name,
        unit_quantity=unit_quantity,
        image_id=image_id,
        price_cents=price_cents,
        description=article.get("description"),
        in_cart=cart_quantities.get(picnic_id, 0),
        on_order=on_order,
        inventory_quantity=inventory_quantity,
        is_subscribed=is_subscribed,
    )
