# Picnic Store Redesign — Full Store Experience

**Date:** 2026-04-08
**Status:** Approved

## Overview

Transform the existing fragmented Picnic integration (separate Store, Shopping List, Import, Tracked Products pages) into a unified, full-featured Picnic Store experience. The Picnic cart becomes the single source of truth — no local shopping list. Pending orders are tracked and surfaced throughout the app.

## Core Decisions

- **Picnic cart = only cart.** No local shopping list. Every cart action goes directly to Picnic API. The `ShoppingListItem` model and all associated code are removed.
- **Pending order awareness.** Products in not-yet-delivered orders are shown as "X in Bestellung" with orange badges in the Store, Inventory, and Subscriptions views. Tracked products below threshold but already on order show yellow (not red).
- **Auto-restock → direct to cart.** The restock service adds products directly to the Picnic cart (checking pending orders first to avoid duplicates), instead of creating shopping list entries.
- **One nav entry.** All Picnic functionality lives under a single "Picnic" navigation entry.

## Architecture

### Page Structure

`PicnicStorePage.tsx` is a thin shell with:
- **Search bar** at the top (always visible, triggers search in Store tab)
- **4 Tabs:** Store, Warenkorb (with item count badge), Bestellungen, Abos

Each tab is its own component. Shared data (cart contents, pending order quantities) is loaded by the shell and passed down.

### Frontend File Structure

```
components/picnic/
  store/
    StoreTab.tsx            — Category navigation + product grid
    CategoryChips.tsx       — Top-level category chips
    SubCategoryChips.tsx    — Sub-category chips
    ProductGrid.tsx         — Product card grid
    ProductCard.tsx         — Single product card (image, price, badges)
    ProductDetailModal.tsx  — Detail modal with full info + cart controls
  cart/
    CartTab.tsx             — Cart overview, editable
    CartItem.tsx            — Single cart row with +/- buttons
  orders/
    OrdersTab.tsx           — Pending + past orders, import
    OrderCard.tsx           — Single order (expandable)
    ImportSection.tsx       — Import logic (refactored from PicnicImportPage)
  subscriptions/
    SubscriptionsTab.tsx    — Tracked products / subscriptions management
    SubscriptionCard.tsx    — Single subscription with min/target display
```

### Hooks

- `usePicnicCart()` — Fetches `GET /api/picnic/cart`, exposes `add(picnicId, count)`, `remove(picnicId, count)`, `clear()`. Auto-refetches after mutations.
- `usePicnicCategories()` — Fetches `GET /api/picnic/categories`, caches result.
- `usePicnicPendingOrders()` — Fetches `GET /api/picnic/orders/pending`. Returns `orders` list and `quantityMap: Record<string, number>` for fast lookup.
- `usePicnicProduct(picnicId)` — Fetches `GET /api/picnic/products/{picnicId}` lazily when modal opens.
- `usePicnicSearch(query)` — Existing hook, extended to include cart/order badge data.
- `usePicnicStatus()` — Existing, unchanged.
- `usePicnicLogin()` — Existing, unchanged.
- `usePicnicImport()` — Existing, moved into orders context.

`useShoppingList()` is removed entirely.

## Backend Changes

### New Endpoints

#### `GET /api/picnic/categories?depth=2`

Returns hierarchical category tree from Picnic.

Response:
```json
{
  "categories": [
    {
      "id": "...",
      "name": "Obst & Gemuese",
      "image_id": "...",
      "children": [
        {
          "id": "...",
          "name": "Aepfel & Birnen",
          "image_id": "...",
          "items": [
            {"picnic_id": "...", "name": "...", "unit_quantity": "1kg", "image_id": "...", "price_cents": 299}
          ]
        }
      ]
    }
  ]
}
```

#### `GET /api/picnic/products/{picnic_id}`

Fetches product details via `get_article(article_id)`. Returns:
```json
{
  "picnic_id": "...",
  "name": "...",
  "unit_quantity": "1L",
  "image_id": "...",
  "price_cents": 199,
  "description": "...",
  "in_cart": 2,
  "on_order": 1,
  "inventory_quantity": 3,
  "is_subscribed": true
}
```

`in_cart`: from current Picnic cart. `on_order`: aggregated from pending orders. `inventory_quantity`: via EAN match in PicnicProduct cache → Inventory lookup. `is_subscribed`: via TrackedProduct lookup.

#### `GET /api/picnic/cart`

Fetches current Picnic cart, enriched with metadata:
```json
{
  "items": [
    {
      "picnic_id": "...",
      "name": "...",
      "quantity": 2,
      "unit_quantity": "1L",
      "image_id": "...",
      "price_cents": 199,
      "total_price_cents": 398
    }
  ],
  "total_items": 5,
  "total_price_cents": 1245
}
```

#### `POST /api/picnic/cart/add`

Request: `{"picnic_id": "...", "count": 1}`
Calls `client.add_product()`. Returns updated cart.

