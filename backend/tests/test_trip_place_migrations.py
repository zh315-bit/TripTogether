from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.check import check_schema
from app.models import ItineraryItem, Trip, TripPlace, User


@pytest.fixture
def place_values(migrated_database):
    conn, _ = migrated_database
    user_id = conn.scalar(User.__table__.insert().values(
        username="owner", email="owner@example.com", password_hash="test-placeholder",
    ).returning(User.id))
    trip_id = conn.scalar(Trip.__table__.insert().values(
        name="Trip", destination="Tokyo", owner_id=user_id,
        start_date=date(2027, 6, 10), end_date=date(2027, 6, 20),
    ).returning(Trip.id))
    return {
        "trip_id": trip_id, "proposed_by_user_id": user_id, "name": "Temple",
        "latitude": Decimal("35.714800"), "longitude": Decimal("139.796700"),
    }


def item_values(conn, trip_id, **changes):
    return {
        "trip_id": trip_id, "title": "Visit temple", "location": "Original location",
        "date": date(2027, 6, 10), "position": 1,
        "created_by_user_id": conn.scalar(select(Trip.owner_id).where(Trip.id == trip_id)),
        **changes,
    }


def other_trip(conn):
    return conn.scalar(Trip.__table__.insert().values(
        name="Other trip", destination="Kyoto", owner_id=conn.scalar(select(User.id)),
        start_date=date(2027, 6, 10), end_date=date(2027, 6, 20),
    ).returning(Trip.id))


def test_place_metadata():
    table = TripPlace.__table__
    assert set(table.c.keys()) == {
        "id", "trip_id", "proposed_by_user_id", "name", "address", "latitude", "longitude",
        "provider", "provider_place_id", "note", "version", "created_at", "updated_at",
    }
    assert table.c.id.identity is not None
    assert {c.name for c in table.c if c.nullable} == {"address", "provider_place_id", "note"}
    assert table.c.name.type.length == 200
    assert table.c.address.type.length == 500
    assert table.c.provider.type.length == 32
    assert table.c.provider_place_id.type.length == 256
    assert table.c.note.type.length == 500
    for name in ("latitude", "longitude"):
        assert table.c[name].type.precision == 9 and table.c[name].type.scale == 6
    assert str(table.c.provider.server_default.arg) == "manual"
    assert str(table.c.updated_at.onupdate.arg) == "statement_timestamp()"
    fk = next(iter(table.c.trip_id.foreign_keys))
    assert fk.target_fullname == "trips.id" and fk.ondelete == "CASCADE"
    proposer = next(iter(table.c.proposed_by_user_id.foreign_keys))
    assert proposer.target_fullname == "users.id" and proposer.ondelete == "RESTRICT"
    assert table.c.proposed_by_user_id.index
    assert ItineraryItem.__table__.c.place_id.nullable


def test_create_defaults_and_orm_update(migrated_database, place_values):
    conn, _ = migrated_database
    with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
        place = TripPlace(**place_values)
        db.add(place)
        db.commit()
        db.refresh(place)
        assert place.id > 0 and place.provider == "manual"
        assert place.address is None and place.provider_place_id is None and place.note is None
        assert place.latitude == place_values["latitude"]
        assert place.longitude == place_values["longitude"]
        assert isinstance(place.latitude, Decimal)
        assert place.created_at.tzinfo is not None and place.updated_at.tzinfo is not None
        before, created = place.updated_at, place.created_at
        place.name = "Renamed temple"
        db.commit()
        db.refresh(place)
        assert place.updated_at > before and place.created_at == created


@pytest.mark.parametrize("column", [
    "id", "trip_id", "proposed_by_user_id", "name", "latitude", "longitude", "provider",
    "created_at", "updated_at",
])
def test_place_not_null(migrated_database, place_values, column):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(TripPlace.__table__.insert().values(**{**place_values, column: None}))
    assert error.value.orig.sqlstate == "23502"
    assert error.value.orig.diag.column_name == column


@pytest.mark.parametrize("field,value", [
    ("latitude", "-90.000001"), ("latitude", "90.000001"),
    ("longitude", "-180.000001"), ("longitude", "180.000001"),
    ("latitude", "NaN"), ("longitude", "NaN"),
])
def test_invalid_coordinates(migrated_database, place_values, field, value):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(TripPlace.__table__.insert().values(**{**place_values, field: Decimal(value)}))
    assert error.value.orig.diag.constraint_name == f"ck_trip_places_{field}"


