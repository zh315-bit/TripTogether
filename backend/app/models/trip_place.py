from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Identity, Integer, Numeric, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TripPlace(Base):
    __tablename__ = "trip_places"
    __table_args__ = (
        UniqueConstraint("trip_id", "id", name="uq_trip_places_trip_id_id"),
        UniqueConstraint(
            "trip_id", "provider", "provider_place_id", name="uq_trip_places_provider_place",
        ),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_trip_places_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_trip_places_longitude"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_trip_places_name"),
        CheckConstraint("length(btrim(provider)) > 0", name="ck_trip_places_provider"),
        # Manual places have no external identity; imported places always do.
        CheckConstraint(
            "(provider = 'manual') = (provider_place_id IS NULL)",
            name="ck_trip_places_provider_place_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", name="fk_trip_places_trip", ondelete="CASCADE"), nullable=False,
    )
    proposed_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_trip_places_proposer", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(500))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, server_default="manual")
    provider_place_id: Mapped[Optional[str]] = mapped_column(String(256))
    note: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )
