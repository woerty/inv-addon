from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrackedProductCreate(BaseModel):
    barcode: str = Field(min_length=1)
    min_quantity: int = Field(ge=0)
    target_quantity: int = Field(gt=0)

    @model_validator(mode="after")
    def _target_gt_min(self) -> "TrackedProductCreate":
        if self.target_quantity <= self.min_quantity:
            raise ValueError("target_quantity must be greater than min_quantity")
        return self


class TrackedProductUpdate(BaseModel):
    min_quantity: int | None = Field(default=None, ge=0)
    target_quantity: int | None = Field(default=None, gt=0)


class TrackedProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    barcode: str
    picnic_id: str
    name: str
    picnic_name: str
    picnic_image_id: str | None
    picnic_unit_quantity: str | None
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
    picnic_id: str | None
    picnic_name: str | None
    picnic_image_id: str | None
    picnic_unit_quantity: str | None
    reason: str | None  # "cache_hit" | "live_lookup" | "not_in_picnic_catalog"