@pytest.mark.parametrize("latitude,longitude", [("-90", "-180"), ("90", "180"), ("0", "0")])
def test_coordinate_boundaries(migrated_database, place_values, latitude, longitude):
    conn, _ = migrated_database
    conn.execute(TripPlace.__table__.insert().values(**{
        **place_values, "latitude": Decimal(latitude), "longitude": Decimal(longitude),
    }))


@pytest.mark.parametrize("changes,constraint", [
    ({"trip_id": 2147483647}, "fk_trip_places_trip"),
    ({"name": " "}, "ck_trip_places_name"),
    ({"proposed_by_user_id": 2147483647}, "fk_trip_places_proposer"),
    ({"provider": " "}, "ck_trip_places_provider"),
    ({"provider_place_id": "node:1"}, "ck_trip_places_provider_place_id"),
    ({"provider": "nominatim"}, "ck_trip_places_provider_place_id"),
])
def test_place_constraints(migrated_database, place_values, changes, constraint):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(TripPlace.__table__.insert().values(**{**place_values, **changes}))
    assert error.value.orig.diag.constraint_name == constraint


def test_provider_unique_scope_and_manual_nulls(migrated_database, place_values):
    conn, _ = migrated_database
    imported = {**place_values, "provider": "nominatim", "provider_place_id": "node:123"}
    conn.execute(TripPlace.__table__.insert().values(**imported))
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(TripPlace.__table__.insert().values(**imported))
    assert error.value.orig.diag.constraint_name == "uq_trip_places_provider_place"
    conn.execute(TripPlace.__table__.insert().values(**{**imported, "trip_id": other_trip(conn)}))
    conn.execute(TripPlace.__table__.insert().values(**{**imported, "provider": "other"}))
    for _ in range(2):
        conn.execute(TripPlace.__table__.insert().values(**place_values))


def test_proposer_delete_restricted(migrated_database, place_values):
    conn, _ = migrated_database
    # A proposer who owns nothing else isolates the place reference.
    proposer = conn.scalar(User.__table__.insert().values(
        username="proposer", email="proposer@example.com", password_hash="test-placeholder",
    ).returning(User.id))
    conn.execute(TripPlace.__table__.insert().values(**{**place_values, "proposed_by_user_id": proposer}))
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(delete(User).where(User.id == proposer))
    assert error.value.orig.diag.constraint_name == "fk_trip_places_proposer"


def test_same_trip_link_and_old_items(migrated_database, place_values):
    conn, _ = migrated_database
    place_id = conn.scalar(TripPlace.__table__.insert().values(**place_values).returning(TripPlace.id))
    for position, linked in ((1, place_id), (2, None), (3, place_id)):
        conn.execute(ItineraryItem.__table__.insert().values(**item_values(
            conn, place_values["trip_id"], place_id=linked, position=position,
        )))
    assert list(conn.scalars(select(ItineraryItem.place_id).order_by(ItineraryItem.position))) == [
        place_id, None, place_id,
    ]


def test_missing_place_rejected(migrated_database, place_values):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(ItineraryItem.__table__.insert().values(**item_values(
                conn, place_values["trip_id"], place_id=2147483647,
            )))
    assert error.value.orig.diag.constraint_name == "fk_itinerary_trip_place"


@pytest.mark.parametrize("operation", ["insert", "change_place", "change_item_trip", "change_place_trip"])
def test_cross_trip_rejected(migrated_database, place_values, operation):
    conn, _ = migrated_database
    trip_id = place_values["trip_id"]
    second_trip = other_trip(conn)
    place_id = conn.scalar(TripPlace.__table__.insert().values(**place_values).returning(TripPlace.id))
    other_place = conn.scalar(TripPlace.__table__.insert().values(
        **{**place_values, "trip_id": second_trip},
    ).returning(TripPlace.id))
    conn.execute(ItineraryItem.__table__.insert().values(**item_values(conn, trip_id, place_id=place_id)))
    statements = {
        "insert": ItineraryItem.__table__.insert().values(**item_values(
            conn, second_trip, place_id=place_id,
        )),
        "change_place": ItineraryItem.__table__.update().values(place_id=other_place),
        "change_item_trip": ItineraryItem.__table__.update().values(trip_id=second_trip),
        "change_place_trip": TripPlace.__table__.update().where(TripPlace.id == place_id).values(
            trip_id=second_trip,
        ),
    }
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(statements[operation])
    assert error.value.orig.sqlstate == "23503"
    assert error.value.orig.diag.constraint_name == "fk_itinerary_trip_place"


