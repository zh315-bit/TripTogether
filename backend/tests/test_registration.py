import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.session import get_db
from app.main import app
from app.models import User
from app.schemas.user import UserRegister


FAKE_PASSWORD = "fake-test-password-123"


@pytest.fixture
def payload() -> dict:
    return {
        "username": "alice", "email": "alice@example.com", "password": FAKE_PASSWORD,
    }


@pytest.fixture
def validation_client():
    db = MagicMock(spec=Session)
    db.scalar.side_effect = AssertionError("Invalid input must not query the database")
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("username", ""), ("username", "   "), ("username", "a" * 51),
        ("username", "invalid name"), ("username", "bad-name"),
        ("email", "not-an-email"), ("email", None),
        ("password", "123"), ("password", "x" * 129),
        ("password", None), ("password", 12345678),
        ("password", "\ud800" * 8),
    ],
)
def test_invalid_registration_returns_safe_422(
    validation_client, payload, field, value
) -> None:
    client, db = validation_client
    payload[field] = value
    response = client.post(
        "/auth/register", content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert FAKE_PASSWORD not in response.text
    assert all("input" not in item and "ctx" not in item for item in response.json()["detail"])
    db.scalar.assert_not_called()


def test_missing_fields_and_extra_credentials_are_not_echoed(validation_client) -> None:
    client, _ = validation_client
    response = client.post("/auth/register", json={
        "password": FAKE_PASSWORD, "password_hash": "fake-sensitive-hash",
    })
    assert response.status_code == 422
    assert FAKE_PASSWORD not in response.text
    assert "fake-sensitive-hash" not in response.text


def test_malformed_json_does_not_echo_body(validation_client) -> None:
    client, _ = validation_client
    response = client.post(
        "/auth/register", content='{"password":"' + FAKE_PASSWORD + '"',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert FAKE_PASSWORD not in response.text


def test_normalization_secret_repr_and_password_boundaries(payload) -> None:
    payload.update(username=" Alice_1 ", email=" Alice@Example.COM ")
    for password in ("a" * 8, "\u00e9" * 128, "  abcdef  "):
        model = UserRegister(**{**payload, "password": password})
        assert model.username == "Alice_1"
        assert model.email == "alice@example.com"
        assert model.password.get_secret_value() == password
        assert password not in repr(model)


def test_openapi_and_docs_expose_safe_schemas() -> None:
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/auth/register"]["post"]
    assert "201" in operation["responses"]
    assert {"409", "422", "503"} <= set(operation["responses"])
    issues = schema["components"]["schemas"]["ValidationIssue"]["properties"]
    assert set(issues) == {"loc", "msg", "type"}
    request = schema["components"]["schemas"]["UserRegister"]["properties"]
    assert request["password"]["writeOnly"]
    assert request["password"]["format"] == "password"
    response = schema["components"]["schemas"]["UserResponse"]["properties"]
    assert set(response) == {"id", "username", "email", "created_at"}


def test_registration_persists_hash_and_safe_response(registration_client, payload) -> None:
    client, connection, _ = registration_client
    response = client.post("/auth/register", json={
        **payload, "username": " alice ", "email": "Alice@Example.COM",
    })
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "username", "email", "created_at"}
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"
    assert datetime.fromisoformat(body["created_at"].replace("Z", "+00:00")).tzinfo
    row = connection.execute(select(User.__table__)).mappings().one()
    assert row["id"] == body["id"]
    assert row["password_hash"] != FAKE_PASSWORD
    assert verify_password(FAKE_PASSWORD, row["password_hash"])
    assert row["password_hash"] not in response.text
    assert FAKE_PASSWORD not in response.text


@pytest.mark.parametrize("field", ["username", "email"])
def test_duplicate_registration_returns_409(registration_client, payload, field) -> None:
    client, connection, _ = registration_client
    assert client.post("/auth/register", json=payload).status_code == 201
    duplicate = {**payload, "username": "other", "email": "other@example.com"}
    duplicate[field] = "alice" if field == "username" else "ALICE@EXAMPLE.COM"
    response = client.post("/auth/register", json=duplicate)
    assert response.status_code == 409
    assert response.json() == {"detail": f"{field.capitalize()} already registered"}
    assert connection.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize("field", ["username", "email"])
def test_unique_race_fallback_rolls_back_and_recovers(
    registration_client, payload, monkeypatch, field
) -> None:
    client, connection, sessions = registration_client
    assert client.post("/auth/register", json=payload).status_code == 201
    duplicate = {**payload, "username": "other", "email": "other@example.com"}
    duplicate[field] = payload[field]
    # Deterministic race outcome: both pre-checks see no row, INSERT still hits UNIQUE.
    with monkeypatch.context() as patch:
        patch.setattr(Session, "scalar", lambda *args, **kwargs: None)
        rollback = Session.rollback
        rolled_back = []

        def record_rollback(db):
            rolled_back.append(db)
            return rollback(db)

        patch.setattr(Session, "rollback", record_rollback)
        response = client.post("/auth/register", json=duplicate)
    assert response.status_code == 409
    assert rolled_back == [sessions[-1]]
    assert connection.scalar(select(func.count()).select_from(User)) == 1
    assert client.post("/auth/register", json={
        **payload, "username": "new", "email": "new@example.com",
    }).status_code == 201
    assert connection.scalar(select(func.count()).select_from(User)) == 2


@pytest.mark.parametrize("stage", ["query", "commit", "integrity"])
def test_database_failure_rolls_back_without_details(
    validation_client, payload, stage
) -> None:
    client, db = validation_client
    error = OperationalError("sensitive SQL", {}, Exception("fake-sensitive-hash"))
    db.scalar.side_effect = None
    db.scalar.return_value = None
    if stage == "query":
        db.scalar.side_effect = error
    elif stage == "commit":
        db.commit.side_effect = error
    else:
        db.commit.side_effect = IntegrityError(
            "sensitive SQL", {},
            SimpleNamespace(sqlstate="23502", diag=SimpleNamespace(constraint_name=None)),
        )
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 503
    assert response.json() == {"detail": "Registration temporarily unavailable"}
    assert "fake-sensitive-hash" not in response.text
    assert FAKE_PASSWORD not in response.text
    db.rollback.assert_called_once()
