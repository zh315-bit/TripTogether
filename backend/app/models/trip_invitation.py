from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TripInvitation(Base):
    __tablename__ = "trip_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_trip_invitations_status",
        ),
        CheckConstraint("inviter_id <> invitee_id", name="ck_trip_invitations_not_self"),
        CheckConstraint(
            "(status = 'pending' AND responded_at IS NULL) OR "
            "(status IN ('accepted', 'rejected') AND responded_at IS NOT NULL)",
            name="ck_trip_invitations_response",
        ),
        Index(
            "uq_trip_invitations_pending", "trip_id", "invitee_id",
            unique=True, postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", name="fk_trip_invitations_trip", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    inviter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_trip_invitations_inviter", ondelete="RESTRICT"),
        nullable=False,
    )
    invitee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_trip_invitations_invitee", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
