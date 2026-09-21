from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import Trip, User


PAYLOAD = {
    "name": "Japan Trip", "destination": "Tokyo, Japan",
    "start_date": "2027-06-10", "end_date": "2027-06-20",
}
ENDPOINTS = [("POST", "/trips"), ("GET", "/trips"), ("GET", "/trips/1"),
             ("PATCH", "/trips/1"), ("DELETE", "/trips/1")]


@pytest.fixture
def actors(registration_client, jwt_environment):
    client, connection, sessions = registration_client
    users = {}
    for name in ("alice", "bob"):
        credentials = {"email": name + "@example.com", "password": "fake-trip-password"}
        response = client.post("/auth/register", json={"username": name, **credentials})
        assert response.status_code == 201
        login = client.post("/auth/login", json=credentials)
        assert login.status_code == 200
        users[name] = (response.json(), {"Authorization": "Bearer " + login.json()["access_token"]})
    return client, connection, sessions, users


def test_full_lifecycle_and_list_isolation(actors):
    client, connection, _, users = actors
    alice, ah = users["alice"]
    bob, bh = users["bob"]
    assert client.get("/trips", headers=ah).json() == []
    created = client.post("/trips", headers=ah, json={
        **PAYLOAD, "name": " Japan Trip ", "destination": " Tokyo, Japan ",
    })
    assert created.status_code == 201
    trip = created.json()
    assert set(trip) == set(PAYLOAD) | {"id", "owner_id", "created_at", "updated_at"}
    assert trip["name"] == "Japan Trip" and trip["destination"] == "Tokyo, Japan"
    assert trip["owner_id"] == alice["id"]
    path = f"/trips/{trip['id']}"
    assert client.get(path, headers=ah).json() == trip
    row = connection.execute(select(Trip.__table__)).mappings().one()
    assert row["owner_id"] == alice["id"]
    assert row["start_date"] == date(2027, 6, 10)
    bob_trip = client.post("/trips", headers=bh, json={**PAYLOAD, "name": "Bob Trip"})
    assert bob_trip.status_code == 201 and bob_trip.json()["owner_id"] == bob["id"]
    assert client.get("/trips", headers=ah).json() == [trip]
    assert client.get("/trips", headers=bh).json() == [bob_trip.json()]
    updated = client.patch(path, headers=ah, json={"name": "Updated"})
    assert updated.status_code == 200
    assert updated.json()["updated_at"] > trip["updated_at"]
    assert updated.json()["created_at"] == trip["created_at"]
    assert updated.json()["owner_id"] == alice["id"]
    removed = client.delete(path, headers=ah)
    assert removed.status_code == 204 and removed.content == b""
    assert client.get(path, headers=ah).status_code == 404
    assert client.delete(path, headers=ah).status_code == 404
    assert client.get("/trips", headers=ah).json() == []
    assert client.get("/trips", headers=bh).json() == [bob_trip.json()]


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_nonowner_and_missing_are_identical(actors, method):
    client, _, _, users = actors
    _, ah = users["alice"]
    _, bh = users["bob"]
    trip = client.post("/trips", headers=ah, json=PAYLOAD).json()
    path = f"/trips/{trip['id']}"
    kwargs = {"json": {"name": "Stolen"}} if method == "PATCH" else {}
    response = client.request(method, path, headers=bh, **kwargs)
    missing = client.request(method, "/trips/2147483647", headers=bh, **kwargs)
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json() == {"detail": "Trip not found"}
    assert client.get(path, headers=ah).json() == trip


@pytest.mark.parametrize("changes", [
    {"name": " New Name "}, {"destination": " Osaka "},
    {"start_date": "2027-06-11"}, {"end_date": "2027-06-21"},
    {"start_date": "2027-07-01", "end_date": "2027-07-10", "name": "July"},
])
def test_partial_updates_preserve_other_fields(actors, changes):
    client, _, _, users = actors
    _, headers = users["alice"]
    trip = client.post("/trips", headers=headers, json=PAYLOAD).json()
    response = client.patch(f"/trips/{trip['id']}", headers=headers, json=changes)
    assert response.status_code == 200
    result = response.json()
    for field in PAYLOAD:
        assert result[field] == changes.get(field, trip[field]).strip()
    assert result["updated_at"] > trip["updated_at"]


