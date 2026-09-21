from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Identity, Integer, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_trips_date_range"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_trips_name_not_blank"),
        CheckConstraint(
            "length(btrim(destination)) > 0", name="ck_trips_destination_not_blank"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_trips_owner_id_users", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )
    owner: Mapped[User] = relationship()
