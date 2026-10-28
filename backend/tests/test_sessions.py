"""Refresh sessions with rotation and reuse detection; password reset by mail."""
from datetime import timedelta
import logging
import re

import pytest
from sqlalchemy import func, select, update

from app.models import AuthToken
from test_authentication import FAKE_PASSWORD, registered_user


def login(client, password=FAKE_PASSWORD):
    response = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_login_issues_a_refresh_token_that_rotates_once(registered_user):
    client, conn, user = registered_user
    first = login(client)
    assert first["refresh_token"] != first["access_token"] and len(first["refresh_token"]) >= 32
    assert conn.scalar(select(func.count()).select_from(AuthToken)) == 1
    stored = conn.execute(select(AuthToken)).one()
    assert stored.kind == "refresh" and first["refresh_token"] not in stored.token_hash
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200 and second.headers["Cache-Control"] == "no-store"
    pair = second.json()
    assert set(pair) == {"access_token", "token_type", "refresh_token"}
    assert pair["refresh_token"] != first["refresh_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert me.status_code == 200 and me.json()["id"] == user["id"]
    # The old token is spent; the new one still works.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    # ...and that replay revoked the whole family, including the newest token.
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"
    assert conn.scalar(select(func.count()).select_from(AuthToken)) == 0


def test_families_are_independent_and_logout_ends_one(registered_user):
    client, conn, _ = registered_user
    phone, laptop = login(client), login(client)
    assert conn.scalar(select(func.count(func.distinct(AuthToken.family)))) == 2
    assert client.post("/api/v1/auth/logout", json={"refresh_token": phone["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": phone["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": laptop["refresh_token"]}).status_code == 200
    # Logging out an unknown or already-revoked token is harmless.
    assert client.post("/api/v1/auth/logout", json={"refresh_token": "nope"}).status_code == 204


def test_expired_refresh_tokens_are_rejected_and_swept(registered_user):
    client, conn, _ = registered_user
    pair = login(client)
    conn.execute(update(AuthToken).values(expires_at=AuthToken.expires_at - timedelta(days=31)))
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401
    conn.execute(update(AuthToken).values(expires_at=AuthToken.expires_at - timedelta(days=2)))
    login(client)  # issuing a new family sweeps rows expired for more than a day
    assert conn.scalar(select(func.count()).select_from(AuthToken)) == 1


@pytest.mark.parametrize("body", [{}, {"refresh_token": ""}, {"refresh_token": "x" * 201}, {"refresh_token": 1}, {"refresh_token": "t", "extra": 1}])
def test_refresh_and_logout_validate_input(registered_user, body):
    client, _, _ = registered_user
    assert client.post("/api/v1/auth/refresh", json=body).status_code == 422
    assert client.post("/api/v1/auth/logout", json=body).status_code == 422


def reset_link(caplog) -> str:
    match = re.search(r"reset-password\?token=([A-Za-z0-9_\-]+)", caplog.text)
    assert match, caplog.text
    return match.group(1)


def test_forgot_then_reset_signs_out_everywhere(registered_user, caplog, monkeypatch):
    client, conn, _ = registered_user
    monkeypatch.setenv("MAIL_BACKEND", "log")
    monkeypatch.setenv("PASSWORD_RESET_URL", "https://app.example.com/reset-password?token={token}")
    caplog.set_level(logging.INFO, logger="triptogether")
    session = login(client)
    asked = client.post("/api/v1/auth/password/forgot", json={"email": " Alice@Example.com "})
    assert asked.status_code == 202 and asked.json() == {"status": "accepted"}
    token = reset_link(caplog)
    assert "https://app.example.com/reset-password?token=" in caplog.text
    assert token not in str(conn.execute(select(AuthToken.token_hash)).scalars().all())
    # Unknown addresses look identical from the outside and store nothing.
    unknown = client.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"})
    assert unknown.status_code == 202 and unknown.json() == asked.json()
    assert conn.scalar(select(func.count()).select_from(AuthToken).where(AuthToken.kind == "reset")) == 1

    short = client.post("/api/v1/auth/password/reset", json={"token": token, "password": "short"})
    assert short.status_code == 422
    done = client.post("/api/v1/auth/password/reset", json={"token": token, "password": "a-brand-new-password"})
    assert done.status_code == 204
    # Old password gone, new one works, and the earlier refresh session is revoked.
    assert client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": FAKE_PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401
    login(client, "a-brand-new-password")
    # The link works once.
    again = client.post("/api/v1/auth/password/reset", json={"token": token, "password": "another-new-password"})
    assert again.status_code == 400 and again.json()["error"]["code"] == "INVALID_RESET_TOKEN"


def test_reset_token_expires_and_a_new_request_replaces_it(registered_user, caplog, monkeypatch):
    client, conn, _ = registered_user
    monkeypatch.setenv("MAIL_BACKEND", "log")
    caplog.set_level(logging.INFO, logger="triptogether")
    assert client.post("/api/v1/auth/password/forgot", json={"email": "alice@example.com"}).status_code == 202
    first = reset_link(caplog)
    caplog.clear()
    assert client.post("/api/v1/auth/password/forgot", json={"email": "alice@example.com"}).status_code == 202
    second = reset_link(caplog)
    assert first != second
    assert client.post("/api/v1/auth/password/reset", json={"token": first, "password": "a-brand-new-password"}).status_code == 400
    conn.execute(update(AuthToken).where(AuthToken.kind == "reset").values(expires_at=AuthToken.expires_at - timedelta(hours=2)))
    assert client.post("/api/v1/auth/password/reset", json={"token": second, "password": "a-brand-new-password"}).status_code == 400


def test_forgot_is_refused_when_mail_cannot_be_delivered(registered_user, monkeypatch):
    client, _, _ = registered_user
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAIL_BACKEND", "log")
    refused = client.post("/api/v1/auth/password/forgot", json={"email": "alice@example.com"})
    assert refused.status_code == 503 and refused.json()["error"]["code"] == "PASSWORD_RESET_UNAVAILABLE"
    monkeypatch.setenv("MAIL_BACKEND", "smtp")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert client.post("/api/v1/auth/password/forgot", json={"email": "alice@example.com"}).status_code == 503
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "9")  # nothing listens here
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    failed = client.post("/api/v1/auth/password/forgot", json={"email": "alice@example.com"})
    assert failed.status_code == 503 and "nobody" not in failed.text


def test_reset_url_configuration(monkeypatch):
    from app.core.config import password_reset_url
    monkeypatch.setenv("PASSWORD_RESET_URL", "https://x.example/r?t={token}")
    assert password_reset_url("abc") == "https://x.example/r?t=abc"
    monkeypatch.setenv("PASSWORD_RESET_URL", "https://x.example/r")
    with pytest.raises(ValueError):
        password_reset_url("abc")
    monkeypatch.delenv("PASSWORD_RESET_URL")
    monkeypatch.setenv("CORS_ORIGINS", '["https://trip.example.com"]')
    assert password_reset_url("abc") == "https://trip.example.com/reset-password?token=abc"