#### `POST /api/picnic/cart/remove`

Request: `{"picnic_id": "...", "count": 1}`
Calls `client.remove_product()`. Returns updated cart.

#### `POST /api/picnic/cart/clear`

Calls `client.clear_cart()`. Returns empty cart.

#### `GET /api/picnic/orders/pending`

Fetches deliveries via `client.get_deliveries()`, filters to those with status indicating not yet delivered (e.g., `CURRENT`, `PENDING`, `ANNOUNCED` — excludes `COMPLETED` and `CANCELLED`), enriches with item details via `get_delivery()`.

Response:
```json
{
  "orders": [
    {
      "delivery_id": "...",
      "status": "...",
      "delivery_time": "2026-04-10T14:00:00",
      "total_items": 12,
      "items": [
        {"picnic_id": "...", "name": "...", "quantity": 2, "image_id": "...", "price_cents": 199}
      ]
    }
  ],
  "quantity_map": {
    "picnic_123": 2,
    "picnic_456": 1
  }
}
```

`quantity_map` aggregates quantities across all pending orders for fast frontend lookup.

### Removed Endpoints

- `GET /api/picnic/shopping-list`
- `POST /api/picnic/shopping-list`
- `PATCH /api/picnic/shopping-list/{item_id}`
- `DELETE /api/picnic/shopping-list/{item_id}`
- `POST /api/picnic/shopping-list/sync`

### Modified Services

#### Restock Service

Currently creates `ShoppingListItem` entries. Changed to:
1. Check `quantity_map` from pending orders — if product already on order, skip or add only delta
2. Check current cart — if product already in cart, skip or add only delta
3. Call `client.add_product(picnic_id, delta)` directly

#### cart.py

- `sync_shopping_list_to_cart()` — removed
- `resolve_shopping_list_status()` — removed
- `_parse_cart_quantities()` — kept, used by new cart endpoint

### Database Migration

One Alembic migration:
- `DROP TABLE shopping_list_items`

## UI Details

### Category Navigation (Store Tab)

Chip/Tab-based, similar to Picnic app:
- Top-level categories as horizontally scrollable chips
- Sub-categories as second row of chips below
- Products displayed as grid of cards

Search bar at top works independently of category navigation.

### Product Card

Displays:
- Product image
- Name, unit quantity, price
- Badges (only when > 0):
  - Blue: "X im Warenkorb"
  - Orange: "X in Bestellung"
  - Green: "X im Inventar"
- Subscription icon if tracked

Click opens ProductDetailModal.

### Product Detail Modal

- Large product image
- Name, price, unit quantity
- Badges (only when values > 0):
  - "X im Warenkorb" (blue)
  - "X in Bestellung" (orange)
  - "X im Inventar" (green)
- Description/details (if available from API)
- Cart controls:
  - Not in cart: quantity selector (default 1) + "In den Warenkorb" button
  - Already in cart: +/- buttons, live quantity editing, changes sent immediately to Picnic API
- Subscribe button (opens SubscribeDialog) or "Abonniert" chip

### Cart Tab

- List of all items in Picnic cart
- Each item: image, name, price, quantity with +/- buttons
- Remove button per item
- Total price at bottom
- "Warenkorb leeren" action

### Orders Tab

- **Pending orders** at top: card per order with delivery date, item count, expandable item list
- **Past orders** below: same format, plus import functionality (refactored from PicnicImportPage)
- Import flow uses existing ReviewCard/MatchCandidateList components

### Subscriptions Tab (Abos)

- List of all tracked products
- Each shows: product image, name, current quantity, min/target thresholds
- Color coding:
  - Green: current >= min
  - Yellow: current < min BUT product in pending order
  - Red: current < min AND not in pending order
- Edit/delete subscription
- "Neues Abo" button (opens product search → SubscribeDialog)

### Inventory Page Changes

For inventory items with a Picnic EAN match that appear in pending orders:
- Orange chip: "X in Bestellung" next to the quantity

### Navbar Changes

Old entries removed: Picnic Store, Einkaufsliste, Nachbestellungen, Picnic-Import

New single entry: **"Picnic"** → PicnicStorePage

PicnicLoginPage remains at `/picnic-login` (shown when `needs_login=true`).

## EAN Bridge

The connection between Picnic products and inventory items uses the existing `PicnicProduct` cache table which has an `ean` field. When an inventory item has barcode X and a `PicnicProduct` exists with `ean=X`, the match is established. No new tables needed.

## Client Library Methods (python-picnic-api2)

New methods to expose in the PicnicClient wrapper:
- `get_categories(depth)` — catalog browsing
- `get_article(article_id)` — product details
- `remove_product(product_id, count)` — remove from cart
- `clear_cart()` — empty cart
- `get_delivery_slots()` — (future use, not in scope for now)

Existing methods already wrapped: `search()`, `get_cart()`, `add_product()`, `get_deliveries()`, `get_delivery()`, `get_article_by_gtin()`, `get_user()`.
