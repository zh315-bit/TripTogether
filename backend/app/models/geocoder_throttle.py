from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GeocoderThrottle(Base):
    """Single-row, application-wide slot for outbound geocoding requests."""

    __tablename__ = "geocoder_throttle"
    __table_args__ = (CheckConstraint("id = 1", name="ck_geocoder_throttle_single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
