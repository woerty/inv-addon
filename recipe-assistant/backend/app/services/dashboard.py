import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.models.picnic import PicnicProduct
from app.schemas.dashboard import (
    PinnedProduct,
    LowStockItem,
    ActivityEntry,
    ConsumptionTrend,
    TrendSeries,
    TopConsumer,
    CategoryCount,
    RestockCosts,
    WeeklyCost,
    StorageLocationCount,
    ProductDetailResponse,
    ProductHistoryEntry,
    ProductStats,
)

CONSUME_ACTIONS = ("remove", "scan-out")


async def get_pinned_products(db: AsyncSession) -> list[PinnedProduct]:
    query = (
        select(
            InventoryItem.barcode,
            InventoryItem.name,
            InventoryItem.quantity,
            InventoryItem.image_url,
            TrackedProduct.min_quantity,
        )
        .outerjoin(TrackedProduct, InventoryItem.barcode == TrackedProduct.barcode)
        .where(InventoryItem.is_pinned == True)  # noqa: E712
        .order_by(InventoryItem.name)
    )
    rows = (await db.execute(query)).all()
    return [
        PinnedProduct(
            barcode=r.barcode,
            name=r.name,
            quantity=r.quantity,
            min_quantity=r.min_quantity,
            image_url=r.image_url,
        )
        for r in rows
    ]


async def get_low_stock(db: AsyncSession) -> list[LowStockItem]:
    query = (
        select(
            InventoryItem.barcode,
            InventoryItem.name,
            InventoryItem.quantity,
            TrackedProduct.min_quantity,
        )
        .join(TrackedProduct, InventoryItem.barcode == TrackedProduct.barcode)
        .where(InventoryItem.quantity < TrackedProduct.min_quantity)
        .order_by(
            (InventoryItem.quantity * 1.0 / TrackedProduct.min_quantity).asc()
        )
    )
    rows = (await db.execute(query)).all()
    return [
        LowStockItem(
            barcode=r.barcode,
            name=r.name,
            quantity=r.quantity,
            min_quantity=r.min_quantity,
        )
        for r in rows
    ]


async def get_recent_activity(
    db: AsyncSession, limit: int = 15
) -> list[ActivityEntry]:
    query = (
        select(
            InventoryLog.action,
            InventoryLog.barcode,
            InventoryLog.details,
            InventoryLog.timestamp,
            InventoryItem.name,
        )
        .outerjoin(InventoryItem, InventoryLog.barcode == InventoryItem.barcode)
        .order_by(InventoryLog.timestamp.desc())
        .limit(limit)
    )
    rows = (await db.execute(query)).all()
    return [
        ActivityEntry(
            action=r.action,
            barcode=r.barcode,
            product_name=r.name or r.barcode,
            details=r.details,
            timestamp=r.timestamp.isoformat(),
        )
        for r in rows
    ]


def _week_label(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"KW{iso.week:02d}"


async def get_consumption_trend(
    db: AsyncSession, days: int = 30
) -> ConsumptionTrend:
    since = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(
            InventoryLog.timestamp,
            InventoryItem.category,
        )
        .join(InventoryItem, InventoryLog.barcode == InventoryItem.barcode)
        .where(
            InventoryLog.action.in_(CONSUME_ACTIONS),
            InventoryLog.timestamp >= since,
        )
        .order_by(InventoryLog.timestamp)
    )
    rows = (await db.execute(query)).all()

    # Build week buckets
    week_set: dict[str, int] = {}
    cat_week: dict[str, dict[str, int]] = {}
    for r in rows:
        wk = _week_label(r.timestamp)
        if wk not in week_set:
            week_set[wk] = len(week_set)
        cat_week.setdefault(r.category, {})
        cat_week[r.category][wk] = cat_week[r.category].get(wk, 0) + 1

    labels = sorted(week_set.keys(), key=lambda w: week_set[w])
    series = []
    for cat, weeks in sorted(cat_week.items()):
        data = [weeks.get(wk, 0) for wk in labels]
        series.append(TrendSeries(category=cat, data=data))

    return ConsumptionTrend(labels=labels, series=series)


