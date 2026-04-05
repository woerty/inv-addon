"""add tracked_products table

Revision ID: 004
Revises: 003
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_products",
        sa.Column("barcode", sa.String(), nullable=False),
        sa.Column("picnic_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("min_quantity", sa.Integer(), nullable=False),
        sa.Column("target_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("min_quantity >= 0", name="ck_tracked_min_nonneg"),
        sa.CheckConstraint(
            "target_quantity > min_quantity",
            name="ck_tracked_target_gt_min",
        ),
        sa.PrimaryKeyConstraint("barcode"),
    )


def downgrade() -> None:
    op.drop_table("tracked_products")
