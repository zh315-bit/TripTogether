"""add entity versions for optimistic concurrency

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSIONED_TABLES = ("trips", "itinerary_items", "expenses", "trip_places")


def upgrade() -> None:
    # Starts at 1 and increases on every ORM update. Clients echo it back in
    # If-Match; a mismatch is a 412 instead of a silent last-write-wins.
    for table in VERSIONED_TABLES:
        op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    for table in reversed(VERSIONED_TABLES):
        op.drop_column(table, "version")
