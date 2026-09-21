"""create itinerary items

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "itinerary_items",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "end_time IS NULL OR (start_time IS NOT NULL AND end_time >= start_time)",
            name="ck_itinerary_times",
        ),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_itinerary_title"),
        sa.CheckConstraint("position > 0", name="ck_itinerary_position"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],
                                name="fk_itinerary_creator", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"],
                                name="fk_itinerary_trip", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "date", "position", name="uq_itinerary_trip_date_position"),
    )
    op.create_index("ix_itinerary_items_created_by_user_id", "itinerary_items", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_itinerary_items_created_by_user_id", table_name="itinerary_items")
    op.drop_table("itinerary_items")
