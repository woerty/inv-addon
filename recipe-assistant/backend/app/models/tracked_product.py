from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrackedProduct(Base):
    """Auto-reorder rule for a product, keyed by EAN/barcode.

    Exists independently from InventoryItem — the rule persists even when
    the product is currently out of stock (quantity=0) or has never been
    in inventory. At creation time, the product MUST resolve to a Picnic
    SKU via get_article_by_gtin; picnic_id is enforced NOT NULL.
    """

    __tablename__ = "tracked_products"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    picnic_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    target_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("min_quantity >= 0", name="ck_tracked_min_nonneg"),
        CheckConstraint(
            "target_quantity > min_quantity",
            name="ck_tracked_target_gt_min",
        ),
    )
