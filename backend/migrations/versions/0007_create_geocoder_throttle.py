"""create geocoder throttle

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One row shared by every worker and instance: the public Nominatim limit
    # is per application, not per process or per user.
    op.create_table(
        "geocoder_throttle",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_geocoder_throttle_single_row"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO geocoder_throttle (id, next_allowed_at) VALUES (1, '-infinity')")


def downgrade() -> None:
    op.drop_table("geocoder_throttle")
