from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("inventory_log", sa.Column("name", sa.String(), nullable=True))
    op.add_column("inventory_log", sa.Column("quantity_before", sa.Integer(), nullable=True))
    op.add_column("inventory_log", sa.Column("quantity_after", sa.Integer(), nullable=True))
    # Best effort: names of items still in the inventory, then of restock
    # rules (whose barcodes the restock entries use). Rows of items that are
    # gone stay without a name.
    for table in ("inventory", "tracked_products"):
        op.execute(
            f"UPDATE inventory_log SET name = "
            f"(SELECT {table}.name FROM {table} WHERE {table}.barcode = inventory_log.barcode) "
            f"WHERE name IS NULL"
        )


def downgrade() -> None:
    op.drop_column("inventory_log", "quantity_after")
    op.drop_column("inventory_log", "quantity_before")
    op.drop_column("inventory_log", "name")
