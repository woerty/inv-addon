from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, model_validator


# --- Status ---

class PicnicStatusResponse(BaseModel):
    enabled: bool
    needs_login: bool = False  # True when credentials set but token missing / stale
    account: dict | None = None  # {"first_name": ..., "last_name": ..., "email": ...}


# --- Login flow (web-based 2FA) ---

class PicnicLoginStartResponse(BaseModel):
    status: Literal["ok", "awaiting_2fa"]


class PicnicLoginSendCodeRequest(BaseModel):
    channel: Literal["SMS", "EMAIL"] = "SMS"


class PicnicLoginSendCodeResponse(BaseModel):
    status: Literal["sent"] = "sent"


class PicnicLoginVerifyRequest(BaseModel):
    code: str


class PicnicLoginVerifyResponse(BaseModel):
    status: Literal["ok"] = "ok"


# --- Import flow ---

class MatchSuggestion(BaseModel):
    inventory_barcode: str
    inventory_name: str
    score: float  # 0-100
    reason: str


class ImportCandidate(BaseModel):
    picnic_id: str
    picnic_name: str
    picnic_image_id: str | None = None
    picnic_unit_quantity: str | None = None
    ordered_quantity: int
    match_suggestions: list[MatchSuggestion] = []
    best_confidence: float = 0.0


class ImportDelivery(BaseModel):
    delivery_id: str
    delivered_at: datetime | None = None
    items: list[ImportCandidate]


class ImportFetchResponse(BaseModel):
    deliveries: list[ImportDelivery]


class ImportDecision(BaseModel):
    picnic_id: str
    action: Literal["match_existing", "create_new", "skip"]
    target_barcode: str | None = None
    scanned_ean: str | None = None
    storage_location: str | None = None
    expiration_date: date | None = None

    @model_validator(mode="after")
    def _check_action_consistency(self) -> "ImportDecision":
        if self.action == "match_existing" and not self.target_barcode:
            raise ValueError("match_existing requires target_barcode")
        return self


class ImportCommitRequest(BaseModel):
    delivery_id: str
    decisions: list[ImportDecision]


class ImportCommitResponse(BaseModel):
    imported: int
    created: int
    skipped: int
    promoted: int  # synthetic -> real EAN promotions


# --- Search (fallback for unavailable items) ---

class PicnicSearchResult(BaseModel):
    picnic_id: str
    name: str
    unit_quantity: str | None = None
    image_id: str | None = None
    price_cents: int | None = None


class PicnicSearchResponse(BaseModel):
    results: list[PicnicSearchResult]


# --- Cache (admin / debug) ---

class PicnicProductCacheEntry(BaseModel):
    picnic_id: str
    ean: str | None
    name: str
    unit_quantity: str | None
    image_id: str | None
    last_price_cents: int | None
    last_seen: datetime

    model_config = {"from_attributes": True}


# ── Cart (Picnic as source of truth) ──────────────────────────────

class CartItemResponse(BaseModel):
    picnic_id: str
    name: str
    quantity: int
    unit_quantity: str | None = None
    image_id: str | None = None
    price_cents: int | None = None
    total_price_cents: int | None = None


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    total_items: int
    total_price_cents: int


class CartModifyRequest(BaseModel):
    picnic_id: str
    count: int = 1


# ── Pending Orders ────────────────────────────────────────────────

class PendingOrderItem(BaseModel):
    picnic_id: str
    name: str
    quantity: int
    image_id: str | None = None
    price_cents: int | None = None  # regular per-unit price
    promo_price_cents: int | None = None  # discounted per-unit price, if on offer
    promo_text: str | None = None  # e.g. "-40% auf 2. Artikel"


class PendingOrder(BaseModel):
    delivery_id: str
    status: str
    delivery_time: datetime | None = None
    total_items: int
    total_price_cents: int | None = None
    items: list[PendingOrderItem]


class PendingOrdersResponse(BaseModel):
    orders: list[PendingOrder]
    quantity_map: dict[str, int]


# ── Delivery slots / checkout ─────────────────────────────────────

class DeliverySlot(BaseModel):
    slot_id: str
    window_start: datetime
    window_end: datetime
    cut_off_time: datetime | None = None
    is_available: bool = True
    selected: bool = False
    reserved: bool = False
    minimum_order_value_cents: int | None = None


class DeliverySlotsResponse(BaseModel):
    slots: list[DeliverySlot]
    selected_slot_id: str | None = None
    cart_total_price_cents: int = 0


class SetSlotRequest(BaseModel):
    slot_id: str


class OrderPlacedResult(BaseModel):
    order_id: str
    status: str
    total_price_cents: int | None = None


# ── Offers ────────────────────────────────────────────────────────

class OfferItem(BaseModel):
    picnic_id: str
    name: str
    image_id: str | None = None
    unit_quantity: str | None = None
    price_cents: int | None = None  # current (discounted) price
    original_price_cents: int | None = None  # strikethrough price, if shown
    promo_label: str | None = None  # e.g. "20% Rabatt", "jetzt 0.99€"


class OffersResponse(BaseModel):
    offers: list[OfferItem]


# ── Product Detail ────────────────────────────────────────────────

class BundleTier(BaseModel):
    picnic_id: str
    quantity: int
    unit_price_cents: int | None = None
    total_price_cents: int | None = None
    savings_text: str | None = None


class ProductDetailResponse(BaseModel):
    picnic_id: str
    name: str
    unit_quantity: str | None = None
    image_id: str | None = None
    price_cents: int | None = None
    description: str | None = None
    in_cart: int = 0
    on_order: int = 0
    inventory_quantity: int = 0
    is_subscribed: bool = False
    bundles: list[BundleTier] = []


# ── Categories ────────────────────────────────────────────────────

class CategoryItem(BaseModel):
    picnic_id: str
    name: str
    unit_quantity: str | None = None
    image_id: str | None = None
    price_cents: int | None = None


class SubCategory(BaseModel):
    id: str
    name: str
    image_id: str | None = None
    items: list[CategoryItem] = []


class Category(BaseModel):
    id: str
    name: str
    image_id: str | None = None
    children: list[SubCategory] = []


class CategoriesResponse(BaseModel):
    categories: list[Category]
