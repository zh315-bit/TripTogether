from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Identity, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TripMember(Base):
    __tablename__ = "trip_members"
    __table_args__ = (
        UniqueConstraint("trip_id", "user_id", name="uq_trip_members_trip_user"),
        CheckConstraint("role IN ('owner', 'member')", name="ck_trip_members_role"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", name="fk_trip_members_trip", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_trip_members_user", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(6), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
