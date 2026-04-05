from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, model_validator


# --- Status ---

class PicnicStatusResponse(BaseModel):
    enabled: bool
    account: dict | None = None  # {"first_name": ..., "last_name": ..., "email": ...}


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


# --- Shopping list ---

class ShoppingListItemResponse(BaseModel):
    id: int
    inventory_barcode: str | None
    picnic_id: str | None
    picnic_name: str | None  # resolved via GTIN lookup or cache
    name: str
    quantity: int
    picnic_status: Literal["mapped", "unavailable"]  # v2: no yellow state
    added_at: datetime

    model_config = {"from_attributes": True}


class ShoppingListAddRequest(BaseModel):
    inventory_barcode: str | None = None
    picnic_id: str | None = None
    name: str
    quantity: int = 1


class ShoppingListUpdateRequest(BaseModel):
    quantity: int | None = None
    picnic_id: str | None = None


class CartSyncItemResult(BaseModel):
    shopping_list_id: int
    picnic_id: str | None
    status: Literal["added", "skipped_unmapped", "failed"]
    failure_reason: str | None = None


class CartSyncResponse(BaseModel):
    results: list[CartSyncItemResult]
    added_count: int
    failed_count: int
    skipped_count: int


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
