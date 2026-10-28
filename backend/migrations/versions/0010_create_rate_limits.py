"""create rate limit windows

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One row per (limit name, client) fixed window, shared by every worker and
    # instance, like the geocoder throttle. Stale rows are swept opportunistically.
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint("count >= 1", name="ck_rate_limits_count"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_rate_limits_window_start", "rate_limits", ["window_start"])


def downgrade() -> None:
    op.drop_index("ix_rate_limits_window_start", table_name="rate_limits")
    op.drop_table("rate_limits")
