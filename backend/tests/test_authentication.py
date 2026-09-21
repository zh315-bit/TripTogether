import json
import time
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import User
from app.schemas.user import UserLogin
from app.services import authentication


FAKE_PASSWORD = "fake-login-password-123"


@pytest.fixture
def registered_user(registration_client, jwt_environment):
    client, connection, _ = registration_client
    payload = {"username": "alice", "email": "alice@example.com", "password": FAKE_PASSWORD}
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    return client, connection, response.json()


def test_register_login_and_current_user(registered_user, jwt_environment):
    client, _, user = registered_user
    response = client.post("/auth/login", json={
        "email": " Alice@Example.COM ", "password": FAKE_PASSWORD,
    })
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert set(data) == {"access_token", "token_type"}
    assert data["token_type"] == "bearer"
    claims = jwt.decode(data["access_token"], jwt_environment, algorithms=["HS256"])
    assert set(claims) == {"sub", "exp"}
    assert claims["sub"] == str(user["id"])
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json() == user
    assert me.headers["Cache-Control"] == "no-store"
    for result in (response, me):
        for forbidden in (FAKE_PASSWORD, "password_hash", "JWT_SECRET_KEY", jwt_environment):
            assert forbidden not in result.text


def test_wrong_password_and_unknown_email_are_identical(registered_user):
    client, _, _ = registered_user
    responses = [
        client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong"}),
        client.post("/auth/login", json={"email": "unknown@example.com", "password": "wrong"}),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json() == {"detail": "Invalid email or password"}


def test_unknown_email_still_verifies_a_dummy_hash(monkeypatch):
    db = MagicMock(spec=Session)
    db.scalar.return_value = None
    verify = MagicMock(return_value=False)
    monkeypatch.setattr(authentication, "verify_password", verify)
    with pytest.raises(authentication.InvalidCredentialsError):
        authentication.authenticate_user(
            db, UserLogin(email="unknown@example.com", password=FAKE_PASSWORD)
        )
    verify.assert_called_once_with(FAKE_PASSWORD, authentication._dummy_password_hash)


@pytest.mark.parametrize("kind", [
    "missing", "wrong_scheme", "empty", "malformed", "expired", "tampered",
    "invalid_sub", "huge_sub", "missing_sub", "missing_exp", "wrong_algorithm",
])
def test_unauthenticated_requests_never_query_database(jwt_environment, kind):
    def forbidden_db():
        raise AssertionError("Invalid credentials must fail before database access")

    claims = {"sub": "1", "exp": int(time.time()) + 300}
    headers = {}
    if kind == "wrong_scheme":
        headers = {"Authorization": "Basic abc123"}
    elif kind == "empty":
        headers = {"Authorization": "Bearer"}
    elif kind != "missing":
        if kind == "expired":
            claims["exp"] = int(time.time()) - 60
        elif kind == "invalid_sub":
            claims["sub"] = "not-an-id"
        elif kind == "huge_sub":
            claims["sub"] = "2147483648"
        elif kind == "missing_sub":
            del claims["sub"]
        elif kind == "missing_exp":
            del claims["exp"]
        token = jwt.encode(
            claims, jwt_environment, algorithm="HS384" if kind == "wrong_algorithm" else "HS256"
        )
        if kind == "malformed":
            token = "abc123"
        elif kind == "tampered":
            parts = token.split(".")
            signature = parts[2]
            parts[2] = ("A" if signature[0] != "A" else "B") + signature[1:]
            token = ".".join(parts)
        headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_db] = forbidden_db
    try:
        with TestClient(app) as client:
            response = client.get("/auth/me", headers=headers)
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json() == {"detail": "Invalid or missing authentication credentials"}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_deleted_user_is_rejected(registered_user):
    client, connection, user = registered_user
    token = client.post("/auth/login", json={
        "email": user["email"], "password": FAKE_PASSWORD,
    }).json()["access_token"]
    connection.execute(delete(User).where(User.id == user["id"]))
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_missing_user_is_rejected(registration_client, jwt_environment):
    client, _, _ = registration_client
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {create_access_token(123)}"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("body", [
    {"email": "bad-email", "password": FAKE_PASSWORD},
    {"email": "alice@example.com", "password": "x" * 129},
    {"email": "alice@example.com", "password": "\ud800" * 8},
    {"password": FAKE_PASSWORD},
])
def test_login_validation_redacts_inputs(body):
    db = MagicMock(spec=Session)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.post("/auth/login", content=json.dumps(body),
                                   headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert FAKE_PASSWORD not in response.text
        assert all("input" not in item for item in response.json()["detail"])
        db.scalar.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_missing_secret_fails_closed_but_health_works(registered_user, monkeypatch):
    client, _, _ = registered_user
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    response = client.post("/auth/login", json={
        "email": "alice@example.com", "password": FAKE_PASSWORD,
    })
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication temporarily unavailable"}
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("endpoint", ["login", "me"])
def test_database_outage_is_safe_503(jwt_environment, endpoint):
    db = MagicMock(spec=Session)
    error = OperationalError("private SQL", {}, Exception("private error details"))
    db.scalar.side_effect = error
    db.get.side_effect = error
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            if endpoint == "login":
                response = client.post("/auth/login", json={
                    "email": "alice@example.com", "password": FAKE_PASSWORD,
                })
            else:
                response = client.get("/auth/me", headers={
                    "Authorization": f"Bearer {create_access_token(1)}",
                })
        assert response.status_code == 503
        assert response.json() == {"detail": "Authentication temporarily unavailable"}
        db.rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_swagger_bearer_security_schema():
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
        assert client.get("/docs").status_code == 200
    scheme = spec["components"]["securitySchemes"]["BearerAuth"]
    assert scheme["type"] == "http"
    assert scheme["scheme"] == "bearer"
    assert spec["paths"]["/api/v1/auth/me"]["get"]["security"] == [{"BearerAuth": []}]
    assert not spec["paths"]["/api/v1/auth/login"]["post"].get("security")
    assert "application/json" in spec["paths"]["/api/v1/auth/login"]["post"]["requestBody"]["content"]