@pytest.mark.parametrize("changes", [
    {"start_date": "2027-06-25"}, {"end_date": "2027-06-01"},
    {"start_date": "2027-07-10", "end_date": "2027-07-01"},
])
def test_invalid_merged_dates_roll_back(actors, changes):
    client, _, _, users = actors
    _, headers = users["alice"]
    trip = client.post("/trips", headers=headers, json=PAYLOAD).json()
    path = f"/trips/{trip['id']}"
    response = client.patch(path, headers=headers, json=changes)
    assert response.status_code == 422
    assert all("input" not in item for item in response.json()["detail"])
    assert client.get(path, headers=headers).json() == trip
    assert client.patch(path, headers=headers, json={"name": "Recovered"}).status_code == 200


def test_empty_and_unchanged_patch_are_noops(actors):
    client, _, _, users = actors
    _, headers = users["alice"]
    trip = client.post("/trips", headers=headers, json=PAYLOAD).json()
    for body in ({}, {"name": trip["name"]}):
        response = client.patch(f"/trips/{trip['id']}", headers=headers, json=body)
        assert response.status_code == 200 and response.json() == trip


@pytest.mark.parametrize("method,path", ENDPOINTS)
@pytest.mark.parametrize("token", [None, "abc123"])
def test_all_routes_require_authentication(jwt_environment, method, path, token):
    def forbidden_db():
        raise AssertionError("Anonymous/invalid token must not access database")

    app.dependency_overrides[get_db] = forbidden_db
    try:
        with TestClient(app) as client:
            headers = {} if token is None else {"Authorization": "Bearer " + token}
            response = client.request(method, path, headers=headers, json=PAYLOAD)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def boundary_client():
    db = MagicMock(spec=Session)
    app.dependency_overrides[get_current_user] = lambda: User(id=1)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("field", ["owner_id", "id", "created_at", "updated_at"])
@pytest.mark.parametrize("method,path", [("POST", "/trips"), ("PATCH", "/trips/1")])
def test_server_fields_rejected_by_api(boundary_client, field, method, path):
    client, db = boundary_client
    response = client.request(method, path, json={**PAYLOAD, field: 999})
    assert response.status_code == 422
    db.scalar.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_create_rejects_invalid_dates_before_write(boundary_client):
    client, db = boundary_client
    response = client.post("/trips", json={**PAYLOAD, "end_date": "2027-06-01"})
    assert response.status_code == 422
    db.add.assert_not_called()


@pytest.mark.parametrize("value", ["0", "-1", "2147483648", "not-an-id"])
def test_trip_id_bounds(boundary_client, value):
    client, db = boundary_client
    assert client.get("/trips/" + value).status_code == 422
    db.scalar.assert_not_called()


@pytest.mark.parametrize("method,path", ENDPOINTS)
@pytest.mark.parametrize("failure", ["query", "write"])
def test_safe_database_errors_and_rollback(boundary_client, method, path, failure):
    client, db = boundary_client
    error = OperationalError("private SQL", {}, Exception("private details"))
    if failure == "query":
        db.scalar.side_effect = error
        db.scalars.side_effect = error
        db.commit.side_effect = error
    else:
        db.scalar.return_value = Trip(
            id=1, owner_id=1, name="Old", destination="Tokyo",
            start_date=date(2027, 6, 10), end_date=date(2027, 6, 20),
        )
        db.commit.side_effect = IntegrityError("private SQL", {}, Exception("private details"))
        db.scalars.side_effect = error
        if method == "GET" and path != "/trips":
            db.scalar.side_effect = error
    response = client.request(method, path, json=PAYLOAD)
    assert response.status_code == 503
    assert response.json() == {"detail": "Trips temporarily unavailable"}
    db.rollback.assert_called_once()


def test_openapi_protects_all_trip_routes_and_empty_delete_response():
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
    for path in ("/api/v1/trips", "/api/v1/trips/{trip_id}"):
        for operation in spec["paths"][path].values():
            assert operation["security"] == [{"BearerAuth": []}]
    assert "content" not in spec["paths"]["/api/v1/trips/{trip_id}"]["delete"]["responses"]["204"]
