# Dashboard Design Spec

## Overview

A household dashboard for the Recipe Assistant inventory system. Replaces the current inventory list as the app's homepage (`/`). Provides a quick overview of inventory status and consumption analytics for all household members.

## Navigation

- Dashboard becomes the new homepage at `/`
- Inventory list moves to `/inventory`
- All other routes remain unchanged

## Layout

Fixed 2-column responsive grid on a single scrollable page. Two sections:

1. **Live Status** (top) — current state at a glance
2. **Analyse** (bottom) — consumption trends and analytics

A time-range selector (7T / 30T / 90T, default 30T) sits top-right and controls all Analyse widgets simultaneously. Live Status widgets are always current and unaffected by the time range.

On mobile (<600px), the grid collapses to a single column.

## Widgets

### Live Status

#### Gepinnte Produkte
- Shared pin list for the entire household (no per-user pins)
- Shows product name + current quantity, color-coded:
  - Green: quantity > min_quantity (or no tracked product rule)
  - Orange: quantity == min_quantity
  - Red: quantity < min_quantity or 0
- Pin/unpin via a new `is_pinned` boolean on `InventoryItem`
- Pinning UI: toggle on the inventory list page or via a "+" button on the widget itself

#### Laufende Bestellungen
- Shows pending Picnic deliveries (from existing `/api/picnic/orders/pending`)
- Shows open cart summary (from existing `/api/picnic/cart`)
- Each entry: delivery date/status, item count, total price

#### Niedrig-Bestand Alerts
- Lists tracked products where current quantity < min_quantity
- Shows current quantity and min_quantity threshold
- Sorted by urgency (lowest ratio of current/min first)
- Data source: existing tracked_products endpoint already joins inventory quantity

#### Letzte Aktivität
- Feed of the most recent InventoryLog entries (last 10-20)
- Shows human-readable action description + relative timestamp
- Action types: scan-in, scan-out, add, remove, restock_auto, delivery import
- Data source: included in `/api/dashboard/summary` response

### Analyse

#### Verbrauchstrend (full width)
- Line chart showing items consumed per week, broken down by category
- Each category is a separate line/series with its own color
- X-axis: calendar weeks within selected time range
- Y-axis: number of items consumed (count of remove/scan-out log entries)
- Data source: aggregate InventoryLog entries with action in (remove, scan-out)

#### Top-Verbraucher
- Ranked list of most-consumed products within the time range
- Each entry shows: product name, mini sparkline (trend), consumption count
- Clicking a product opens the Produkt-Detail view (see below)
- Data source: group InventoryLog (remove/scan-out) by barcode, count, order desc

#### Kategorien
- Horizontal bar chart showing item count per category
- Two segments per bar: current inventory (blue) + items on order via Picnic (teal)
- "On order" count comes from pending orders quantity_map matched to inventory categories
- Data source: group InventoryItem by category + cross-reference pending Picnic orders

#### Restock-Kosten
- Total auto-restock cost for the selected time range
- Percentage change vs. previous equivalent period
- Bar chart: cost per week
- Cost calculation: count of restock_auto log entries × last_price_cents from PicnicProduct
- Data source: join InventoryLog (restock_auto) with TrackedProduct → PicnicProduct

#### Lagerorte
- Bar chart showing number of items per storage location
- Data source: group InventoryItem by storage_location_id

### Produkt-Detail (expandable)

Opens as an expandable panel below the Top-Verbraucher widget when clicking a product. Shows:

- **Bestandsverlauf**: Step-line chart of quantity over time
  - X-axis: days within time range
  - Y-axis: quantity
  - Horizontal dashed red line at min_quantity (if tracked)
  - Green dots marking restock/delivery events
  - Data source: reconstruct from InventoryLog entries for that barcode
- **Kennzahlen**: Total consumed, avg consumption rate per week, times restocked, total cost
- **"Reicht noch" estimate**: current quantity / avg consumption rate = estimated days until depletion

## Backend API

### New Endpoints

All under `/api/dashboard/`:

#### `GET /api/dashboard/summary`
Returns aggregated data for all dashboard widgets in a single call to minimize round-trips.

Query params:
- `days` (int, default 30): time range for analytics (7, 30, or 90)

