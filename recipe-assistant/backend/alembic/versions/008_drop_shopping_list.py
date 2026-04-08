"""drop shopping_list table

Revision ID: 008
Revises: 007
Create Date: 2026-04-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("shopping_list")


def downgrade() -> None:
    op.create_table(
        "shopping_list",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("inventory_barcode", sa.String, nullable=True),
        sa.Column("picnic_id", sa.String, nullable=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("added_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
