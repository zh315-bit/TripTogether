import os
from datetime import date, timedelta

import pytest
from alembic import command
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Trip, User


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 with a real PostgreSQL DATABASE_URL.",
)


@pytest.fixture
def owner_id(migrated_database):
    connection, _ = migrated_database
    return connection.scalar(User.__table__.insert().values(
        username="owner", email="owner@example.com", password_hash="test-placeholder",
    ).returning(User.id))


def trip_values(owner_id):
    return {
        "name": "Japan", "destination": "Tokyo",
        "start_date": date(2027, 6, 10), "end_date": date(2027, 6, 20),
        "owner_id": owner_id,
    }


def test_0002_round_trip_preserves_users(migrated_database, owner_id):
    connection, config = migrated_database
    assert set(inspect(connection).get_table_names()) == {
        "users", "trips", "trip_members", "trip_invitations", "itinerary_items",
        "expenses", "expense_splits", "alembic_version",
    }
    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
    foreign_keys = inspect(connection).get_foreign_keys("trips")
    assert foreign_keys[0]["referred_table"] == "users"
    assert foreign_keys[0]["constrained_columns"] == ["owner_id"]
    assert foreign_keys[0]["options"]["ondelete"] == "RESTRICT"
    command.check(config)
    command.downgrade(config, "0001")
    assert set(inspect(connection).get_table_names()) == {"users", "alembic_version"}
    assert connection.scalar(select(User.id)) == owner_id
    command.upgrade(config, "head")
    assert "trips" in inspect(connection).get_table_names()
    assert connection.scalar(select(User.id)) == owner_id
    command.check(config)


def test_defaults_relationship_and_orm_updated_at(migrated_database, owner_id):
    connection, _ = migrated_database
    with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
        trip = Trip(**trip_values(owner_id))
        db.add(trip)
        db.commit()
        db.refresh(trip)
        assert trip.id > 0 and trip.owner.id == owner_id
        assert trip.created_at.utcoffset() == timedelta(0)
        assert trip.updated_at.utcoffset() == timedelta(0)
        created = trip.created_at
        before = trip.updated_at
        trip.name = "Changed"
        db.commit()
        db.refresh(trip)
        assert trip.updated_at > before
        assert trip.created_at == created


@pytest.mark.parametrize("column", [
    "id", "name", "destination", "start_date", "end_date",
    "owner_id", "created_at", "updated_at",
])
def test_trip_not_null(migrated_database, owner_id, column):
    connection, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with connection.begin_nested():
            connection.execute(Trip.__table__.insert().values(
                **{**trip_values(owner_id), column: None}
            ))
    assert error.value.orig.sqlstate == "23502"
    assert error.value.orig.diag.column_name == column


@pytest.mark.parametrize("field,value,constraint", [
    ("owner_id", 2147483647, "fk_trips_owner_id_users"),
    ("end_date", date(2027, 6, 9), "ck_trips_date_range"),
    ("name", "   ", "ck_trips_name_not_blank"),
    ("destination", "", "ck_trips_destination_not_blank"),
])
def test_trip_constraints(migrated_database, owner_id, field, value, constraint):
    connection, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with connection.begin_nested():
            connection.execute(Trip.__table__.insert().values(
                **{**trip_values(owner_id), field: value}
            ))
    assert error.value.orig.diag.constraint_name == constraint


def test_owner_delete_is_restricted(migrated_database, owner_id):
    connection, _ = migrated_database
    connection.execute(Trip.__table__.insert().values(**trip_values(owner_id)))
    with pytest.raises(IntegrityError) as error:
        with connection.begin_nested():
            connection.execute(delete(User).where(User.id == owner_id))
    assert error.value.orig.sqlstate == "23503"