@pytest.mark.parametrize("orm", [False, True])
def test_delete_place_preserves_items_and_location(migrated_database, place_values, orm):
    conn, _ = migrated_database
    place_id = conn.scalar(TripPlace.__table__.insert().values(**place_values).returning(TripPlace.id))
    for position in (1, 2):
        conn.execute(ItineraryItem.__table__.insert().values(**item_values(
            conn, place_values["trip_id"], place_id=place_id, position=position,
        )))
    before = conn.execute(select(ItineraryItem.__table__).order_by(ItineraryItem.id)).mappings().all()
    if orm:
        with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
            db.delete(db.get(TripPlace, place_id))
            db.commit()
    else:
        conn.execute(delete(TripPlace).where(TripPlace.id == place_id))
    after = conn.execute(select(ItineraryItem.__table__).order_by(ItineraryItem.id)).mappings().all()
    assert after == [{**row, "place_id": None} for row in before]
    assert conn.scalar(select(Trip.id)) == place_values["trip_id"]


@pytest.mark.parametrize("orm", [False, True])
def test_delete_trip_cascades_only_its_data(migrated_database, place_values, orm):
    conn, _ = migrated_database
    second_trip = other_trip(conn)
    for trip_id in (place_values["trip_id"], second_trip):
        place_id = conn.scalar(TripPlace.__table__.insert().values(
            **{**place_values, "trip_id": trip_id},
        ).returning(TripPlace.id))
        conn.execute(ItineraryItem.__table__.insert().values(**item_values(conn, trip_id, place_id=place_id)))
    if orm:
        with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
            db.delete(db.get(Trip, place_values["trip_id"]))
            db.commit()
    else:
        conn.execute(delete(Trip).where(Trip.id == place_values["trip_id"]))
    assert list(conn.scalars(select(TripPlace.trip_id))) == [second_trip]
    assert list(conn.scalars(select(ItineraryItem.trip_id))) == [second_trip]
    assert conn.scalar(select(User.id)) is not None


def test_0006_round_trip_preserves_legacy_data(migrated_database, place_values):
    conn, config = migrated_database
    command.downgrade(config, "0005")
    # Use SQL for the production schema: ORM metadata already includes place_id.
    conn.execute(text(
        "INSERT INTO itinerary_items (trip_id, title, location, date, position, created_by_user_id) "
        "VALUES (:trip_id, :title, :location, :date, :position, :created_by_user_id)"
    ), item_values(conn, place_values["trip_id"]))
    old_item = dict(conn.execute(text("SELECT * FROM itinerary_items")).mappings().one())
    old_trip = conn.execute(text("SELECT * FROM trips")).one()
    old_user = conn.execute(select(User.__table__)).one()
    command.upgrade(config, "head")
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0010"
    assert dict(conn.execute(text("SELECT * FROM itinerary_items")).mappings().one()) == {
        **old_item, "place_id": None, "version": 1,
    }
    command.check(config)
    with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
        check_schema(db)
    fk = next(fk for fk in inspect(conn).get_foreign_keys("itinerary_items")
              if fk["name"] == "fk_itinerary_trip_place")
    assert fk["constrained_columns"] == ["trip_id", "place_id"]
    assert fk["referred_columns"] == ["trip_id", "id"]
    assert fk["options"]["ondelete"] == "SET NULL (place_id)"
    assert {index["name"] for index in inspect(conn).get_indexes("itinerary_items")} == {
        "ix_itinerary_items_created_by_user_id", "ix_itinerary_items_trip_id_place_id",
        "uq_itinerary_trip_date_position",
    }
    assert "ix_trip_places_proposed_by_user_id" in {
        index["name"] for index in inspect(conn).get_indexes("trip_places")
    }
    place_id = conn.scalar(TripPlace.__table__.insert().values(**place_values).returning(TripPlace.id))
    # Link with SQL so ORM onupdate does not change the legacy timestamp.
    conn.execute(text("UPDATE itinerary_items SET place_id = :place_id"), {"place_id": place_id})
    command.downgrade(config, "0005")
    assert "trip_places" not in inspect(conn).get_table_names()
    assert "place_id" not in {c["name"] for c in inspect(conn).get_columns("itinerary_items")}
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
    assert dict(conn.execute(text("SELECT * FROM itinerary_items")).mappings().one()) == old_item
    assert conn.execute(text("SELECT * FROM trips")).one() == old_trip
    assert conn.execute(select(User.__table__)).one() == old_user
    command.upgrade(config, "head")
    command.check(config)
