from argon2.exceptions import HashingError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import User
from app.schemas.user import UserRegister


class DuplicateUserError(Exception):
    """A username or email is already registered."""

    def __init__(self, field: str):
        self.code = field.upper() + "_ALREADY_EXISTS"
        super().__init__(field.capitalize() + " already registered")

class RegistrationUnavailableError(Exception):
    """Credential-safe infrastructure failure."""


def register_user(db: Session, payload: UserRegister) -> User:
    try:
        if db.scalar(select(User.id).where(User.username == payload.username)) is not None:
            raise DuplicateUserError("username")
        if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
            raise DuplicateUserError("email")

        user = User(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password.get_secret_value()),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except DuplicateUserError:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        # Pre-checks can race; named PostgreSQL UNIQUE constraints decide the winner.
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if getattr(error.orig, "sqlstate", None) == "23505":
            if constraint == "uq_users_username":
                raise DuplicateUserError("username") from None
            if constraint == "uq_users_email":
                raise DuplicateUserError("email") from None
        raise RegistrationUnavailableError() from None
    except (SQLAlchemyError, HashingError):
        db.rollback()
        # SQL exceptions may contain bound credential values; never expose/log them.
        raise RegistrationUnavailableError() from None
