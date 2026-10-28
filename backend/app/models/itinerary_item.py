from datetime import date as CalendarDay, datetime, time
from typing import Optional

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Index, Integer, String,
    Time, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["trip_id", "place_id"], ["trip_places.trip_id", "trip_places.id"],
            name="fk_itinerary_trip_place", ondelete="SET NULL (place_id)",
        ),
        Index("ix_itinerary_items_trip_id_place_id", "trip_id", "place_id"),
        UniqueConstraint("trip_id", "date", "position", name="uq_itinerary_trip_date_position"),
        CheckConstraint("position > 0", name="ck_itinerary_position"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_itinerary_title"),
        CheckConstraint(
            "end_time IS NULL OR (start_time IS NOT NULL AND end_time >= start_time)",
            name="ck_itinerary_times",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", name="fk_itinerary_trip", ondelete="CASCADE"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(200))
    place_id: Mapped[Optional[int]] = mapped_column(Integer)
    date: Mapped[CalendarDay] = mapped_column(Date, nullable=False)
    start_time: Mapped[Optional[time]] = mapped_column(Time(timezone=False))
    end_time: Mapped[Optional[time]] = mapped_column(Time(timezone=False))
    notes: Mapped[Optional[str]] = mapped_column(String(2000))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_itinerary_creator", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )
    # Optimistic concurrency: bumped by every ORM update; echoed by clients in If-Match.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __mapper_args__ = {"version_id_col": version}
