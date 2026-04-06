from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class TrackedProductCreate(BaseModel):
    barcode: str | None = Field(default=None, min_length=1)
    picnic_id: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    min_quantity: int = Field(ge=0)
    target_quantity: int = Field(gt=0)

    @model_validator(mode="after")
    def _target_gte_min(self) -> "TrackedProductCreate":
        if self.target_quantity < self.min_quantity:
            raise ValueError("target_quantity must be >= min_quantity")
        return self

    @model_validator(mode="after")
    def _barcode_or_picnic_id(self) -> "TrackedProductCreate":
        if not self.barcode and not self.picnic_id:
            raise ValueError("either barcode or picnic_id must be provided")
        return self


class TrackedProductUpdate(BaseModel):
    min_quantity: int | None = Field(default=None, ge=0)
    target_quantity: int | None = Field(default=None, gt=0)


class TrackedProductRead(BaseModel):
    model_config = {"from_attributes": True}

    barcode: str
    picnic_id: str
    name: str
    picnic_name: str
    picnic_image_id: str | None = None
    picnic_unit_quantity: str | None = None
    min_quantity: int
    target_quantity: int
    current_quantity: int
    below_threshold: bool
    created_at: datetime
    updated_at: datetime


class ResolvePreviewRequest(BaseModel):
    barcode: str = Field(min_length=1)


class ResolvePreviewResponse(BaseModel):
    resolved: bool
    picnic_id: str | None = None
    picnic_name: str | None = None
    picnic_image_id: str | None = None
    picnic_unit_quantity: str | None = None
    reason: str | None = None  # "cache_hit" | "live_lookup" | "not_in_picnic_catalog"


class PromoteBarcodeRequest(BaseModel):
    new_barcode: str = Field(min_length=1)


class PromoteBarcodeResponse(BaseModel):
    model_config = {"from_attributes": True}

    tracked: TrackedProductRead
    merged: bool
