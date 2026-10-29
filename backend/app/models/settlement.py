from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Identity, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Settlement(Base):
    """A payment one member made to another, recorded against the trip's balances."""

    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint("amount > 0 AND amount <= 9999999999.99", name="ck_settlements_amount"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_settlements_currency"),
        CheckConstraint("from_user_id <> to_user_id", name="ck_settlements_distinct_parties"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", name="fk_settlements_trip", ondelete="CASCADE"), nullable=False, index=True)
    from_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_settlements_from", ondelete="RESTRICT"), nullable=False)
    to_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_settlements_to", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    recorded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_settlements_recorder", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
