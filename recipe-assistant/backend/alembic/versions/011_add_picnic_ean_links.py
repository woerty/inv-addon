from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "picnic_ean_links",
        sa.Column("ean", sa.String(), primary_key=True),
        sa.Column("picnic_id", sa.String(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_picnic_ean_links_picnic_id", "picnic_ean_links", ["picnic_id"])


def downgrade() -> None:
    op.drop_index("ix_picnic_ean_links_picnic_id", table_name="picnic_ean_links")
    op.drop_table("picnic_ean_links")
