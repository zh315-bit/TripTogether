"""create trips table

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("destination", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_trips_date_range"),
        sa.CheckConstraint(
            "length(btrim(destination)) > 0", name="ck_trips_destination_not_blank"
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_trips_name_not_blank"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_trips_owner_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trips_owner_id", "trips", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trips_owner_id", table_name="trips")
    op.drop_table("trips")
