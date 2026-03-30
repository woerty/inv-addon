"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "storage_locations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "inventory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("barcode", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("storage_location_id", sa.Integer(), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("added_date", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_date", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["storage_location_id"], ["storage_locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_inventory_barcode"), "inventory", ["barcode"], unique=True)

    op.create_table(
        "chat_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_history_session_id"), "chat_history", ["session_id"], unique=False)

    op.create_table(
        "inventory_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("barcode", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("inventory_log")
    op.drop_index(op.f("ix_chat_history_session_id"), table_name="chat_history")
    op.drop_table("chat_history")
    op.drop_index(op.f("ix_inventory_barcode"), table_name="inventory")
    op.drop_table("inventory")
    op.drop_table("storage_locations")
