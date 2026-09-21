import os
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 with a real PostgreSQL DATABASE_URL.",
)


def test_migration_round_trip_and_metadata(migrated_database) -> None:
    connection, config = migrated_database
    assert set(inspect(connection).get_table_names()) == {
        "users", "trips", "trip_members", "trip_invitations", "itinerary_items",
        "expenses", "expense_splits", "alembic_version",
    }
    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
    command.check(config)
    command.downgrade(config, "base")
    assert "users" not in inspect(connection).get_table_names()
    assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0
    command.upgrade(config, "head")
    assert "users" in inspect(connection).get_table_names()
    command.check(config)


def test_database_defaults_and_orm_round_trip(migrated_database) -> None:
    connection, _ = migrated_database
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        first = User(
            username="first", email="first@example.test",
            password_hash="test-hash-placeholder-not-a-password",
        )
        second = User(
            username="second", email="second@example.test",
            password_hash="test-hash-placeholder-not-a-password",
        )
        session.add_all([first, second])
        session.flush()
        assert first.id > 0
        assert second.id > first.id
        assert first.created_at.utcoffset() == timedelta(0)
        first_id = first.id
        session.expunge_all()
        loaded = session.get(User, first_id)
        assert loaded is not None
        assert loaded.username == "first"


@pytest.mark.parametrize("column", ["username", "email"])
def test_database_rejects_duplicate_values(migrated_database, column: str) -> None:
    connection, _ = migrated_database
    connection.execute(User.__table__.insert().values(
        username="first", email="first@example.test",
        password_hash="test-hash-placeholder-not-a-password",
    ))
    values = {
        "username": "second", "email": "second@example.test",
        "password_hash": "test-hash-placeholder-not-a-password",
    }
    values[column] = "first" if column == "username" else "first@example.test"
    with pytest.raises(IntegrityError) as error:
        with connection.begin_nested():
            connection.execute(User.__table__.insert().values(**values))
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == f"uq_users_{column}"


@pytest.mark.parametrize(
    "column", ["id", "username", "email", "password_hash", "created_at"]
)
def test_database_rejects_null(migrated_database, column: str) -> None:
    connection, _ = migrated_database
    values = {
        "username": "first", "email": "first@example.test",
        "password_hash": "test-hash-placeholder-not-a-password",
        column: None,
    }
    with pytest.raises(IntegrityError) as error:
        with connection.begin_nested():
            connection.execute(User.__table__.insert().values(**values))
    assert error.value.orig.sqlstate == "23502"
    assert error.value.orig.diag.column_name == column
