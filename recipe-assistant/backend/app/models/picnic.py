from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PicnicProduct(Base):
    """Cache of Picnic catalog entries + learned EAN pairing.

    ean is nullable and indexed. It is populated whenever:
      - get_article_by_gtin(ean) succeeds (cart sync path)
      - user scans or confirms an EAN during import review

    ean is NOT unique: one EAN may map to multiple Picnic SKUs (pack sizes).
    On resolution we pick the most recently seen match (ORDER BY last_seen DESC).
    """
    __tablename__ = "picnic_products"

    picnic_id: Mapped[str] = mapped_column(String, primary_key=True)
    ean: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit_quantity: Mapped[str | None] = mapped_column(String, nullable=True)
    image_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None),
        server_default=func.now(), onupdate=func.now()
    )


class PicnicDeliveryImport(Base):
    """Dedup record of which Picnic deliveries have been imported."""
    __tablename__ = "picnic_delivery_imports"

    delivery_id: Mapped[str] = mapped_column(String, primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)