Response shape:
```json
{
  "pinned_products": [
    {"barcode": "...", "name": "...", "quantity": 3, "min_quantity": 2, "image_url": "..."}
  ],
  "low_stock": [
    {"barcode": "...", "name": "...", "quantity": 0, "min_quantity": 2}
  ],
  "recent_activity": [
    {"action": "scan-out", "barcode": "...", "product_name": "...", "details": "...", "timestamp": "..."}
  ],
  "consumption_trend": {
    "labels": ["KW11", "KW12", ...],
    "series": [
      {"category": "Milchprodukte", "data": [8, 6, 10, 7]}
    ]
  },
  "top_consumers": [
    {"barcode": "...", "name": "...", "count": 14, "sparkline": [3, 4, 2, 5]}
  ],
  "categories": [
    {"category": "Milchprodukte", "inventory_count": 12, "on_order_count": 3}
  ],
  "restock_costs": {
    "total_cents": 8740,
    "previous_period_cents": 9930,
    "weekly": [
      {"week": "KW11", "cents": 1800},
      {"week": "KW12", "cents": 2400}
    ]
  },
  "storage_locations": [
    {"name": "Kühlschrank", "item_count": 18}
  ]
}
```

#### `GET /api/dashboard/product/{barcode}`
Returns detailed consumption history for one product.

Query params:
- `days` (int, default 30)

Response shape:
```json
{
  "barcode": "...",
  "name": "...",
  "current_quantity": 3,
  "min_quantity": 2,
  "history": [
    {"timestamp": "...", "quantity_after": 5, "action": "scan-out"},
    {"timestamp": "...", "quantity_after": 8, "action": "restock_auto"}
  ],
  "stats": {
    "total_consumed": 14,
    "avg_per_week": 3.5,
    "times_restocked": 4,
    "total_cost_cents": 1260,
    "estimated_days_remaining": 6
  }
}
```

### Database Changes

#### InventoryItem
- Add `is_pinned: bool = False` column (new Alembic migration)

#### InventoryLog
- No schema changes needed. Already has all required fields (barcode, action, details, timestamp)
- Need to parse quantity changes from `details` text for history reconstruction. If `details` format is inconsistent, consider adding a `quantity_after` integer column for future log entries.

## Frontend

### New Dependencies
- `recharts` — React charting library (lightweight, composable, good MUI compatibility)

### New Components

#### `DashboardPage.tsx`
- New page component at route `/`
- Fetches `/api/dashboard/summary` on mount and on time-range change
- Renders all widgets in CSS Grid layout
- Time range selector as toggle buttons (7T/30T/90T)

#### Widget Components (in `components/dashboard/`)
- `PinnedProducts.tsx` — pinned items list with color-coded quantities
- `PendingOrders.tsx` — Picnic orders + cart summary
- `LowStockAlerts.tsx` — items below min_quantity
- `RecentActivity.tsx` — scrollable activity feed
- `ConsumptionTrend.tsx` — recharts LineChart, full width
- `TopConsumers.tsx` — ranked list with sparklines, click handler
- `CategoryBreakdown.tsx` — recharts horizontal BarChart with stacked segments
- `RestockCosts.tsx` — total + trend + recharts BarChart
- `StorageLocations.tsx` — recharts horizontal BarChart
- `ProductDetail.tsx` — expandable panel with recharts StepLine chart + stats

### Hooks
- `useDashboard(days)` — fetches summary endpoint, returns data + loading + refetch
- `useProductDetail(barcode, days)` — fetches product detail endpoint on demand

### Routing Change
- `/` → `DashboardPage`
- `/inventory` → `InventoryPage` (moved from `/`)
- Navigation menu updated accordingly

## Chart Library

Using `recharts` because:
- React-native composable components (not a canvas wrapper)
- Good TypeScript support
- Lightweight (~40kb gzipped)
- Supports all needed chart types: LineChart, BarChart, custom step-lines
- Works well with MUI theming

## Data Aggregation Strategy

All analytics are computed server-side from InventoryLog. The log already captures every inventory mutation with timestamps. Aggregation approach:

1. **Consumption**: Count InventoryLog entries where `action in ('remove', 'scan-out')`, grouped by time bucket (week) and optionally by category (join through InventoryItem)
2. **Restock costs**: Count InventoryLog entries where `action = 'restock_auto'`, parse quantity delta from `details`, multiply by `PicnicProduct.last_price_cents`
3. **Product history**: Query all InventoryLog entries for a barcode, ordered by timestamp. Reconstruct quantity timeline by working backwards from current quantity or by parsing `details` field.
4. **Consumption rate**: total consumed / days in range, extrapolated to per-week

The `details` field in InventoryLog stores human-readable strings like "quantity: 5 → 3". For reliable aggregation, the parsing needs to handle the existing format. A future improvement could add structured fields, but is not required for v1.
