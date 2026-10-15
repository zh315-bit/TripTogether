"""add trip places and itinerary associations

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Column-specific SET NULL requires PostgreSQL 15+. Fail before any DDL.
    if not op.get_context().as_sql and op.get_bind().dialect.server_version_info < (15,):
        raise RuntimeError("Trip places require PostgreSQL 15 or newer.")
    op.create_table(
        "trip_places",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("proposed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("provider_place_id", sa.String(length=256), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_trip_places_latitude"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_trip_places_longitude"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_trip_places_name"),
        sa.CheckConstraint("length(btrim(provider)) > 0", name="ck_trip_places_provider"),
        sa.CheckConstraint("(provider = 'manual') = (provider_place_id IS NULL)",
                           name="ck_trip_places_provider_place_id"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"],
                                name="fk_trip_places_trip", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposed_by_user_id"], ["users.id"],
                                name="fk_trip_places_proposer", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "id", name="uq_trip_places_trip_id_id"),
        sa.UniqueConstraint("trip_id", "provider", "provider_place_id",
                            name="uq_trip_places_provider_place"),
    )
    op.create_index("ix_trip_places_proposed_by_user_id", "trip_places", ["proposed_by_user_id"])
    op.add_column("itinerary_items", sa.Column("place_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_itinerary_trip_place", "itinerary_items", "trip_places",
        ["trip_id", "place_id"], ["trip_id", "id"], ondelete="SET NULL (place_id)",
    )
    op.create_index("ix_itinerary_items_trip_id_place_id", "itinerary_items", ["trip_id", "place_id"])


def downgrade() -> None:
    op.drop_index("ix_itinerary_items_trip_id_place_id", table_name="itinerary_items")
    op.drop_constraint("fk_itinerary_trip_place", "itinerary_items", type_="foreignkey")
    op.drop_column("itinerary_items", "place_id")
    op.drop_index("ix_trip_places_proposed_by_user_id", table_name="trip_places")
    op.drop_table("trip_places")
