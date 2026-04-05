"""add index on tracked_products.picnic_id

Revision ID: 005
Revises: 004
Create Date: 2026-04-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_tracked_products_picnic_id", "tracked_products", ["picnic_id"])


def downgrade() -> None:
    op.drop_index("ix_tracked_products_picnic_id", table_name="tracked_products")
