from app.services.custom_products import (
    CUSTOM_BARCODE_PREFIX,
    is_custom_barcode,
    make_custom_barcode,
)


def test_make_custom_barcode_has_prefix():
    bc = make_custom_barcode()
    assert bc.startswith(CUSTOM_BARCODE_PREFIX)
    assert is_custom_barcode(bc)


def test_make_custom_barcode_is_unique():
    assert make_custom_barcode() != make_custom_barcode()


def test_real_ean_is_not_custom():
    assert not is_custom_barcode("4006381333931")
    assert not is_custom_barcode("picnic:12345")
