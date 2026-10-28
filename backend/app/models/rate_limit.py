from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimit(Base):
    """A fixed-window counter: how many requests `key` made since `window_start`."""

    __tablename__ = "rate_limits"
    __table_args__ = (CheckConstraint("count >= 1", name="ck_rate_limits_count"),)

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
