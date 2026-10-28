"""Login and registration are rate limited per client with a database-backed window."""
from datetime import timedelta

import pytest
from sqlalchemy import delete, inspect, select, text, update

from app.models import RateLimit
from app.services.rate_limiting import RateLimitRule, parse_rule
from test_membership import collaboration


LOGIN = {"email": "alice@example.com", "password": "not-the-password-1"}


def fresh(conn):
    """The collaboration fixture already signed in several times; start the windows over."""
    conn.execute(delete(RateLimit))


@pytest.mark.parametrize("value,expected", [
    ("10/60", RateLimitRule(10, 60)), (" 3 / 5 ", RateLimitRule(3, 5)), ("off", None),
    ("", None), (None, None), ("0", None),
])
def test_rules_parse(value, expected):
    assert parse_rule(value) == expected


@pytest.mark.parametrize("value", ["10", "10/", "/60", "ten/60", "10/60/1", "-1/60", "10/0", "1000000/60"])
def test_bad_rules_are_rejected(value):
    with pytest.raises(ValueError):
        parse_rule(value)


def test_migration_creates_the_window_table(migrated_database):
    conn, _ = migrated_database
    columns = {c["name"]: c for c in inspect(conn).get_columns("rate_limits")}
    assert set(columns) == {"key", "window_start", "count"}
    assert not columns["count"]["nullable"] and not columns["window_start"]["nullable"]
    assert [i["name"] for i in inspect(conn).get_indexes("rate_limits")] == ["ix_rate_limits_window_start"]


def test_login_attempts_are_limited_per_client_and_recover(collaboration, monkeypatch):
    client, conn, _, users, _ = collaboration
    fresh(conn)
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "3/60")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    path = "/api/v1/auth/login"
    # Wrong passwords count: brute force is the whole point.
    for _ in range(3):
        assert client.post(path, json=LOGIN).status_code == 401
    blocked = client.post(path, json=LOGIN)
    assert blocked.status_code == 429
    assert blocked.json() == {"error": {
        "code": "RATE_LIMITED", "message": "Too many attempts; try again shortly", "details": []}}
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    assert blocked.headers["Cache-Control"] == "no-store"
    # The right password is blocked too; the limit is about the client, not the outcome.
    good = {"email": "alice@example.com", "password": users["alice"][0].get("password", "x")}
    assert client.post(path, json=good).status_code == 429
    # Legacy path shares the counter and answers with the legacy body shape.
    legacy = client.post("/auth/login", json=LOGIN)
    assert legacy.status_code == 429 and legacy.json() == {"detail": "Too many attempts; try again shortly"}
    # Another client, as named by the trusted proxy header, has its own window.
    other = client.post(path, json=LOGIN, headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
    assert other.status_code == 401
    assert conn.scalar(select(RateLimit.key).where(RateLimit.key == "login:203.0.113.9")) is not None
    # Once the window has passed, the counter starts over.
    conn.execute(update(RateLimit).values(window_start=RateLimit.window_start - timedelta(seconds=61)))
    assert client.post(path, json=LOGIN).status_code == 401
    assert conn.scalar(select(RateLimit.count).where(RateLimit.key == "login:testclient")) == 1


def test_proxy_header_is_ignored_unless_trusted(collaboration, monkeypatch):
    client, conn, _, _, _ = collaboration
    fresh(conn)
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "2/60")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "0")
    for _ in range(2):
        assert client.post("/api/v1/auth/login", json=LOGIN).status_code == 401
    # A client cannot escape its window by inventing a forwarded address.
    spoofed = client.post("/api/v1/auth/login", json=LOGIN, headers={"X-Forwarded-For": "198.51.100.7"})
    assert spoofed.status_code == 429
    assert conn.scalar(select(RateLimit.key).where(RateLimit.key.like("login:198.%"))) is None


def test_registration_limit_and_off_switch(collaboration, monkeypatch):
    client, conn, _, _, _ = collaboration
    fresh(conn)
    monkeypatch.setenv("RATE_LIMIT_REGISTER", "1/60")
    body = {"username": "limited1", "email": "limited1@example.com", "password": "long-enough-pw"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    second = client.post("/api/v1/auth/register", json={**body, "username": "limited2", "email": "l2@example.com"})
    assert second.status_code == 429 and second.json()["error"]["code"] == "RATE_LIMITED"
    # Validation still runs first and never consumes the window.
    assert client.post("/api/v1/auth/register", json={**body, "password": "short"}).status_code == 422
    monkeypatch.setenv("RATE_LIMIT_REGISTER", "off")
    assert client.post("/api/v1/auth/register", json={
        **body, "username": "limited3", "email": "l3@example.com"}).status_code == 201


def test_bad_rule_configuration_fails_closed(collaboration, monkeypatch):
    client, _, _, _, _ = collaboration
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "lots")
    response = client.post("/api/v1/auth/login", json=LOGIN)
    assert response.status_code == 503 and response.json()["error"]["code"] == "RATE_LIMITER_UNAVAILABLE"


def test_new_window_sweeps_stale_rows(collaboration, monkeypatch):
    client, conn, _, _, _ = collaboration
    fresh(conn)
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "5/60")
    conn.execute(text(
        "INSERT INTO rate_limits (key, window_start, count) VALUES ('login:old', clock_timestamp() - interval '2 days', 4)"))
    assert client.post("/api/v1/auth/login", json=LOGIN).status_code == 401
    assert conn.scalar(select(RateLimit.key).where(RateLimit.key == "login:old")) is None
