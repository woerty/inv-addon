from pydantic import BaseModel


class PinnedProduct(BaseModel):
    barcode: str
    name: str
    quantity: int
    min_quantity: int | None
    image_url: str | None

    model_config = {"from_attributes": True}


class LowStockItem(BaseModel):
    barcode: str
    name: str
    quantity: int
    min_quantity: int


class ActivityEntry(BaseModel):
    action: str
    barcode: str
    product_name: str
    details: str | None
    timestamp: str


class TrendSeries(BaseModel):
    category: str
    data: list[int]


class ConsumptionTrend(BaseModel):
    labels: list[str]
    series: list[TrendSeries]


class TopConsumer(BaseModel):
    barcode: str
    name: str
    count: int
    sparkline: list[int]


class CategoryCount(BaseModel):
    category: str
    inventory_count: int
    on_order_count: int


class WeeklyCost(BaseModel):
    week: str
    cents: int


class RestockCosts(BaseModel):
    total_cents: int
    previous_period_cents: int
    weekly: list[WeeklyCost]


class StorageLocationCount(BaseModel):
    name: str
    item_count: int


class DashboardSummary(BaseModel):
    pinned_products: list[PinnedProduct]
    low_stock: list[LowStockItem]
    recent_activity: list[ActivityEntry]
    consumption_trend: ConsumptionTrend
    top_consumers: list[TopConsumer]
    categories: list[CategoryCount]
    restock_costs: RestockCosts
    storage_locations: list[StorageLocationCount]


class ProductHistoryEntry(BaseModel):
    timestamp: str
    quantity_after: int
    action: str


class ProductStats(BaseModel):
    total_consumed: int
    avg_per_week: float
    times_restocked: int
    total_cost_cents: int
    estimated_days_remaining: float | None


class ProductDetailResponse(BaseModel):
    barcode: str
    name: str
    current_quantity: int
    min_quantity: int | None
    history: list[ProductHistoryEntry]
    stats: ProductStats
