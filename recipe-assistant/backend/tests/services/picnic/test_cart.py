from app.services.picnic.cart import parse_cart_response
from tests.fixtures.picnic.fake_client import FakePicnicClient


async def test_parse_cart_response_builds_items():
    client = FakePicnicClient()
    client.cart_items = {"s100": 2, "s200": 1}
    result = await parse_cart_response(client)
    assert result.total_items == 3
    assert len(result.items) == 2
    ids = {item.picnic_id for item in result.items}
    assert ids == {"s100", "s200"}


async def test_parse_cart_response_empty():
    client = FakePicnicClient()
    result = await parse_cart_response(client)
    assert result.total_items == 0
    assert result.items == []


async def test_parse_cart_response_reads_prices():
    """Inner cart article carries its price under ``price`` (not ``display_price``,
    which is the search-result field). Regression: cart showed €0,00 for all rows."""
    client = FakePicnicClient()
    client.cart = {
        "items": [
            {
                "id": "order-line-1",
                "items": [
                    {
                        "id": "s100",
                        "name": "Ja! Vollmilch 1 L",
                        "unit_quantity": "1 L",
                        "image_id": "img-100",
                        "price": 99,
                        "decorators": [{"type": "QUANTITY", "quantity": 2}],
                    }
                ],
            }
        ],
        "total_price": 198,
    }
    result = await parse_cart_response(client)
    assert result.total_items == 2
    item = result.items[0]
    assert item.price_cents == 99
    assert item.total_price_cents == 198
    assert result.total_price_cents == 198
