from __future__ import annotations

import httpx

TIMEOUT_SECONDS = 5.0
FALLBACK = {"name": "Unbekanntes Produkt", "category": "Unbekannt"}


async def _lookup_openfoodfacts(barcode: str, client: httpx.AsyncClient) -> dict[str, str] | None:
    """OpenFoodFacts - largest open food database."""
    try:
        response = await client.get(
            f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
        )
        data = response.json()
        if data.get("status") != 1:
            return None
        product = data.get("product", {})
        name = product.get("product_name")
        if not name:
            return None
        return {
            "name": name,
            "category": product.get("categories") or "Unbekannt",
        }
    except (httpx.TimeoutException, httpx.HTTPError):
        return None


async def _lookup_openbeautyfacts(barcode: str, client: httpx.AsyncClient) -> dict[str, str] | None:
    """OpenBeautyFacts - for non-food products (cosmetics, cleaning, etc.)."""
    try:
        response = await client.get(
            f"https://world.openbeautyfacts.org/api/v0/product/{barcode}.json"
        )
        data = response.json()
        if data.get("status") != 1:
            return None
        product = data.get("product", {})
        name = product.get("product_name")
        if not name:
            return None
        return {
            "name": name,
            "category": product.get("categories") or "Unbekannt",
        }
    except (httpx.TimeoutException, httpx.HTTPError):
        return None


async def _lookup_openpetfoodfacts(barcode: str, client: httpx.AsyncClient) -> dict[str, str] | None:
    """OpenPetFoodFacts - for pet food products."""
    try:
        response = await client.get(
            f"https://world.openpetfoodfacts.org/api/v0/product/{barcode}.json"
        )
        data = response.json()
        if data.get("status") != 1:
            return None
        product = data.get("product", {})
        name = product.get("product_name")
        if not name:
            return None
        return {
            "name": name,
            "category": product.get("categories") or "Unbekannt",
        }
    except (httpx.TimeoutException, httpx.HTTPError):
        return None


async def _lookup_upcitemdb(barcode: str, client: httpx.AsyncClient) -> dict[str, str] | None:
    """UPCitemdb - general product database (free tier: 100 req/day)."""
    try:
        response = await client.get(
            f"https://api.upcitemdb.com/prod/trial/lookup?upc={barcode}"
        )
        data = response.json()
        items = data.get("items", [])
        if not items:
            return None
        item = items[0]
        name = item.get("title")
        if not name:
            return None
        return {
            "name": name,
            "category": item.get("category") or "Unbekannt",
        }
    except (httpx.TimeoutException, httpx.HTTPError):
        return None


# Providers in priority order
PROVIDERS = [
    ("OpenFoodFacts", _lookup_openfoodfacts),
    ("UPCitemdb", _lookup_upcitemdb),
    ("OpenBeautyFacts", _lookup_openbeautyfacts),
    ("OpenPetFoodFacts", _lookup_openpetfoodfacts),
]


async def lookup_barcode(barcode: str) -> dict[str, str]:
    """Look up a barcode across multiple providers. Returns first match."""
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        for _name, provider in PROVIDERS:
            result = await provider(barcode, client)
            if result:
                return result
    return FALLBACK
