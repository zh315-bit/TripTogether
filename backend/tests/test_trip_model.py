from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, Date, DateTime, Integer

from app.db.base import Base
from app.models import Trip, User
from app.schemas.trip import TripCreate, TripUpdate


PAYLOAD = {
    "name": "Japan Trip", "destination": "Tokyo, Japan",
    "start_date": "2027-06-10", "end_date": "2027-06-20",
}


def test_trip_metadata():
    table = Trip.__table__
    assert Base.metadata.tables["trips"] is table
    assert set(table.columns.keys()) == {
        "id", "name", "destination", "start_date", "end_date",
        "owner_id", "created_at", "updated_at",
    }
    assert list(table.primary_key.columns.keys()) == ["id"]
    assert isinstance(table.c.id.type, Integer)
    assert table.c.id.identity is not None
    assert all(not column.nullable for column in table.columns)
    assert table.c.name.type.length == 120
    assert table.c.destination.type.length == 200
    for field in ("start_date", "end_date"):
        assert isinstance(table.c[field].type, Date)
    for field in ("created_at", "updated_at"):
        assert isinstance(table.c[field].type, DateTime)
        assert table.c[field].type.timezone
        assert str(table.c[field].server_default.arg) == "now()"
    assert str(table.c.updated_at.onupdate.arg) == "statement_timestamp()"
    fk = next(iter(table.c.owner_id.foreign_keys))
    assert fk.target_fullname == "users.id"
    assert fk.ondelete == "RESTRICT"
    assert {(index.name, tuple(index.columns.keys())) for index in table.indexes} == {
        ("ix_trips_owner_id", ("owner_id",)),
    }
    assert {c.name for c in table.constraints if isinstance(c, CheckConstraint)} == {
        "ck_trips_date_range", "ck_trips_name_not_blank", "ck_trips_destination_not_blank",
    }
    assert Trip.owner.property.mapper.class_ is User


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("name", " \t\n"), ("name", "x" * 121), ("name", None),
    ("destination", ""), ("destination", "x" * 201), ("destination", None),
    ("name", "null\x00text"), ("destination", "\ud800"),
    ("start_date", "2027-02-30"), ("start_date", "2027-06-10T00:00:00Z"),
    ("start_date", 1800000000), ("end_date", "2027-06-09"),
    ("owner_id", 99), ("id", 99), ("created_at", "2027-06-10"),
    ("updated_at", "2027-06-10"),
])
def test_create_schema_rejects_invalid_and_server_fields(field, value):
    with pytest.raises(ValidationError):
        TripCreate(**{**PAYLOAD, field: value})


def test_schema_normalization_same_day_and_patch_omission():
    created = TripCreate(**{
        **PAYLOAD, "name": " Japan Trip ", "destination": " Tokyo ",
        "end_date": PAYLOAD["start_date"],
    })
    assert created.name == "Japan Trip" and created.destination == "Tokyo"
    assert created.start_date == created.end_date == date(2027, 6, 10)
    assert TripUpdate().model_dump(exclude_unset=True) == {}
    assert TripUpdate(name=" New ").model_dump(exclude_unset=True) == {"name": "New"}


@pytest.mark.parametrize("field", [
    "name", "destination", "start_date", "end_date",
])
def test_patch_rejects_null(field):
    with pytest.raises(ValidationError):
        TripUpdate(**{field: None})


@pytest.mark.parametrize("field", ["owner_id", "id", "created_at", "updated_at"])
def test_patch_cannot_change_server_fields(field):
    with pytest.raises(ValidationError):
        TripUpdate(**{field: 1})
