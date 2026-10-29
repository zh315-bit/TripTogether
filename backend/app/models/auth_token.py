from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthToken(Base):
    """A hashed, single-use token: a refresh session rotation or a password reset."""

    __tablename__ = "auth_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_tokens_token_hash"),
        CheckConstraint("kind IN ('refresh', 'reset')", name="ck_auth_tokens_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_auth_tokens_user", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(7), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Rotations of one refresh session share a family; a reset token is its own.
    family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
