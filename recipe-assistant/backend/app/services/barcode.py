from __future__ import annotations

import httpx

OPENFOODFACTS_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
TIMEOUT_SECONDS = 5.0

FALLBACK = {"name": "Unbekanntes Produkt", "category": "Unbekannt"}


async def lookup_barcode(barcode: str) -> dict[str, str]:
    """Look up a barcode on OpenFoodFacts. Returns dict with 'name' and 'category'."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(OPENFOODFACTS_URL.format(barcode=barcode))
            data = response.json()

        if data.get("status") != 1:
            return FALLBACK

        product = data.get("product", {})
        return {
            "name": product.get("product_name") or FALLBACK["name"],
            "category": product.get("categories") or FALLBACK["category"],
        }
    except (httpx.TimeoutException, httpx.HTTPError):
        return FALLBACK
