import os
import secrets
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.orm import Session

from app.core import config as app_config
from app.core.config import get_database_url
from app.db.session import get_db
from app.main import app


@pytest.fixture
def migrated_database() -> Iterator[tuple[Connection, Config]]:
    """Run real migrations in a private schema, then roll back all test DDL."""
    if os.environ.get("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_TESTS=1 with a real PostgreSQL DATABASE_URL.")
    engine = create_engine(get_database_url(), connect_args={"connect_timeout": 5})
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    schema = "test_users_" + uuid4().hex
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                yield connection, config
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.fixture
def registration_client(migrated_database):
    connection, _ = migrated_database
    sessions = []

    def override_db():
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            sessions.append(db)
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, connection, sessions
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def jwt_environment(monkeypatch):
    # JWT tests never use the developer's signing key.
    secret = secrets.token_urlsafe(48)
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    return secret


@pytest.fixture
def isolated_jwt_config(monkeypatch, tmp_path):
    for name in ("JWT_SECRET_KEY", "JWT_ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    monkeypatch.setattr(app_config, "ENV_FILE", env_file)
    return env_file
