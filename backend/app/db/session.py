from functools import lru_cache
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        pool_timeout=5,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine())


class DatabaseUnavailableError(Exception):
    pass


def get_db() -> Iterator[Session]:
    """Provide one session per request and close it even after an error."""
    try:
        factory = get_session_factory()
    except (ValueError, SQLAlchemyError):
        raise DatabaseUnavailableError() from None
    with factory() as session:
        yield session
