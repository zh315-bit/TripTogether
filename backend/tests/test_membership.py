from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import Trip, TripInvitation, TripMember, User
from app.schemas.membership import InvitationCreate
from app.schemas.user import UserLogin


TRIP = {
    "name": "Japan", "destination": "Tokyo",
    "start_date": "2027-06-10", "end_date": "2027-06-20",
}
NEW_ROUTES = [
    ("POST", "/trips/1/invitations"), ("GET", "/invitations"),
    ("POST", "/invitations/1/accept"), ("POST", "/invitations/1/reject"),
    ("GET", "/trips/1/members"),
]


@pytest.fixture
def collaboration(registration_client, jwt_environment):
    client, connection, sessions = registration_client
    users = {}
    for name in ("alice", "bob", "charlie"):
        credentials = {"email": name + "@example.com", "password": "fake-collaboration-password"}
        response = client.post("/auth/register", json={"username": name, **credentials})
        assert response.status_code == 201
        login = client.post("/auth/login", json=credentials)
        assert login.status_code == 200
        users[name] = (response.json(), {"Authorization": "Bearer " + login.json()["access_token"]})
    response = client.post("/trips", json=TRIP, headers=users["alice"][1])
    assert response.status_code == 201
    return client, connection, sessions, users, response.json()


def invite(context, name="bob"):
    client, _, _, users, trip = context
    response = client.post(f"/trips/{trip['id']}/invitations",
                           headers=users["alice"][1], json={"email": f" {name.upper()}@Example.COM "})
    assert response.status_code == 201
    return response.json()


def test_owner_membership_and_complete_collaboration(collaboration):
    client, conn, _, users, trip = collaboration
    alice, ah = users["alice"]
    bob, bh = users["bob"]
    _, ch = users["charlie"]
    path = f"/trips/{trip['id']}"
    owner = conn.execute(select(TripMember.__table__)).mappings().one()
    assert owner["trip_id"] == trip["id"] and owner["user_id"] == alice["id"]
    assert owner["role"] == "owner"
    assert client.get("/trips", headers=ah).json() == [trip]
    invitation = invite(collaboration)
    assert invitation["status"] == "pending" and invitation["responded_at"] is None
    assert invitation["inviter_id"] == alice["id"] and invitation["invitee_id"] == bob["id"]
    assert client.get("/invitations", headers=bh).json() == [invitation]
    assert client.get("/invitations", headers=ah).json() == []
    assert client.get("/invitations", headers=ch).json() == []
    assert client.get(path, headers=bh).status_code == 404
    response = client.post(f"/invitations/{invitation['id']}/accept", headers=bh)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted" and response.json()["responded_at"]
    assert client.get("/invitations", headers=bh).json() == [response.json()]
    assert client.get("/trips", headers=bh).json() == [trip]
    assert client.get("/trips", headers=ah).json() == [trip]
    assert client.get(path, headers=bh).json() == trip
    assert client.get(path, headers=ch).status_code == 404
    assert client.get(path + "/members", headers=ch).status_code == 404
    for headers in (ah, bh):
        members = client.get(path + "/members", headers=headers)
        assert members.status_code == 200
        rows = members.json()
        assert [(r["user_id"], r["role"]) for r in rows] == [
            (alice["id"], "owner"), (bob["id"], "member"),
        ]
        assert all(set(r) == {"user_id", "username", "email", "role", "joined_at"} for r in rows)
        assert "password" not in members.text
    for method, suffix, body in [
        ("PATCH", "", {"name": "Not allowed"}), ("DELETE", "", None),
        ("POST", "/invitations", {"email": "charlie@example.com"}),
    ]:
        assert client.request(method, path + suffix, headers=bh, json=body).status_code == 404
    assert client.get(path, headers=ah).json() == trip
    assert client.post(path + "/invitations", headers=ah,
                       json={"email": "bob@example.com"}).status_code == 409
    # Even a corrupted advisory role cannot grant ownership or appear as Owner.
    conn.execute(TripMember.__table__.update().where(
        TripMember.user_id == bob["id"]
    ).values(role="owner"))
    assert client.patch(path, headers=bh, json={"name": "Escalated"}).status_code == 404
    assert client.get(path + "/members", headers=bh).json()[1]["role"] == "member"


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_invitation_recipient_privacy(collaboration, action):
    client, _, _, users, _ = collaboration
    invitation = invite(collaboration)
    for user in ("alice", "charlie"):
        response = client.post(f"/invitations/{invitation['id']}/{action}", headers=users[user][1])
        missing = client.post(f"/invitations/2147483647/{action}", headers=users[user][1])
        assert response.status_code == missing.status_code == 404
        assert response.json() == missing.json() == {"detail": "Invitation not found"}
    assert client.get("/invitations", headers=users["bob"][1]).json() == [invitation]


