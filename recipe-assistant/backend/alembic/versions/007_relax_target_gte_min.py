"""relax tracked_products constraint: target >= min (was >)

Revision ID: 007
Revises: 006
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_tracked_target_gt_min", "tracked_products", type_="check")
    op.create_check_constraint(
        "ck_tracked_target_gte_min",
        "tracked_products",
        "target_quantity >= min_quantity",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tracked_target_gte_min", "tracked_products", type_="check")
    op.create_check_constraint(
        "ck_tracked_target_gt_min",
        "tracked_products",
        "target_quantity > min_quantity",
    )
