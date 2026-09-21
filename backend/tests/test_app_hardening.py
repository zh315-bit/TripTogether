import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import config
from app.db import session as database
from app.db.session import get_db
from app.main import create_app
from test_api_contract import error_contract


@pytest.fixture
def settings_env(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "[]")
    return monkeypatch


@pytest.mark.parametrize("value", [
    "*", '["*"]', "null", "{}", '["null"]', '["https://example.com/"]',
    '["https://user:secret@example.com"]', '["https://example.com?q=x"]',
    '["https://example.com#x"]', '["https://example.com:wrong"]', '["https://example.com:0"]',
    '["https://example.com:"]', '["https://bad host"]', '["https://*.example.com"]',
    '[42]', '["file://example.com"]',
])
def test_rejects_unsafe_cors_config(settings_env, value):
    settings_env.setenv("CORS_ORIGINS", value)
    with pytest.raises(ValueError) as error:
        config.get_app_settings()
    assert "secret@" not in str(error.value)


def test_config_precedence_and_environment_validation(settings_env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('APP_ENV=production\nCORS_ORIGINS=["https://example.com"]\n')
    settings_env.setattr(config, "ENV_FILE", env_file)
    assert config.get_app_settings().environment == "development"
    settings_env.delenv("APP_ENV")
    settings_env.delenv("CORS_ORIGINS")
    assert config.get_app_settings().cors_origins == ("https://example.com",)
    settings_env.setenv("APP_ENV", "staging-typo")
    with pytest.raises(ValueError):
        config.get_app_settings()
    settings_env.setenv("APP_ENV", "production")
    settings_env.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    with pytest.raises(ValueError):
        config.get_app_settings()


@pytest.mark.parametrize("origin,allowed", [
    ("http://localhost:3000", True), ("http://127.0.0.1:3000", False),
    ("https://untrusted.example", False), ("null", False),
])
def test_cors_preflight(settings_env, origin, allowed):
    settings_env.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    with TestClient(create_app()) as client:
        response = client.options("/api/v1/trips", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        })
        assert response.status_code == (200 if allowed else 400)
        assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)
        assert "access-control-allow-credentials" not in response.headers


def test_cors_401_and_disallowed_method(settings_env):
    settings_env.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/trips", headers={"Origin": "http://localhost:3000"})
        error_contract(response, 401, "INVALID_CREDENTIALS")
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        denied = client.options("/api/v1/trips", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "TRACE",
        })
        assert denied.status_code == 400


@pytest.mark.parametrize("broken", [False, True])
def test_readiness_and_liveness(settings_env, jwt_environment, broken, caplog):
    application = create_app()
    db = MagicMock(spec=Session)
    db.execute.return_value.scalar_one.return_value = 1
    if broken:
        db.execute.side_effect = OperationalError("secret SQL", {}, Exception("private-password"))
    application.dependency_overrides[get_db] = lambda: db
    with TestClient(application) as client:
        assert client.get("/health").json() == {"status": "ok"}
        db.execute.assert_not_called()
        response = client.get("/ready")
        if broken:
            error_contract(response, 503, "NOT_READY")
            db.rollback.assert_called_once()
        else:
            assert response.status_code == 200 and response.json() == {"status": "ready"}
    assert "private-password" not in caplog.text + response.text
    assert "Application startup" in caplog.text and "Application shutdown" in caplog.text


def test_readiness_missing_jwt(settings_env):
    settings_env.setenv("JWT_SECRET_KEY", "")
    application = create_app()
    db = MagicMock(spec=Session)
    application.dependency_overrides[get_db] = lambda: db
    with TestClient(application) as client:
        error_contract(client.get("/ready"), 503, "NOT_READY")
        db.execute.assert_not_called()


@pytest.mark.parametrize("production", [False, True])
def test_missing_secrets_development_liveness_or_production_startup_failure(settings_env, production, caplog):
    settings_env.setenv("APP_ENV", "production" if production else "development")
    settings_env.setenv("DATABASE_URL", "postgresql+psycopg://user:private-db-secret@localhost/db")
    settings_env.setenv("JWT_SECRET_KEY", "")
    application = create_app()
    if production:
        with pytest.raises(RuntimeError, match="Production configuration invalid"):
            with TestClient(application):
                pass
    else:
        with TestClient(application) as client:
            assert client.get("/health").status_code == 200
    assert "private-db-secret" not in caplog.text


def test_production_valid_config_does_not_connect_on_startup(settings_env, jwt_environment):
    settings_env.setenv("APP_ENV", "production")
    settings_env.setenv("DATABASE_URL", "postgresql+psycopg://user:placeholder@localhost/db")
    def no_connect():
        raise AssertionError("Startup should not connect")
    settings_env.setattr(database, "get_engine", no_connect)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200


def test_blank_long_secret_rejected(settings_env):
    settings_env.setenv("JWT_SECRET_KEY", " " * 64)
    with pytest.raises(config.JWTConfigurationError):
        config.get_jwt_settings()


def test_dependency_initialization_failure_safe_503(settings_env, caplog):
    def failed_factory():
        raise ValueError("database-url-private-password")
    settings_env.setattr(database, "get_session_factory", failed_factory)
    with TestClient(create_app()) as client:
        response = client.get("/ready")
        error_contract(response, 503, "DATABASE_UNAVAILABLE")
    assert "private-password" not in caplog.text + response.text


def test_unexpected_error_redaction_and_cors(settings_env, caplog):
    settings_env.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    application = create_app()

    @application.get("/api/v1/test-failure")
    def fail():
        raise RuntimeError("private-password private-jwt private-database-url")

    with TestClient(application) as client:
        response = client.get("/api/v1/test-failure?token=private-query", headers={
            "Authorization": "Bearer private-header", "Origin": "http://localhost:3000",
        })
        error_contract(response, 500, "INTERNAL_ERROR")
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    records = [r for r in caplog.records if r.name == "triptogether"]
    assert any(r.getMessage() == "Unexpected server error" for r in records)
    assert all("private-" not in r.getMessage() and not r.exc_info for r in records)
    assert "private-" not in response.text
    assert logging.getLogger("uvicorn.access").disabled


def test_real_postgres_readiness(registration_client, jwt_environment):
    client, _, _ = registration_client
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
