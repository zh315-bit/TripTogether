from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock
import re

from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import User
from test_membership import TRIP


PREFIX = "/api/v1"


def error_contract(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert isinstance(body["error"]["details"], list)
    assert response.headers["cache-control"] == "no-store"
    return body["error"]


def assert_datetime(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_openapi_is_complete_and_unique():
    with TestClient(app) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert client.get("/docs").status_code == 200
    operations = [(path, method, operation) for path, methods in spec["paths"].items()
                  for method, operation in methods.items()]
    assert len(operations) == 27
    assert sum(path.startswith(PREFIX + "/") for path, _, _ in operations) == 25
    ids = [op["operationId"] for _, _, op in operations]
    assert len(ids) == len(set(ids))
    assert set(spec["paths"]) >= {
        PREFIX + "/auth/register", PREFIX + "/auth/login", PREFIX + "/auth/me",
        PREFIX + "/trips", PREFIX + "/invitations", PREFIX + "/trips/{trip_id}/members",
        PREFIX + "/trips/{trip_id}/itinerary", PREFIX + "/trips/{trip_id}/expenses",
        PREFIX + "/trips/{trip_id}/balances", "/health", "/ready",
    }
    for path, method, op in operations:
        assert op["tags"] and op["summary"]
        for status, response in op["responses"].items():
            if int(status) >= 400:
                expected_ref = "#/components/schemas/APIErrorResponse"
                actual_ref = (
                    response.get("content", {}).get("application/json", {})
                    .get("schema", {}).get("$ref", "<missing>")
                )
                assert actual_ref == expected_ref, (
                    f"{method.upper()} {path} status {status}: "
                    f"expected {expected_ref}, got {actual_ref}"
                )
        if method == "delete":
            assert "content" not in op["responses"]["204"]
        if path.startswith(PREFIX) and path not in (PREFIX + "/auth/register", PREFIX + "/auth/login"):
            assert op["security"] == [{"BearerAuth": []}]
    for route in app.routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            assert route.response_model is not None or route.status_code == 204


def test_every_protected_v1_operation_rejects_anonymous_before_database():
    def no_database():
        raise AssertionError("Anonymous database access")
    app.dependency_overrides[get_db] = no_database
    try:
        with TestClient(app) as client:
            checked = 0
            for path, methods in app.openapi()["paths"].items():
                for method, operation in methods.items():
                    if operation.get("security"):
                        response = client.request(method, re.sub(r"\{[^}]+\}", "1", path), json={})
                        error_contract(response, 401, "INVALID_CREDENTIALS")
                        assert response.headers["www-authenticate"] == "Bearer"
                        checked += 1
            assert checked == 23
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("method,path,status,code", [
    ("GET", PREFIX + "/absent", 404, "NOT_FOUND"),
    ("POST", PREFIX + "/auth/me", 405, "METHOD_NOT_ALLOWED"),
])
def test_framework_error_contract(method, path, status, code):
    with TestClient(app) as client:
        error_contract(client.request(method, path), status, code)


@pytest.mark.parametrize("content", [
    '{"password":"sensitive-contract-input"}',
    '{"password":"sensitive-contract-input"',
    '{"username":"x","email":"invalid","password":"sensitive-contract-input"}',
])
def test_validation_contract_preserves_fields_without_inputs(content):
    app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    try:
        with TestClient(app) as client:
            result = client.post(PREFIX + "/auth/register", content=content,
                                 headers={"Content-Type": "application/json"})
            body = error_contract(result, 422, "VALIDATION_ERROR")
        assert body["details"]
        assert all(set(issue) == {"loc", "msg", "type"} for issue in body["details"])
        assert "sensitive-contract-input" not in result.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_real_v1_client_workflow(registration_client, jwt_environment):
    client, _, _ = registration_client
    users = {}
    password = "contract-test-password"
    for name in ("alice", "bob", "outsider"):
        credentials = {"email": name + "@example.com", "password": password}
        registered = client.post(PREFIX + "/auth/register", json={"username": name, **credentials})
        assert registered.status_code == 201
        user = registered.json()
        assert set(user) == {"id", "username", "email", "created_at"}
        assert_datetime(user["created_at"])
        login = client.post(PREFIX + "/auth/login", json=credentials)
        assert login.status_code == 200
        assert set(login.json()) == {"access_token", "token_type"}
        assert login.json()["token_type"] == "bearer"
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        users[name] = (user, headers)
        assert client.get(PREFIX + "/auth/me", headers=headers).json() == user
        assert client.get("/auth/me", headers=headers).json() == user
    alice, ah = users["alice"]
    bob, bh = users["bob"]
    _, oh = users["outsider"]
    error_contract(client.post(PREFIX + "/auth/register", json={
        "username": "unique", "email": alice["email"], "password": password,
    }), 409, "EMAIL_ALREADY_EXISTS")
    error_contract(client.post(PREFIX + "/auth/login", json={
        "email": alice["email"], "password": "incorrect",
    }), 401, "INVALID_CREDENTIALS")
    trip_response = client.post(PREFIX + "/trips", headers=ah, json=TRIP)
    assert trip_response.status_code == 201
    trip = trip_response.json()
    assert set(trip) == set(TRIP) | {"id", "owner_id", "created_at", "updated_at"}
    assert_datetime(trip["created_at"])
    assert_datetime(trip["updated_at"])
    assert trip["start_date"] == "2027-06-10"
    base = PREFIX + f"/trips/{trip['id']}"
    assert client.get(PREFIX + "/trips", headers=ah).json() == [trip]
    assert client.get(PREFIX + "/trips", headers=oh).json() == []
    invited = client.post(base + "/invitations", headers=ah, json={"email": bob["email"]})
    assert invited.status_code == 201
    invitation = invited.json()
    assert set(invitation) == {"id", "trip_id", "inviter_id", "invitee_id",
                               "status", "created_at", "responded_at"}
    assert invitation["responded_at"] is None
    error_contract(client.get(base, headers=bh), 404, "TRIP_NOT_FOUND")
    error_contract(client.get(base, headers=oh), 404, "TRIP_NOT_FOUND")
    assert client.get(PREFIX + "/invitations", headers=bh).json() == [invitation]
    invite_path = PREFIX + f"/invitations/{invitation['id']}/accept"
    error_contract(client.post(invite_path, headers=ah), 404, "INVITATION_NOT_FOUND")
    accepted = client.post(invite_path, headers=bh)
    assert accepted.status_code == 200
    assert_datetime(accepted.json()["responded_at"])
    error_contract(client.post(invite_path, headers=bh), 409, "INVITATION_CONFLICT")
    assert client.get(base, headers=bh).json() == trip
    error_contract(client.patch(base, headers=bh, json={"name": "No"}), 404, "TRIP_NOT_FOUND")
    members = client.get(base + "/members", headers=bh).json()
    assert len(members) == 2
    assert set(members[0]) == {"user_id", "username", "email", "role", "joined_at"}
    item = client.post(base + "/itinerary", headers=bh, json={
        "title": "Temple", "date": "2027-06-10", "start_time": "09:30",
    })
    assert item.status_code == 201 and item.json()["start_time"] == "09:30:00"
    assert item.json()["end_time"] is None
    assert_datetime(item.json()["created_at"])
    error_contract(client.patch(base, headers=ah, json={"start_date": "2027-06-11"}),
                   409, "TRIP_ITINERARY_CONFLICT")
    expense_body = {
        "description": "Dinner", "amount": "100.00", "currency": "USD",
        "paid_by_user_id": alice["id"], "participant_user_ids": [alice["id"], bob["id"]],
        "expense_date": "2027-05-01",
    }
    expense = client.post(base + "/expenses", headers=bh, json=expense_body)
    assert expense.status_code == 201
    data = expense.json()
    assert data["amount"] == "100.00" and all(s["share_amount"] == "50.00" for s in data["splits"])
    assert_datetime(data["updated_at"])
    error_contract(client.post(base + "/expenses", headers=ah,
                               json={**expense_body, "currency": "EUR"}), 409, "EXPENSE_CURRENCY_CONFLICT")
    invalid = error_contract(client.post(base + "/expenses", headers=ah,
                                        json={**expense_body, "amount": 100}), 422, "VALIDATION_ERROR")
    assert invalid["details"][0]["loc"] == ["body", "amount"]
    balance = client.get(base + "/balances", headers=bh)
    assert balance.status_code == 200
    assert set(balance.json()) == {"trip_id", "currency", "members", "suggested_settlements"}
    assert [m["balance"] for m in balance.json()["members"]] == ["50.00", "-50.00"]
    assert sum(Decimal(m["balance"]) for m in balance.json()["members"]) == 0
    for response in (registered, trip_response, accepted, item, expense, balance):
        assert "password_hash" not in response.text and password not in response.text
    error_contract(client.get(base + "/balances", headers=oh), 404, "TRIP_NOT_FOUND")
    deleted = client.delete(base, headers=ah)
    assert deleted.status_code == 204 and deleted.content == b""
    error_contract(client.get(base, headers=bh), 404, "TRIP_NOT_FOUND")


def test_v1_database_failure_is_safe_and_rolls_back(caplog):
    db = MagicMock(spec=Session)
    db.scalars.side_effect = OperationalError("sensitive-sql", {}, Exception("sensitive-password"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(id=1)
    try:
        with TestClient(app) as client:
            response = client.get(PREFIX + "/trips")
            error_contract(response, 503, "TRIPS_UNAVAILABLE")
        db.rollback.assert_called_once()
        assert "sensitive" not in response.text
        assert "sensitive" not in caplog.text
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