@pytest.mark.parametrize("initial", ["accept", "reject"])
def test_terminal_states_and_reinvitation(collaboration, initial):
    client, conn, _, users, trip = collaboration
    invitation = invite(collaboration)
    bh = users["bob"][1]
    response = client.post(f"/invitations/{invitation['id']}/{initial}", headers=bh)
    assert response.status_code == 200
    for action in ("accept", "reject"):
        again = client.post(f"/invitations/{invitation['id']}/{action}", headers=bh)
        assert again.status_code == 409
    count = conn.scalar(select(func.count()).select_from(TripMember).where(
        TripMember.user_id == users["bob"][0]["id"]
    ))
    assert count == (1 if initial == "accept" else 0)
    if initial == "reject":
        assert client.get(f"/trips/{trip['id']}", headers=bh).status_code == 404
        fresh = invite(collaboration)
        assert fresh["id"] != invitation["id"]
        assert [i["status"] for i in client.get("/invitations", headers=bh).json()] == ["rejected", "pending"]
        assert client.post(f"/invitations/{fresh['id']}/accept", headers=bh).status_code == 200


def test_invite_conflicts_and_nonowner(collaboration):
    client, _, _, users, trip = collaboration
    path = f"/trips/{trip['id']}/invitations"
    assert client.post(path, headers=users["alice"][1],
                       json={"email": "alice@example.com"}).status_code == 409
    assert client.post(path, headers=users["alice"][1],
                       json={"email": "not_registered@example.com"}).status_code == 404
    assert client.post(path, headers=users["bob"][1],
                       json={"email": "charlie@example.com"}).status_code == 404
    invite(collaboration)
    assert client.post(path, headers=users["alice"][1],
                       json={"email": "bob@example.com"}).status_code == 409


def test_trip_delete_cascades_members_and_all_invitation_states(collaboration):
    client, conn, _, users, trip = collaboration
    first = invite(collaboration)
    client.post(f"/invitations/{first['id']}/reject", headers=users["bob"][1])
    second = invite(collaboration)
    client.post(f"/invitations/{second['id']}/accept", headers=users["bob"][1])
    invite(collaboration, "charlie")
    assert conn.scalar(select(func.count()).select_from(TripMember)) == 2
    assert conn.scalar(select(func.count()).select_from(TripInvitation)) == 3
    assert client.delete(f"/trips/{trip['id']}", headers=users["alice"][1]).status_code == 204
    assert conn.scalar(select(func.count()).select_from(TripMember)) == 0
    assert conn.scalar(select(func.count()).select_from(TripInvitation)) == 0
    assert client.get("/invitations", headers=users["bob"][1]).json() == []
    assert client.post(f"/invitations/{second['id']}/accept", headers=users["bob"][1]).status_code == 404


