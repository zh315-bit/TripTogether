"""Every response carries a request id, and every request leaves one JSON access line."""
import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, RequestIdFilter, log_format, request_id_var
from app.main import app
from test_membership import collaboration


def access_lines(caplog):
    return [r for r in caplog.records if r.name == "triptogether.access"]


def test_request_id_is_generated_echoed_or_replaced(caplog):
    with TestClient(app) as client:
        generated = client.get("/health").headers["X-Request-ID"]
        assert len(generated) == 32 and all(c in "0123456789abcdef" for c in generated)
        echoed = client.get("/health", headers={"X-Request-ID": "trace-abc.123_x"}).headers["X-Request-ID"]
        assert echoed == "trace-abc.123_x"
        for bad in ("has space", "x" * 65, "quote\"", ""):
            replaced = client.get("/health", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
            assert replaced != bad and len(replaced) == 32
        # Liveness probes are not logged; everything else is, with the route template.
        assert access_lines(caplog) == []
        missing = client.get("/api/v1/trips/999?token=secret-query", headers={"X-Request-ID": "req-1"})
        assert missing.status_code == 401
    line = access_lines(caplog)[-1]
    assert line.fields == {
        "event": "request", "method": "GET", "path": "/api/v1/trips/{trip_id}",
        "status": 401, "duration_ms": line.fields["duration_ms"],
    }
    assert "secret-query" not in caplog.text
    assert request_id_var.get() == "-"  # reset after the request


def test_access_line_carries_the_request_id_and_formats_as_json(collaboration, caplog):
    client, _, _, users, trip = collaboration
    caplog.set_level(logging.INFO, logger="triptogether.access")
    response = client.get(f"/api/v1/trips/{trip['id']}", headers={**users["alice"][1], "X-Request-ID": "req-42"})
    assert response.status_code == 200 and response.headers["X-Request-ID"] == "req-42"
    record = [r for r in access_lines(caplog) if r.fields["path"] == "/api/v1/trips/{trip_id}"][-1]
    RequestIdFilter().filter(record)
    # The filter reads the context var, which has been reset; the id was bound while handling.
    record.request_id = "req-42"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "req-42" and payload["status"] == 200
    assert payload["path"] == "/api/v1/trips/{trip_id}" and payload["level"] == "INFO"
    assert set(payload) >= {"time", "level", "logger", "message", "request_id", "event", "method", "duration_ms"}


def test_error_logs_share_the_request_id(caplog):
    from unittest.mock import MagicMock
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session
    from app.api.dependencies import get_current_user
    from app.db.session import get_db
    from app.models import User

    db = MagicMock(spec=Session)
    db.scalars.side_effect = OperationalError("sql", {}, Exception("x"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(id=1)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/trips", headers={"X-Request-ID": "req-err"})
        assert response.status_code == 503
        error_record = [r for r in caplog.records if r.levelno >= logging.ERROR][-1]
        assert error_record.request_id == "req-err"
        assert access_lines(caplog)[-1].fields["status"] == 503
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_log_format_defaults(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    assert log_format("production") == "json" and log_format("development") == "text"
    monkeypatch.setenv("LOG_FORMAT", "JSON")
    assert log_format("development") == "json"