async def get_top_consumers(
    db: AsyncSession, days: int = 30, limit: int = 10
) -> list[TopConsumer]:
    since = datetime.now(UTC) - timedelta(days=days)

    # Total counts
    count_q = (
        select(
            InventoryLog.barcode,
            func.count().label("cnt"),
        )
        .where(
            InventoryLog.action.in_(CONSUME_ACTIONS),
            InventoryLog.timestamp >= since,
        )
        .group_by(InventoryLog.barcode)
        .order_by(func.count().desc())
        .limit(limit)
    )
    count_rows = (await db.execute(count_q)).all()
    if not count_rows:
        return []

    barcodes = [r.barcode for r in count_rows]
    count_map = {r.barcode: r.cnt for r in count_rows}

    # Get names
    name_q = select(InventoryItem.barcode, InventoryItem.name).where(
        InventoryItem.barcode.in_(barcodes)
    )
    name_map = {r.barcode: r.name for r in (await db.execute(name_q)).all()}

    # Sparkline data: split time range into 4 buckets
    bucket_size = max(days // 4, 1)
    now = datetime.now(UTC)

    result = []
    for bc in barcodes:
        sparkline = []
        for i in range(4):
            bucket_end = now - timedelta(days=i * bucket_size)
            bucket_start = now - timedelta(days=(i + 1) * bucket_size)
            sq = (
                select(func.count())
                .where(
                    InventoryLog.barcode == bc,
                    InventoryLog.action.in_(CONSUME_ACTIONS),
                    InventoryLog.timestamp >= bucket_start,
                    InventoryLog.timestamp < bucket_end,
                )
            )
            cnt = (await db.execute(sq)).scalar() or 0
            sparkline.append(cnt)
        sparkline.reverse()  # oldest first

        result.append(
            TopConsumer(
                barcode=bc,
                name=name_map.get(bc, bc),
                count=count_map[bc],
                sparkline=sparkline,
            )
        )

    return result


async def get_category_counts(db: AsyncSession) -> list[CategoryCount]:
    query = (
        select(
            InventoryItem.category,
            func.count().label("cnt"),
        )
        .group_by(InventoryItem.category)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(query)).all()
    return [
        # on_order_count: v1 always 0, enriching from Picnic pending orders is a follow-up
        CategoryCount(category=r.category, inventory_count=r.cnt, on_order_count=0)
        for r in rows
    ]


def _parse_restock_delta(details: str | None) -> int:
    """Parse cart delta from restock_auto log details like 'qty->4, cart delta=3'."""
    if not details:
        return 1
    m = re.search(r"cart delta=(\d+)", details)
    return int(m.group(1)) if m else 1


async def get_restock_costs(
    db: AsyncSession, days: int = 30
) -> RestockCosts:
    since = datetime.now(UTC) - timedelta(days=days)
    previous_since = since - timedelta(days=days)

    # Current period
    query = (
        select(InventoryLog.barcode, InventoryLog.details, InventoryLog.timestamp)
        .where(
            InventoryLog.action == "restock_auto",
            InventoryLog.timestamp >= since,
        )
    )
    rows = (await db.execute(query)).all()

    # Get prices for all barcodes involved
    barcodes = list({r.barcode for r in rows})
    price_map: dict[str, int] = {}
    if barcodes:
        price_q = (
            select(TrackedProduct.barcode, PicnicProduct.last_price_cents)
            .join(PicnicProduct, TrackedProduct.picnic_id == PicnicProduct.picnic_id)
            .where(TrackedProduct.barcode.in_(barcodes))
        )
        for r in (await db.execute(price_q)).all():
            if r.last_price_cents is not None:
                price_map[r.barcode] = r.last_price_cents

    total_cents = 0
    week_costs: dict[str, int] = {}
    for r in rows:
        delta = _parse_restock_delta(r.details)
        cost = delta * price_map.get(r.barcode, 0)
        total_cents += cost
        wk = _week_label(r.timestamp)
        week_costs[wk] = week_costs.get(wk, 0) + cost

    # Previous period
    prev_query = (
        select(InventoryLog.barcode, InventoryLog.details)
        .where(
            InventoryLog.action == "restock_auto",
            InventoryLog.timestamp >= previous_since,
            InventoryLog.timestamp < since,
        )
    )
    prev_rows = (await db.execute(prev_query)).all()
    prev_total = sum(
        _parse_restock_delta(r.details) * price_map.get(r.barcode, 0)
        for r in prev_rows
    )

    weekly = sorted(
        [WeeklyCost(week=wk, cents=c) for wk, c in week_costs.items()],
        key=lambda w: w.week,
    )

    return RestockCosts(
        total_cents=total_cents,
        previous_period_cents=prev_total,
        weekly=weekly,
    )


async def get_storage_location_counts(
    db: AsyncSession,
) -> list[StorageLocationCount]:
    query = (
        select(
            StorageLocation.name,
            func.count(InventoryItem.id).label("cnt"),
        )
        .join(InventoryItem, StorageLocation.id == InventoryItem.storage_location_id)
        .group_by(StorageLocation.name)
        .order_by(func.count(InventoryItem.id).desc())
    )
    rows = (await db.execute(query)).all()
    return [
        StorageLocationCount(name=r.name, item_count=r.cnt)
        for r in rows
    ]


def _parse_quantity_after(details: str | None) -> int | None:
    """Parse the target quantity from details like 'quantity: 5 -> 3' or 'qty->4, cart delta=3'."""
    if not details:
        return None
    # "quantity: X → Y"
    m = re.search(r"→\s*(\d+)", details)
    if m:
        return int(m.group(1))
    # "qty→N"
    m = re.search(r"qty→(\d+)", details)
    if m:
        return int(m.group(1))
    return None


async def get_product_detail(
    db: AsyncSession, barcode: str, days: int = 30
) -> ProductDetailResponse:
    since = datetime.now(UTC) - timedelta(days=days)

    # Get current item
    item = (
        await db.execute(
            select(InventoryItem).where(InventoryItem.barcode == barcode)
        )
    ).scalar_one_or_none()

    name = item.name if item else barcode
    current_qty = item.quantity if item else 0

    # Get tracked product for min_quantity
    tp = (
        await db.execute(
            select(TrackedProduct.min_quantity).where(TrackedProduct.barcode == barcode)
        )
    ).scalar_one_or_none()

    # Get all logs in range
    logs_q = (
        select(InventoryLog)
        .where(
            InventoryLog.barcode == barcode,
            InventoryLog.timestamp >= since,
        )
        .order_by(InventoryLog.timestamp)
    )
    logs = (await db.execute(logs_q)).scalars().all()

    # Build history: reconstruct quantity at each point
    history = []
    for log in logs:
        qty_after = _parse_quantity_after(log.details)
        if log.details == "removed last item":
            qty_after = 0
        if log.details == "new item":
            qty_after = 1
        if qty_after is not None:
            history.append(
                ProductHistoryEntry(
                    timestamp=log.timestamp.isoformat(),
                    quantity_after=qty_after,
                    action=log.action,
                )
            )

    # Stats
    consumed = sum(1 for log in logs if log.action in CONSUME_ACTIONS)
    restocked = sum(1 for log in logs if log.action == "restock_auto")

    days_in_range = max(days, 1)
    avg_per_week = consumed / days_in_range * 7

    # Cost
    cost_cents = 0
    if restocked > 0:
        price_q = (
            select(PicnicProduct.last_price_cents)
            .join(TrackedProduct, TrackedProduct.picnic_id == PicnicProduct.picnic_id)
            .where(TrackedProduct.barcode == barcode)
        )
        price = (await db.execute(price_q)).scalar_one_or_none()
        if price:
            for log in logs:
                if log.action == "restock_auto":
                    delta = _parse_restock_delta(log.details)
                    cost_cents += delta * price

    # Estimated days remaining
    estimated_days = None
    if avg_per_week > 0 and current_qty > 0:
        estimated_days = round(current_qty / avg_per_week * 7, 1)

    return ProductDetailResponse(
        barcode=barcode,
        name=name,
        current_quantity=current_qty,
        min_quantity=tp,
        history=history,
        stats=ProductStats(
            total_consumed=consumed,
            avg_per_week=round(avg_per_week, 1),
            times_restocked=restocked,
            total_cost_cents=cost_cents,
            estimated_days_remaining=estimated_days,
        ),
    )
