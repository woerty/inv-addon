from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.picnic import PicnicProduct
from app.schemas.picnic import PicnicSearchResult
from app.services.picnic.client import PicnicClientProtocol

_IMAGE_BASE = "https://storefront-prod.de.picnicinternational.com/static/images"


def picnic_image_url(image_id: str) -> str:
    return f"{_IMAGE_BASE}/{image_id}/small.png"


@dataclass(frozen=True)
class PicnicProductData:
    """Data we may know about a Picnic product.

    ean is None when we've only seen the product via a delivery line item (no
    reverse lookup available). It's set when:
      - a get_article_by_gtin(ean) call returned this product
      - a user manually confirmed an EAN match during import review
      - a user scanned a barcode during import review
    """
    picnic_id: str
    ean: str | None
    name: str
    unit_quantity: str | None
    image_id: str | None
    last_price_cents: int | None


async def get_product(session: AsyncSession, picnic_id: str) -> PicnicProduct | None:
    result = await session.execute(
        select(PicnicProduct).where(PicnicProduct.picnic_id == picnic_id)
    )
    return result.scalar_one_or_none()


async def get_product_by_ean(session: AsyncSession, ean: str) -> PicnicProduct | None:
    """Find the most-recently-seen Picnic product with this EAN.

    Multiple rows may share the same EAN (different pack sizes of the same product);
    we return the one with the newest last_seen timestamp.
    """
    result = await session.execute(
        select(PicnicProduct)
        .where(PicnicProduct.ean == ean)
        .order_by(PicnicProduct.last_seen.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_product(session: AsyncSession, data: PicnicProductData) -> PicnicProduct:
    """Insert a new PicnicProduct or update mutable fields on an existing row.

    The ean field is special: if the caller passes ean=None and the row already
    has a non-null ean, the existing ean is preserved (don't clobber learned data).
    If the caller passes a new ean, it wins (overwrites).
    """
    existing = await get_product(session, data.picnic_id)
    if existing:
        existing.name = data.name
        existing.unit_quantity = data.unit_quantity
        existing.image_id = data.image_id
        existing.last_price_cents = data.last_price_cents
        if data.ean is not None:
            existing.ean = data.ean
        return existing

    row = PicnicProduct(
        picnic_id=data.picnic_id,
        ean=data.ean,
        name=data.name,
        unit_quantity=data.unit_quantity,
        image_id=data.image_id,
        last_price_cents=data.last_price_cents,
    )
    session.add(row)
    await session.flush()
    return row


async def image_urls_by_ean(session: AsyncSession, eans: list[str]) -> dict[str, str]:
    """Picnic CDN image per EAN, for the EANs the catalog has an image for."""
    if not eans:
        return {}
    rows = (
        await session.execute(
            select(PicnicProduct.ean, PicnicProduct.image_id)
            .where(PicnicProduct.ean.in_(eans))
            .where(PicnicProduct.image_id.isnot(None))
        )
    ).all()
    return {row.ean: picnic_image_url(row.image_id) for row in rows}


async def search_products(
    session: AsyncSession,
    client: PicnicClientProtocol,
    query: str,
    *,
    limit: int,
) -> list[PicnicSearchResult]:
    """Free-text Picnic search, up to `limit` hits; every hit is cached in
    picnic_products. One Picnic request. The caller commits."""
    results: list[PicnicSearchResult] = []
    for group in await client.search(query):
        for item in group.get("items", []):
            if len(results) >= limit:
                return results
            pid = item.get("id")
            if not pid:
                continue
            name = item.get("name", "")
            await upsert_product(
                session,
                PicnicProductData(
                    picnic_id=pid,
                    ean=None,
                    name=name,
                    unit_quantity=item.get("unit_quantity"),
                    image_id=item.get("image_id"),
                    last_price_cents=item.get("display_price"),
                ),
            )
            results.append(
                PicnicSearchResult(
                    picnic_id=pid,
                    name=name,
                    unit_quantity=item.get("unit_quantity"),
                    image_id=item.get("image_id"),
                    price_cents=item.get("display_price"),
                )
            )
    return results
