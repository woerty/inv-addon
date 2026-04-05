from __future__ import annotations

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

router = APIRouter()


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
        return PicnicStatusResponse(enabled=False, account=None)
    try:
        user = await client.get_user()
        return PicnicStatusResponse(
            enabled=True,
            account={
                "first_name": user.get("firstname"),
                "last_name": user.get("lastname"),
                "email": user.get("contact_email"),
            },
        )
    except PicnicNotConfigured:
        return PicnicStatusResponse(enabled=False, account=None)
    except PicnicReauthRequired:
        # Feature is configured but the cached token is gone and 2FA is required.
        # Report as disabled so the frontend hides the UI; a banner should tell
        # the user to run the setup CLI.
        return PicnicStatusResponse(enabled=False, account=None)
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "picnic_auth_failed", "detail": str(e)})


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
    where an inventory item has no EAN or get_article_by_gtin missed."""
    _require_enabled()
    raw = await client.search(q)
    # python-picnic-api2 returns list of groups; flatten items
    results: list[PicnicSearchResult] = []
    for group in raw:
        for item in group.get("items", []):
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
