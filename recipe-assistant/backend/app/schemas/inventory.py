from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class StorageLocationCreate(BaseModel):
    location_name: str


class StorageLocationResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class InventoryItemResponse(BaseModel):
    id: int
    barcode: str
    name: str
    quantity: int
    category: str
    storage_location: StorageLocationResponse | None = None
    expiration_date: date | None = None
    image_id: str | None = None
    added_date: datetime
    updated_date: datetime

    model_config = {"from_attributes": True}


class BarcodeAddRequest(BaseModel):
    barcode: str
    storage_location: str | None = None
    expiration_date: date | None = None


class BarcodeRemoveRequest(BaseModel):
    barcode: str


class InventoryUpdateRequest(BaseModel):
    quantity: int | None = None
    storage_location: str | None = None
    expiration_date: date | None = None


class ScanOutRequest(BaseModel):
    barcode: str


class ScanInRequest(BaseModel):
    barcode: str
    storage_location_id: int | None = None
