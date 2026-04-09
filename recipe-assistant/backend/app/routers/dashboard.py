from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.inventory import InventoryItem
from app.schemas.dashboard import DashboardSummary, ProductDetailResponse
from app.services.dashboard import (
    get_pinned_products,
    get_low_stock,
    get_recent_activity,
    get_consumption_trend,
    get_top_consumers,
    get_category_counts,
    get_restock_costs,
    get_storage_location_counts,
    get_product_detail,
)

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    return DashboardSummary(
        pinned_products=await get_pinned_products(db),
        low_stock=await get_low_stock(db),
        recent_activity=await get_recent_activity(db),
        consumption_trend=await get_consumption_trend(db, days=days),
        top_consumers=await get_top_consumers(db, days=days),
        categories=await get_category_counts(db),
        restock_costs=await get_restock_costs(db, days=days),
        storage_locations=await get_storage_location_counts(db),
    )


@router.get("/product/{barcode}", response_model=ProductDetailResponse)
async def product_detail(
    barcode: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    return await get_product_detail(db, barcode=barcode, days=days)


@router.patch("/pin/{barcode}")
async def toggle_pin(
    barcode: str,
    db: AsyncSession = Depends(get_db),
):
    item = (
        await db.execute(
            select(InventoryItem).where(InventoryItem.barcode == barcode)
        )
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.is_pinned = not item.is_pinned
    await db.commit()
    return {"barcode": barcode, "is_pinned": item.is_pinned}
