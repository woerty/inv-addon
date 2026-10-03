"""Tests for the PicnicClient boundary over python-picnic-api2 2.x.

2.x returns pydantic models; the wrapper must hand callers the same raw dicts
the 1.x library returned (verified live against 1.3.4 on 2026-10-03), and must
raise -- not pass through -- when Picnic answers with an error payload.
The fake below stands in for the library's HTTP layer only: the model
classes and their parsing are the real ones.
"""

from __future__ import annotations

import pytest
from python_picnic_api2 import Cart, Delivery, DeliverySummary, SearchResult, User
from python_picnic_api2.session import PicnicAuthError

from app.services.picnic.client import PicnicAPIError, PicnicClient, _is_auth_error

CART = {
    "type": "ORDER",
    "id": "shopping_cart",
    "items": [
        {
            "type": "ORDER_LINE",
            "id": "line-1",
            "items": [{"type": "ORDER_ARTICLE", "id": "s1172792", "name": "Weidemilch"}],
        }
    ],
    "total_count": 4,
}
PICNIC_ERROR = {
    "error": {
        "code": "UNPROCESSABLE_CONTENT",
        "message": "Client version is required to preview the cart page.",
        "details": {},
    }
}
SEARCH_PAGE = {
    "body": {
        "child": {
            "children": [
                {
                    "type": "SELLING_UNIT_TILE",
                    "sellingUnit": {"id": "s1028032", "name": "Schlagsahne", "display_price": 89},
                }
            ]
        }
    }
}


class FakeLibrary:
    """Answers like python-picnic-api2 2.x, with canned payloads."""

    def __init__(self, cart: dict = CART) -> None:
        self.cart = cart

    def get_cart(self):
        return Cart.from_api(self.cart)

    def add_product(self, product_id, count=1):
        return Cart.from_api(self.cart)

    def get_user(self):
        return User.from_api({"user_id": "u1", "firstname": "Dustin"})

    def get_deliveries(self):
        return [DeliverySummary.from_api({"delivery_id": "d1", "status": "COMPLETED"})]

    def get_delivery(self, delivery_id):
        return Delivery.from_api({"delivery_id": delivery_id, "orders": []})

    def search(self, term):
        return SearchResult.from_page(SEARCH_PAGE)


def _client(library: FakeLibrary) -> PicnicClient:
    client = PicnicClient()
    client._inner = library  # skip login; _ensure_ready returns early
    return client


async def test_models_are_unwrapped_to_the_raw_payload():
    client = _client(FakeLibrary())

    assert await client.get_cart() == CART
    assert await client.add_product("s1172792") == CART
    assert (await client.get_user())["firstname"] == "Dustin"
    assert await client.get_deliveries() == [{"delivery_id": "d1", "status": "COMPLETED"}]
    assert await client.get_delivery("d1") == {"delivery_id": "d1", "orders": []}


async def test_search_keeps_the_1x_group_shape():
    client = _client(FakeLibrary())

    groups = await client.search("sahne")

    assert groups == [
        {
            "items": [
                {
                    "id": "s1028032",
                    "name": "Schlagsahne",
                    "display_price": 89,
                    # None on every live hit, in 1.3.4 and 2.x alike.
                    "sole_article_id": None,
                }
            ]
        }
    ]


async def test_error_payload_on_cart_read_raises():
    client = _client(FakeLibrary(cart=PICNIC_ERROR))

    with pytest.raises(PicnicAPIError, match="Client version is required"):
        await client.get_cart()


async def test_error_payload_on_cart_write_raises():
    """A rejected add must not look like a success: restock logged
    'cart delta=N' for adds Picnic had refused."""
    client = _client(FakeLibrary(cart=PICNIC_ERROR))

    with pytest.raises(PicnicAPIError):
        await client.add_product("s1172792", count=2)


def test_library_auth_error_counts_as_auth_error():
    assert _is_auth_error(PicnicAuthError("Picnic authentication error"))
    assert not _is_auth_error(ValueError("boom"))
