"""create settlements: payments members record against their balances

Revision ID: 0012
Revises: 0011
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settlements",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=False),
        sa.Column("to_user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount > 0 AND amount <= 9999999999.99", name="ck_settlements_amount"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_settlements_currency"),
        sa.CheckConstraint("from_user_id <> to_user_id", name="ck_settlements_distinct_parties"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], name="fk_settlements_trip", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.id"], name="fk_settlements_from", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.id"], name="fk_settlements_to", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], name="fk_settlements_recorder", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_settlements_trip_id", "settlements", ["trip_id"])


def downgrade() -> None:
    op.drop_index("ix_settlements_trip_id", table_name="settlements")
    op.drop_table("settlements")
