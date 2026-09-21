from datetime import date, datetime, timezone

import pytest
from alembic import command
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models import Trip, TripInvitation, TripMember, User


def test_membership_metadata():
    members = TripMember.__table__
    invites = TripInvitation.__table__
    assert set(members.c.keys()) == {"id", "trip_id", "user_id", "role", "joined_at"}
    assert all(not c.nullable for c in members.c)
    assert set(invites.c.keys()) == {
        "id", "trip_id", "inviter_id", "invitee_id", "status", "created_at", "responded_at",
    }
    assert {c.name for c in invites.c if c.nullable} == {"responded_at"}
    for table in (members, invites):
        assert table.c.id.identity is not None
        assert next(iter(table.c.trip_id.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(members.c.user_id.foreign_keys)).ondelete == "RESTRICT"
    assert next(iter(invites.c.inviter_id.foreign_keys)).ondelete == "RESTRICT"
    assert next(iter(invites.c.invitee_id.foreign_keys)).ondelete == "RESTRICT"
    assert members.c.joined_at.type.timezone
    assert invites.c.created_at.type.timezone and invites.c.responded_at.type.timezone
    pending = next(i for i in invites.indexes if i.name == "uq_trip_invitations_pending")
    assert pending.unique
    assert str(pending.dialect_options["postgresql"]["where"]) == "status = 'pending'"


@pytest.fixture
def rows(migrated_database):
    conn, _ = migrated_database
    ids = []
    for name in ("alice", "bob"):
        ids.append(conn.scalar(User.__table__.insert().values(
            username=name, email=name + "@example.com", password_hash="test-placeholder",
        ).returning(User.id)))
    trip = conn.scalar(Trip.__table__.insert().values(
        name="Japan", destination="Tokyo", owner_id=ids[0],
        start_date=date(2027, 6, 10), end_date=date(2027, 6, 20),
    ).returning(Trip.id))
    return conn, ids, trip


def test_upgrade_backfills_old_owners_and_reverses(migrated_database):
    conn, config = migrated_database
    command.downgrade(config, "0002")
    assert not {"trip_members", "trip_invitations"} & set(inspect(conn).get_table_names())
    user_id = conn.scalar(User.__table__.insert().values(
        username="old_owner", email="old_owner@example.com", password_hash="test-placeholder",
    ).returning(User.id))
    trip_ids = []
    for name in ("First old trip", "Second old trip"):
        trip_ids.append(conn.scalar(Trip.__table__.insert().values(
            name=name, destination="Tokyo", owner_id=user_id,
            start_date=date(2027, 6, 10), end_date=date(2027, 6, 20),
        ).returning(Trip.id)))
    for _ in range(2):
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        members = conn.execute(select(TripMember.__table__).order_by(TripMember.trip_id)).mappings().all()
        assert [(m["trip_id"], m["user_id"], m["role"]) for m in members] == [
            (trip_id, user_id, "owner") for trip_id in trip_ids
        ]
        for member in members:
            assert member["joined_at"] == conn.scalar(select(Trip.created_at).where(Trip.id == member["trip_id"]))
        command.check(config)
        command.downgrade(config, "0002")
        assert set(inspect(conn).get_table_names()) == {"users", "trips", "alembic_version"}
        assert conn.scalar(select(User.id)) == user_id
        assert list(conn.scalars(select(Trip.id).order_by(Trip.id))) == trip_ids
    command.upgrade(config, "head")


def test_unique_membership_and_pending_history(rows):
    conn, (alice, bob), trip = rows
    conn.execute(TripMember.__table__.insert().values(trip_id=trip, user_id=alice, role="owner"))
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(TripMember.__table__.insert().values(trip_id=trip, user_id=alice, role="member"))
    assert error.value.orig.diag.constraint_name == "uq_trip_members_trip_user"
    values = {"trip_id": trip, "inviter_id": alice, "invitee_id": bob}
    first = conn.scalar(TripInvitation.__table__.insert().values(**values).returning(TripInvitation.id))
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(TripInvitation.__table__.insert().values(**values))
    assert error.value.orig.diag.constraint_name == "uq_trip_invitations_pending"
    conn.execute(TripInvitation.__table__.update().where(TripInvitation.id == first).values(
        status="rejected", responded_at=datetime.now(timezone.utc),
    ))
    conn.execute(TripInvitation.__table__.insert().values(**values))


@pytest.mark.parametrize("model,field,value,sqlstate", [
    (TripMember, "trip_id", 2147483647, "23503"),
    (TripMember, "user_id", 2147483647, "23503"),
    (TripMember, "role", "admin", "23514"),
    (TripMember, "role", None, "23502"),
    (TripMember, "joined_at", None, "23502"),
    (TripMember, "trip_id", None, "23502"),
    (TripMember, "user_id", None, "23502"),
    (TripInvitation, "trip_id", 2147483647, "23503"),
    (TripInvitation, "inviter_id", 2147483647, "23503"),
    (TripInvitation, "invitee_id", 2147483647, "23503"),
    (TripInvitation, "status", "expired", "23514"),
    (TripInvitation, "status", "accepted", "23514"),
    (TripInvitation, "responded_at", datetime.now(timezone.utc), "23514"),
    (TripInvitation, "trip_id", None, "23502"),
    (TripInvitation, "inviter_id", None, "23502"),
    (TripInvitation, "invitee_id", None, "23502"),
    (TripInvitation, "status", None, "23502"),
    (TripInvitation, "created_at", None, "23502"),
])
def test_database_constraints(rows, model, field, value, sqlstate):
    conn, (alice, bob), trip = rows
    values = ({"trip_id": trip, "user_id": bob, "role": "member"} if model is TripMember
              else {"trip_id": trip, "inviter_id": alice, "invitee_id": bob})
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(model.__table__.insert().values(**{**values, field: value}))
    assert error.value.orig.sqlstate == sqlstate


def test_no_self_invite_and_user_delete_restricted(rows):
    conn, (alice, bob), trip = rows
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(TripInvitation.__table__.insert().values(
                trip_id=trip, inviter_id=alice, invitee_id=alice,
            ))
    assert error.value.orig.diag.constraint_name == "ck_trip_invitations_not_self"
    conn.execute(TripMember.__table__.insert().values(trip_id=trip, user_id=bob, role="member"))
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(User.__table__.delete().where(User.id == bob))
