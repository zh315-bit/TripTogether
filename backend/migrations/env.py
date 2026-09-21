from alembic import context
from sqlalchemy.engine import Connection

from app.db.base import Base
from app.db.session import get_engine
from app.core.config import get_database_url
from app import models  # Register all models before reading Base.metadata.


config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests supply an isolated connection with an outer transaction.
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
        return
    engine = get_engine()
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
