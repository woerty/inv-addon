from __future__ import annotations

import logging
import time
from typing import Any, Callable

from app.schemas.picnic import OfferItem, OffersResponse
from app.services.picnic.client import PicnicClientProtocol

log = logging.getLogger(__name__)

# The promo page is large (~4-5 MB) and offers change roughly weekly, so cache
# the parsed result briefly to avoid re-fetching/re-parsing on every page load.
_CACHE_TTL_SECONDS = 30 * 60
_cache: tuple[float, OffersResponse] | None = None


def _walk(node: Any, fn: Callable[[dict], None]) -> None:
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            _walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            _walk(v, fn)


def _promo_map(page: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """sku -> {label, strikethrough} from analytics promotion contexts.

    Each promoted tile carries an analytics block whose `contexts` array pairs a
    `product` context (product_id) with a `promotion` context (promotion_label,
    strikethrough_price).
    """
    out: dict[str, dict[str, Any]] = {}

    def visit(n: dict) -> None:
        analytics = n.get("analytics")
        if not isinstance(analytics, dict):
            return
        ctxs = analytics.get("contexts")
        if not isinstance(ctxs, list):
            return
        sku = label = strike = None
        for ctx in ctxs:
            data = ctx.get("data", {}) if isinstance(ctx, dict) else {}
            if "product_id" in data:
                sku = data["product_id"]
            if "promotion_label" in data:
                label = data.get("promotion_label")
                strike = data.get("strikethrough_price")
        if sku and (label or strike):
            out[sku] = {"label": label, "strike": strike}

    _walk(page, visit)
    return out


def parse_offers(page: dict[str, Any]) -> OffersResponse:
    """Extract all current offers from the raw promo-page-root PML.

    Each SELLING_UNIT_TILE.sellingUnit is self-contained (id, name, image_id,
    display_price=current price, unit_quantity); the strikethrough/original price
    and human label come from the paired promotion analytics context.
    """
    promo = _promo_map(page)
    offers: list[OfferItem] = []
    seen: set[str] = set()

    def visit(n: dict) -> None:
        if n.get("type") != "SELLING_UNIT_TILE":
            return
        su = n.get("sellingUnit")
        if not isinstance(su, dict):
            return
        sku = su.get("id")
        if not sku or sku in seen:
            return
        seen.add(sku)
        p = promo.get(sku, {})
        offers.append(
            OfferItem(
                picnic_id=sku,
                name=su.get("name", ""),
                image_id=su.get("image_id"),
                unit_quantity=su.get("unit_quantity"),
                price_cents=su.get("display_price"),
                original_price_cents=p.get("strike"),
                promo_label=p.get("label"),
            )
        )

    _walk(page, visit)
    return OffersResponse(offers=offers)


async def get_offers(client: PicnicClientProtocol, *, force: bool = False) -> OffersResponse:
    """Fetch + parse current offers, cached for _CACHE_TTL_SECONDS."""
    global _cache
    now = time.monotonic()
    if not force and _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]
    page = await client.get_promo_page()
    result = parse_offers(page)
    _cache = (now, result)
    return result


def _reset_cache() -> None:
    """Test hook to clear the module-level cache."""
    global _cache
    _cache = None
