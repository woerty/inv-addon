"""Parse the Picnic "Bündel-Bonus" (quantity-tier) block from a product page.

Picnic represents volume discounts ("kauf 2, spar 20 Cent") as a set of distinct
selling units on the product-details page, rendered in a BLOCK whose id starts
with ``product-page-bundles``. Each tier is its own SELLING_UNIT_TILE with:

  - ``content.sellingUnit.id``      → the tier's picnic_id
  - a ``PRICE`` node (``price``)     → per-unit price in cents
  - a digit RICH_TEXT next to a      → the quantity (e.g. "2", "4"); the base
    ``crossSmall`` icon                tier has no marker → quantity 1
  - a "Spare X Cent" RICH_TEXT       → human-readable savings label (optional)

The data lives ONLY on the product-details page — search results and similar
listings carry neither this block nor a ``price_ranges`` value.
"""

from __future__ import annotations

import re
from typing import Any

_COLOR_RE = re.compile(r"#\(#[0-9a-fA-F]{6}\)")
_SAVINGS_RE = re.compile(r"Spare\b.*?Cent", re.IGNORECASE)


def _clean(markdown: str) -> str:
    """Strip Picnic inline colour markers like ``#(#b40117)`` and whitespace."""
    return _COLOR_RE.sub("", markdown).strip()


def _walk(node: Any):
    """Yield every dict in an arbitrarily nested dict/list tree."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _find_bundles_block(page: dict) -> dict | None:
    for node in _walk(page):
        node_id = node.get("id")
        if (
            isinstance(node_id, str)
            and node_id.startswith("product-page-bundles")
            and node.get("type") == "BLOCK"
        ):
            return node
    return None


def _parse_tier(child: dict) -> dict | None:
    picnic_id: str | None = None
    unit_price: int | None = None
    has_cross = False
    savings: str | None = None
    int_markdowns: list[int] = []

    for node in _walk(child):
        content = node.get("content")
        if isinstance(content, dict) and content.get("type") == "SELLING_UNIT_TILE":
            selling_unit = content.get("sellingUnit")
            if isinstance(selling_unit, dict) and selling_unit.get("id"):
                picnic_id = selling_unit["id"]

        if node.get("type") == "PRICE" and isinstance(node.get("price"), int):
            if unit_price is None:
                unit_price = node["price"]

        if node.get("iconKey") == "crossSmall":
            has_cross = True

        markdown = node.get("markdown")
        if isinstance(markdown, str):
            cleaned = _clean(markdown)
            if savings is None and _SAVINGS_RE.search(cleaned):
                savings = cleaned
            if cleaned.isdigit():
                int_markdowns.append(int(cleaned))

    if picnic_id is None:
        return None

    quantity = int_markdowns[0] if (has_cross and int_markdowns) else 1
    total = unit_price * quantity if unit_price is not None else None
    return {
        "picnic_id": picnic_id,
        "quantity": quantity,
        "unit_price_cents": unit_price,
        "total_price_cents": total,
        "savings_text": savings,
    }


def parse_bundles(page: dict) -> list[dict]:
    """Return the quantity tiers for *page*, sorted ascending by quantity.

    Empty list if the page has no bundle block (the common case — most products
    have no volume discount).
    """
    block = _find_bundles_block(page)
    if not block:
        return []
    tiers = [t for child in block.get("children", []) if (t := _parse_tier(child))]
    tiers.sort(key=lambda t: t["quantity"])
    return tiers
