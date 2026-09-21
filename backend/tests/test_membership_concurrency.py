import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_database_url
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import TripInvitation, TripMember, User
from app.schemas.trip import TripCreate
from app.services.trips import create_trip


@pytest.fixture
def concurrent_client(jwt_environment):
    """Only race tests need committed fixtures visible to independent connections."""
    if os.environ.get("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_TESTS=1 with real PostgreSQL.")
    schema = "test_membership_" + uuid4().hex
    admin = create_engine(get_database_url())
    engine = None
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(get_database_url(), connect_args={
            "options": f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000",
        })
        with engine.begin() as connection:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        factory = sessionmaker(engine)
        with factory() as db:
            alice = User(username="alice", email="alice@example.com", password_hash="test-placeholder")
            bob = User(username="bob", email="bob@example.com", password_hash="test-placeholder")
            db.add_all([alice, bob])
            db.commit()
            alice_id, bob_id = alice.id, bob.id
            trip = create_trip(db, TripCreate(
                name="Japan", destination="Tokyo", start_date="2027-06-10", end_date="2027-06-20",
            ), alice_id)
            trip_id = trip.id
        ah = {"Authorization": "Bearer " + create_access_token(alice_id)}
        bh = {"Authorization": "Bearer " + create_access_token(bob_id)}

        def request_session():
            with factory() as db:
                yield db

        app.dependency_overrides[get_db] = request_session
        with TestClient(app) as client:
            yield client, engine, factory, trip_id, alice_id, bob_id, ah, bh
    finally:
        app.dependency_overrides.pop(get_db, None)
        if engine is not None:
            engine.dispose()
        # This random private schema belongs solely to this test, never public.
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def simultaneous_requests(engine, operations):
    barrier = Barrier(2, timeout=10)

    def synchronize(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT trips.") and "FOR UPDATE" in statement:
            barrier.wait()

    event.listen(engine, "before_cursor_execute", synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(operation) for operation in operations]
            return [future.result(timeout=20) for future in futures]
    finally:
        event.remove(engine, "before_cursor_execute", synchronize)


def test_simultaneous_invites_create_one_pending(concurrent_client):
    client, engine, factory, trip_id, _, bob_id, ah, _ = concurrent_client

    def invite():
        return client.post(f"/trips/{trip_id}/invitations",
                           headers=ah, json={"email": "bob@example.com"})

    results = simultaneous_requests(engine, [invite, invite])
    assert sorted(r.status_code for r in results) == [201, 409]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TripInvitation).where(
            TripInvitation.trip_id == trip_id, TripInvitation.invitee_id == bob_id,
            TripInvitation.status == "pending",
        )) == 1


@pytest.mark.parametrize("actions", [("accept", "accept"), ("accept", "reject")])
def test_simultaneous_responses_commit_one_transition(concurrent_client, actions):
    client, engine, factory, trip_id, _, bob_id, ah, bh = concurrent_client
    response = client.post(f"/trips/{trip_id}/invitations",
                           headers=ah, json={"email": "bob@example.com"})
    assert response.status_code == 201
    invitation_id = response.json()["id"]
    operations = [
        lambda action=action: client.post(f"/invitations/{invitation_id}/{action}", headers=bh)
        for action in actions
    ]
    results = simultaneous_requests(engine, operations)
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r for r in results if r.status_code == 200).json()
    with factory() as db:
        invitation = db.get(TripInvitation, invitation_id)
        assert invitation.status == winner["status"]
        assert invitation.responded_at is not None
        count = db.scalar(select(func.count()).select_from(TripMember).where(
            TripMember.trip_id == trip_id, TripMember.user_id == bob_id,
        ))
        assert count == (1 if invitation.status == "accepted" else 0)
