from __future__ import annotations

from app.services.picnic.offers import _reset_cache, get_offers, parse_offers
from tests.fixtures.picnic.fake_client import FakePicnicClient
from tests.fixtures.picnic.sample_deliveries import SAMPLE_PROMO_PAGE


def test_parse_offers_extracts_tiles_and_promo():
    resp = parse_offers(SAMPLE_PROMO_PAGE)
    assert len(resp.offers) == 2
    by_id = {o.picnic_id: o for o in resp.offers}

    gouda = by_id["s100"]
    assert gouda.name == "Gut&Günstig Gouda gerieben"
    assert gouda.image_id == "img-100"
    assert gouda.price_cents == 143  # current
    assert gouda.original_price_cents == 179  # strikethrough
    assert gouda.promo_label == "20% Rabatt"
    assert gouda.unit_quantity == "250g"

    # Promo without a strikethrough (e.g. "jetzt 0.99€") still surfaces.
    bread = by_id["s200"]
    assert bread.price_cents == 99
    assert bread.original_price_cents is None
    assert bread.promo_label == "jetzt 0.99€"


def test_parse_offers_dedupes_by_sku():
    page = {"children": [
        {"type": "SELLING_UNIT_TILE", "sellingUnit": {"id": "s1", "name": "A", "display_price": 100}},
        {"type": "SELLING_UNIT_TILE", "sellingUnit": {"id": "s1", "name": "A", "display_price": 100}},
    ]}
    assert len(parse_offers(page).offers) == 1


def test_parse_offers_empty_page():
    assert parse_offers({"foo": "bar"}).offers == []


async def test_get_offers_caches(monkeypatch):
    _reset_cache()
    client = FakePicnicClient()
    calls = {"n": 0}
    orig = client.get_promo_page

    async def counting():
        calls["n"] += 1
        return await orig()

    client.get_promo_page = counting  # type: ignore[method-assign]

    r1 = await get_offers(client)
    r2 = await get_offers(client)
    assert calls["n"] == 1  # second call served from cache
    assert r1.offers == r2.offers
    _reset_cache()
