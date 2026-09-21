import secrets

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.user import UserLogin


# Unknown emails still perform an Argon2 verification instead of returning early.
_dummy_password_hash = hash_password(secrets.token_urlsafe(32))


class InvalidCredentialsError(Exception):
    pass


class AuthenticationUnavailableError(Exception):
    pass


def authenticate_user(db: Session, payload: UserLogin) -> User:
    try:
        user = db.scalar(select(User).where(User.email == payload.email))
    except SQLAlchemyError:
        db.rollback()
        raise AuthenticationUnavailableError() from None
    password_hash = user.password_hash if user is not None else _dummy_password_hash
    verified = verify_password(payload.password.get_secret_value(), password_hash)
    if user is None or not verified:
        raise InvalidCredentialsError()
    return user


def find_current_user(db: Session, user_id: int) -> User:
    try:
        user = db.get(User, user_id)
    except SQLAlchemyError:
        db.rollback()
        raise AuthenticationUnavailableError() from None
    if user is None:
        raise InvalidCredentialsError()
    return user