def test_accept_rolls_back_insert_when_later_update_fails(collaboration):
    client, conn, _, users, _ = collaboration
    invitation = invite(collaboration)
    seen_insert = []

    def fail_update(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO trip_members"):
            seen_insert.append(True)
        if statement.startswith("UPDATE trip_invitations"):
            raise OperationalError("private SQL", {}, Exception("private details"))

    event.listen(conn, "before_cursor_execute", fail_update)
    try:
        response = client.post(f"/invitations/{invitation['id']}/accept", headers=users["bob"][1])
    finally:
        event.remove(conn, "before_cursor_execute", fail_update)
    assert seen_insert
    assert response.status_code == 503
    assert response.json() == {"detail": "Invitations temporarily unavailable"}
    assert conn.scalar(select(func.count()).select_from(TripMember).where(
        TripMember.user_id == users["bob"][0]["id"]
    )) == 0
    assert client.get("/invitations", headers=users["bob"][1]).json() == [invitation]
    assert client.post(f"/invitations/{invitation['id']}/accept", headers=users["bob"][1]).status_code == 200


def test_trip_and_owner_membership_are_atomic(collaboration):
    client, conn, _, users, _ = collaboration
    before = conn.scalar(select(func.count()).select_from(Trip))

    def fail_member(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO trip_members"):
            raise OperationalError("private SQL", {}, Exception("private details"))

    event.listen(conn, "before_cursor_execute", fail_member)
    try:
        response = client.post("/trips", headers=users["alice"][1], json=TRIP)
    finally:
        event.remove(conn, "before_cursor_execute", fail_member)
    assert response.status_code == 503
    assert conn.scalar(select(func.count()).select_from(Trip)) == before


def test_pending_unique_violation_has_safe_409_and_recovers(collaboration, monkeypatch):
    client, _, _, users, trip = collaboration
    invitation = invite(collaboration)
    original = Session.scalar

    def miss_pending(db, statement, *args, **kwargs):
        if str(statement).startswith("SELECT trip_invitations.id"):
            return None
        return original(db, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "scalar", miss_pending)
        response = client.post(f"/trips/{trip['id']}/invitations", headers=users["alice"][1],
                               json={"email": "bob@example.com"})
    assert response.status_code == 409
    assert response.json() == {"detail": "Invitation or membership already exists"}
    assert client.get("/invitations", headers=users["bob"][1]).json() == [invitation]


@pytest.mark.parametrize("method,path", NEW_ROUTES)
def test_new_routes_require_authentication(method, path):
    def forbidden_db():
        raise AssertionError("Anonymous request accessed database")

    app.dependency_overrides[get_db] = forbidden_db
    try:
        with TestClient(app) as client:
            result = client.request(method, path, json={"email": "bob@example.com"})
        assert result.status_code == 401
        assert result.headers["www-authenticate"] == "Bearer"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("body", [
    {"email": "bad"}, {"email": None}, {},
    {"email": "bob@example.com", "inviter_id": 999},
    {"email": "bob@example.com", "invitee_id": 999},
    {"email": "bob@example.com", "status": "accepted"},
    {"email": "bob@example.com", "role": "owner"},
])
def test_invitation_input_rejects_server_fields(body):
    db = MagicMock(spec=Session)
    app.dependency_overrides[get_current_user] = lambda: User(id=1)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.post("/trips/1/invitations", json=body)
        assert response.status_code == 422
        db.scalar.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


def test_email_policy_is_shared():
    email = " Bob@Example.COM "
    assert InvitationCreate(email=email).email == UserLogin(email=email, password="x").email


@pytest.mark.parametrize("method,path", NEW_ROUTES)
def test_safe_read_failures(method, path):
    db = MagicMock(spec=Session)
    error = OperationalError("private SQL", {}, Exception("private details"))
    db.scalar.side_effect = error
    db.scalars.side_effect = error
    app.dependency_overrides[get_current_user] = lambda: User(id=1)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.request(method, path, json={"email": "bob@example.com"})
        assert response.status_code == 503
        assert "private" not in response.text
        db.rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
