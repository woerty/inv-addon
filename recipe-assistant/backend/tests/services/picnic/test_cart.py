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
