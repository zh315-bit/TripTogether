"""Refresh sessions and password resets, both backed by single-use hashed tokens.

A refresh token is opaque and random; only its SHA-256 is stored. Using one
issues a new pair and marks the old one used (rotation). Presenting a used
token again is the signature of a stolen copy, so the whole family is revoked.
A reset token works the same way with a short life, and a successful reset
logs the account out everywhere by revoking its refresh families.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import _get_setting
from app.core.security import hash_password
from app.models import AuthToken, User


RESET_TOKEN_LIFETIME = timedelta(hours=1)


class InvalidRefreshTokenError(Exception):
    pass


class InvalidResetTokenError(Exception):
    pass


class SessionsUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class RefreshResult:
    user: User
    refresh_token: str


def refresh_lifetime() -> timedelta:
    try:
        days = int(_get_setting("REFRESH_TOKEN_EXPIRE_DAYS", "30") or "30")
    except ValueError:
        raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be an integer.") from None
    if not 1 <= days <= 365:
        raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be between 1 and 365.")
    return timedelta(days=days)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _purge_expired(db: Session) -> None:
    # Opportunistic sweep: expired rows cannot be used, so nothing waits on this.
    db.execute(delete(AuthToken).where(AuthToken.expires_at < _now() - timedelta(days=1)))


def _store(db: Session, user_id: int, kind: str, family: str, lifetime: timedelta) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user_id, kind=kind, family=family, token_hash=token_hash(raw),
                     expires_at=_now() + lifetime))
    return raw


def issue_refresh_token(db: Session, user_id: int) -> str:
    """Start a new refresh family for a fresh sign-in; the caller commits."""
    try:
        _purge_expired(db)
        return _store(db, user_id, "refresh", secrets.token_hex(16), refresh_lifetime())
    except SQLAlchemyError:
        db.rollback()
        raise SessionsUnavailableError() from None


def _find(db: Session, raw: str, kind: str) -> Optional[AuthToken]:
    if not raw or len(raw) > 200:
        return None
    return db.scalar(select(AuthToken).where(
        AuthToken.token_hash == token_hash(raw), AuthToken.kind == kind).with_for_update())


def rotate_refresh_token(db: Session, raw: str) -> RefreshResult:
    """Exchange a live refresh token for a new one; a replayed token revokes its family."""
    try:
        token = _find(db, raw, "refresh")
        if token is None or token.expires_at < _now():
            db.rollback()
            raise InvalidRefreshTokenError()
        if token.used_at is not None:
            # Reuse means two parties hold this token: end the session for both.
            db.execute(delete(AuthToken).where(AuthToken.family == token.family))
            db.commit()
            raise InvalidRefreshTokenError()
        user = db.get(User, token.user_id)
        if user is None:
            db.rollback()
            raise InvalidRefreshTokenError()
        token.used_at = _now()
        replacement = _store(db, user.id, "refresh", token.family, refresh_lifetime())
        db.commit()
        return RefreshResult(user=user, refresh_token=replacement)
    except SQLAlchemyError:
        db.rollback()
        raise SessionsUnavailableError() from None


def revoke_refresh_token(db: Session, raw: str) -> None:
    """Sign out: the token's whole family stops working. Unknown tokens are ignored."""
    try:
        token = _find(db, raw, "refresh")
        if token is not None:
            db.execute(delete(AuthToken).where(AuthToken.family == token.family))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise SessionsUnavailableError() from None


def revoke_all_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(AuthToken).where(AuthToken.user_id == user_id, AuthToken.kind == "refresh"))


def create_reset_token(db: Session, user: User) -> str:
    """One live reset token per account; a new request replaces the previous one."""
    try:
        db.execute(delete(AuthToken).where(AuthToken.user_id == user.id, AuthToken.kind == "reset"))
        raw = _store(db, user.id, "reset", secrets.token_hex(16), RESET_TOKEN_LIFETIME)
        db.commit()
        return raw
    except SQLAlchemyError:
        db.rollback()
        raise SessionsUnavailableError() from None


def reset_password(db: Session, raw: str, new_password: str) -> User:
    """Set a new password from a live reset token and sign the account out everywhere."""
    try:
        token = _find(db, raw, "reset")
        if token is None or token.used_at is not None or token.expires_at < _now():
            db.rollback()
            raise InvalidResetTokenError()
        user = db.get(User, token.user_id)
        if user is None:
            db.rollback()
            raise InvalidResetTokenError()
        user.password_hash = hash_password(new_password)
        token.used_at = _now()
        revoke_all_sessions(db, user.id)
        db.commit()
        return user
    except SQLAlchemyError:
        db.rollback()
        raise SessionsUnavailableError() from None
