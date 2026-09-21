from datetime import date, time

import pytest
from alembic import command
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.models import ItineraryItem, Trip, User


@pytest.fixture
def item_values(migrated_database):
    conn, _ = migrated_database
    user_id = conn.scalar(User.__table__.insert().values(
        username="owner", email="owner@example.com", password_hash="test-placeholder",
    ).returning(User.id))
    trip_id = conn.scalar(Trip.__table__.insert().values(
        name="Trip", destination="Tokyo", owner_id=user_id,
        start_date=date(2027, 6, 10), end_date=date(2027, 6, 20),
    ).returning(Trip.id))
    return {
        "trip_id": trip_id, "created_by_user_id": user_id,
        "title": "Temple", "date": date(2027, 6, 10), "position": 1,
    }


def test_metadata():
    table = ItineraryItem.__table__
    assert table.c.id.identity is not None
    assert str(table.c.date.type) == "DATE"
    assert str(table.c.start_time.type) == "TIME"
    assert not table.c.start_time.type.timezone
    assert table.c.updated_at.type.timezone
    assert {fk.ondelete for fk in table.foreign_keys} == {"CASCADE", "RESTRICT"}
    assert "uq_itinerary_trip_date_position" in {c.name for c in table.constraints}


def test_0004_round_trip(migrated_database, item_values):
    conn, config = migrated_database
    conn.execute(ItineraryItem.__table__.insert().values(**item_values))
    command.check(config)
    columns = {c["name"]: c for c in inspect(conn).get_columns("itinerary_items")}
    assert columns["id"]["identity"]
    assert len(columns) == 12
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
    command.downgrade(config, "0003")
    assert "itinerary_items" not in inspect(conn).get_table_names()
    assert conn.scalar(select(Trip.id)) == item_values["trip_id"]
    assert conn.scalar(select(User.id)) == item_values["created_by_user_id"]
    command.upgrade(config, "head")
    command.check(config)
    assert conn.scalar(select(ItineraryItem.id)) is None
    row = conn.execute(ItineraryItem.__table__.insert().values(**item_values).returning(
        ItineraryItem.id, ItineraryItem.created_at, ItineraryItem.updated_at,
    )).one()
    assert row.id > 0 and row.created_at.tzinfo is not None and row.updated_at.tzinfo is not None


@pytest.mark.parametrize("column", [
    "id", "trip_id", "title", "date", "position", "created_by_user_id", "created_at", "updated_at",
])
def test_not_null(migrated_database, item_values, column):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(ItineraryItem.__table__.insert().values(**{**item_values, column: None}))
    assert error.value.orig.sqlstate == "23502"


@pytest.mark.parametrize("changes,constraint", [
    ({"position": 0}, "ck_itinerary_position"),
    ({"position": -1}, "ck_itinerary_position"),
    ({"title": "   "}, "ck_itinerary_title"),
    ({"end_time": time(10)}, "ck_itinerary_times"),
    ({"start_time": time(23), "end_time": time(1)}, "ck_itinerary_times"),
    ({"trip_id": 2147483647}, "fk_itinerary_trip"),
    ({"created_by_user_id": 2147483647}, "fk_itinerary_creator"),
])
def test_constraints(migrated_database, item_values, changes, constraint):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(ItineraryItem.__table__.insert().values(**{**item_values, **changes}))
    assert error.value.orig.diag.constraint_name == constraint


def test_unique_scope_and_creator_restrict(migrated_database, item_values):
    conn, _ = migrated_database
    conn.execute(ItineraryItem.__table__.insert().values(**item_values))
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(ItineraryItem.__table__.insert().values(**item_values))
    assert error.value.orig.diag.constraint_name == "uq_itinerary_trip_date_position"
    conn.execute(ItineraryItem.__table__.insert().values(
        **{**item_values, "date": date(2027, 6, 11)},
    ))
    other = conn.scalar(User.__table__.insert().values(
        username="creator", email="creator@example.com", password_hash="test-placeholder",
    ).returning(User.id))
    conn.execute(ItineraryItem.__table__.update().values(created_by_user_id=other))
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(delete(User).where(User.id == other))
    assert error.value.orig.diag.constraint_name == "fk_itinerary_creator"
