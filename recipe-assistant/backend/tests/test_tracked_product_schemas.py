import pytest
from pydantic import ValidationError

from app.schemas.tracked_product import TrackedProductCreate


def test_create_accepts_valid_values():
    body = TrackedProductCreate(barcode="4014400900057", min_quantity=1, target_quantity=4)
    assert body.min_quantity == 1
    assert body.target_quantity == 4


def test_create_rejects_target_equal_to_min():
    with pytest.raises(ValidationError, match="greater than min_quantity"):
        TrackedProductCreate(barcode="123", min_quantity=2, target_quantity=2)


def test_create_rejects_target_less_than_min():
    with pytest.raises(ValidationError, match="greater than min_quantity"):
        TrackedProductCreate(barcode="123", min_quantity=5, target_quantity=3)


def test_create_rejects_negative_min():
    with pytest.raises(ValidationError):
        TrackedProductCreate(barcode="123", min_quantity=-1, target_quantity=3)


def test_create_rejects_zero_target():
    with pytest.raises(ValidationError):
        TrackedProductCreate(barcode="123", min_quantity=0, target_quantity=0)


def test_create_rejects_empty_barcode():
    with pytest.raises(ValidationError):
        TrackedProductCreate(barcode="", min_quantity=1, target_quantity=2)
