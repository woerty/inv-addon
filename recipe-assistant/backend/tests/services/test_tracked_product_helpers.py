from app.services.tracked_products import (
    SYNTHETIC_BARCODE_PREFIX,
    is_synthetic_barcode,
    make_synthetic_barcode,
)


def test_make_synthetic_barcode():
    assert make_synthetic_barcode("s100") == "picnic:s100"


def test_is_synthetic_true():
    assert is_synthetic_barcode("picnic:s100") is True


def test_is_synthetic_false_real_ean():
    assert is_synthetic_barcode("4014400900057") is False


def test_is_synthetic_false_empty():
    assert is_synthetic_barcode("") is False


def test_prefix_constant():
    assert SYNTHETIC_BARCODE_PREFIX == "picnic:"
