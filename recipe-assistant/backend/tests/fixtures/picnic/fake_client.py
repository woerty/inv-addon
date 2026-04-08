from __future__ import annotations

from typing import Any

from tests.fixtures.picnic.sample_deliveries import (
    SAMPLE_CART_EMPTY,
    SAMPLE_DELIVERIES_SUMMARY,
    SAMPLE_DELIVERY_DETAIL,
    SAMPLE_SEARCH_MILK,
    SAMPLE_USER,
)


class FakePicnicClient:
    """In-memory fake that satisfies PicnicClientProtocol."""

    def __init__(self) -> None:
        self.deliveries_summary = list(SAMPLE_DELIVERIES_SUMMARY)
        self.delivery_details = {"del-1": SAMPLE_DELIVERY_DETAIL}
        self.search_results: dict[str, list[dict[str, Any]]] = {
            "milch": SAMPLE_SEARCH_MILK,
        }
        # ean -> {"id": picnic_id, "name": ...} map for get_article_by_gtin
        self.gtin_lookup: dict[str, dict[str, Any]] = {
            "4014400900057": {"id": "s100", "name": "Ja! Vollmilch 1 L"},
            "8000270013122": {"id": "s200", "name": "Barilla Spaghetti Nr. 5 500 g"},
        }
        self.cart: dict[str, Any] = dict(SAMPLE_CART_EMPTY)
        self.user = dict(SAMPLE_USER)
        self.added_products: list[tuple[str, int]] = []
        self.gtin_calls: list[str] = []  # track calls to get_article_by_gtin
        self.raise_on_add: dict[str, str] = {}  # picnic_id -> reason
        self.removed_products: list[tuple[str, int]] = []
        self.cart_items: dict[str, int] = {}
        self.categories: list[dict[str, Any]] = []
        self.articles: dict[str, dict[str, Any]] = {}

    async def search(self, query: str) -> list[dict[str, Any]]:
        return self.search_results.get(query.lower(), [])

    async def get_article_by_gtin(self, ean: str) -> dict[str, Any] | None:
        self.gtin_calls.append(ean)
        return self.gtin_lookup.get(ean)

    async def get_deliveries(self) -> list[dict[str, Any]]:
        return self.deliveries_summary

    async def get_delivery(self, delivery_id: str) -> dict[str, Any]:
        return self.delivery_details[delivery_id]

    async def get_cart(self) -> dict[str, Any]:
        if self.cart_items:
            items = [
                {"id": picnic_id, "name": picnic_id, "quantity": qty}
                for picnic_id, qty in self.cart_items.items()
            ]
            return {"items": items, "total_price": 0}
        return self.cart

    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
        if picnic_id in self.raise_on_add:
            raise RuntimeError(self.raise_on_add[picnic_id])
        self.added_products.append((picnic_id, count))
        self.cart_items[picnic_id] = self.cart_items.get(picnic_id, 0) + count
        return {"ok": True}

    async def get_user(self) -> dict[str, Any]:
        return self.user

    async def remove_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
        self.removed_products.append((picnic_id, count))
        current = self.cart_items.get(picnic_id, 0)
        new_qty = max(0, current - count)
        if new_qty == 0:
            self.cart_items.pop(picnic_id, None)
        else:
            self.cart_items[picnic_id] = new_qty
        return {"ok": True}

    async def clear_cart(self) -> dict[str, Any]:
        self.cart_items.clear()
        return {"ok": True}

    async def get_categories(self, depth: int = 0) -> list[dict[str, Any]]:
        return self.categories

    async def get_article(self, article_id: str) -> dict[str, Any]:
        if article_id in self.articles:
            return self.articles[article_id]
        raise Exception(f"Article {article_id} not found")


# Static conformance check: ensures FakePicnicClient stays in sync with
# PicnicClientProtocol. If the protocol grows a new method, mypy/pyright
# will flag this line until the fake adds the method too.
from app.services.picnic.client import PicnicClientProtocol as _Protocol

_protocol_check: _Protocol = FakePicnicClient()
