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
from app.models.picnic import PicnicProduct, ShoppingListItem
from app.schemas.picnic import (
    CartSyncResponse,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportFetchResponse,
    PicnicLoginSendCodeRequest,
    PicnicLoginSendCodeResponse,
    PicnicLoginStartResponse,
    PicnicLoginVerifyRequest,
    PicnicLoginVerifyResponse,
    PicnicProductCacheEntry,
    PicnicSearchResponse,
    PicnicSearchResult,
    PicnicStatusResponse,
    ShoppingListAddRequest,
    ShoppingListItemResponse,
    ShoppingListUpdateRequest,
)
from app.services.picnic.cart import resolve_shopping_list_status, sync_shopping_list_to_cart
from app.services.picnic.catalog import PicnicProductData, upsert_product
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


@router.get("/shopping-list", response_model=list[ShoppingListItemResponse])
async def get_shopping_list(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        items = await resolve_shopping_list_status(db, client)
        await db.commit()
        return items
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})


@router.post("/shopping-list", response_model=ShoppingListItemResponse, status_code=201)
async def add_shopping_list_item(
    req: ShoppingListAddRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    item = ShoppingListItem(
        inventory_barcode=req.inventory_barcode,
        picnic_id=req.picnic_id,
        name=req.name,
        quantity=req.quantity,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    try:
        items = await resolve_shopping_list_status(db, client)
        await db.commit()
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})
    return next(i for i in items if i.id == item.id)


@router.patch("/shopping-list/{item_id}", response_model=ShoppingListItemResponse)
async def update_shopping_list_item(
    item_id: int,
    req: ShoppingListUpdateRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    result = await db.execute(select(ShoppingListItem).where(ShoppingListItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    if req.quantity is not None:
        item.quantity = req.quantity
    if req.picnic_id is not None:
        item.picnic_id = req.picnic_id
    await db.commit()
    try:
        items = await resolve_shopping_list_status(db, client)
        await db.commit()
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})
    return next(i for i in items if i.id == item_id)


@router.delete("/shopping-list/{item_id}")
async def delete_shopping_list_item(item_id: int, db: AsyncSession = Depends(get_db)):
    _require_enabled()
    result = await db.execute(select(ShoppingListItem).where(ShoppingListItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(item)
    await db.commit()
    return {"message": "deleted"}


@router.post("/shopping-list/sync", response_model=CartSyncResponse)
async def sync_cart(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        response = await sync_shopping_list_to_cart(db, client)
        await db.commit()
        return response
    except PicnicReauthRequired:
        raise HTTPException(status_code=503, detail={"error": "picnic_reauth_required"})


@router.get("/cache", response_model=list[PicnicProductCacheEntry])
async def list_cache(db: AsyncSession = Depends(get_db)):
    """Admin/debug: list cached picnic_products entries (shows ean pairings)."""
    _require_enabled()
    result = await db.execute(select(PicnicProduct).order_by(PicnicProduct.last_seen.desc()))
    return result.scalars().all()


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
