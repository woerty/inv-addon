"""add picnic tables

Revision ID: 003
Revises: 002
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "picnic_products",
        sa.Column("picnic_id", sa.String(), nullable=False),
        sa.Column("ean", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("unit_quantity", sa.String(), nullable=True),
        sa.Column("image_id", sa.String(), nullable=True),
        sa.Column("last_price_cents", sa.Integer(), nullable=True),
        sa.Column(
            "last_seen",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("picnic_id"),
    )
    op.create_index("ix_picnic_products_ean", "picnic_products", ["ean"])

    op.create_table(
        "picnic_delivery_imports",
        sa.Column("delivery_id", sa.String(), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("delivery_id"),
    )

    op.create_table(
        "shopping_list",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("inventory_barcode", sa.String(), nullable=True),
        sa.Column("picnic_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "added_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("shopping_list")
    op.drop_table("picnic_delivery_imports")
    op.drop_index("ix_picnic_products_ean", table_name="picnic_products")
    op.drop_table("picnic_products")
