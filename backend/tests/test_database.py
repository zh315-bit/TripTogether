from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import config
from app.db import check, session as database


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    database.get_session_factory.cache_clear()
    database.get_engine.cache_clear()
    yield env_file
    database.get_session_factory.cache_clear()
    database.get_engine.cache_clear()


def test_environment_overrides_dotenv(isolated_config, monkeypatch):
    isolated_config.write_text(
        "DATABASE_URL=postgresql+psycopg://file:secret@localhost/from_file\n"
    )
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://env:p%40ss@localhost/from_env"
    )
    url = config.get_database_url()
    assert url.database == "from_env"
    assert url.password == "p@ss"


def test_dotenv_loaded_independently_of_working_directory(
    isolated_config, monkeypatch, tmp_path
):
    isolated_config.write_text(
        "DATABASE_URL=postgresql+psycopg://user:secret@localhost/from_file\n"
    )
    monkeypatch.chdir(tmp_path)
    assert config.get_database_url().database == "from_file"


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_standard_postgres_provider_url_uses_psycopg(isolated_config, monkeypatch, scheme):
    monkeypatch.setenv("DATABASE_URL", f"{scheme}://user:secret@provider.example/triptogether?sslmode=require")
    url = config.get_database_url()
    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"


def test_missing_database_url(isolated_config):
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        config.get_database_url()


@pytest.mark.parametrize(
    "value",
    ["", "secret-invalid-url", "sqlite:///test.db",
     "postgresql+psycopg://user:secret@localhost",
     "postgresql+psycopg://user:secret@localhost:bad/db"],
)
def test_invalid_configuration_is_rejected(isolated_config, monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(ValueError) as error:
        config.get_database_url()
    assert "secret" not in str(error.value)


def test_engine_and_factory_are_reused_without_connecting(
    isolated_config, monkeypatch
):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:secret@localhost/test"
    )
    engine = database.get_engine()
    try:
        assert database.get_engine() is engine
        factory = database.get_session_factory()
        assert database.get_session_factory() is factory
        with factory() as first, factory() as second:
            assert first is not second
            assert first.get_bind() is engine
    finally:
        engine.dispose()


@pytest.mark.parametrize("fail", [False, True])
def test_dependency_closes_session_after_request(monkeypatch, fail):
    factory = MagicMock()
    db = factory.return_value.__enter__.return_value
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    app = FastAPI()

    @app.get("/probe")
    def probe(session: Session = Depends(database.get_db)):
        assert session is db
        if fail:
            raise RuntimeError("Endpoint failed")
        return {"status": "ok"}

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/probe")
    assert response.status_code == (500 if fail else 200)
    factory.return_value.__exit__.assert_called_once()


def test_check_executes_select_one():
    db = MagicMock(spec=Session)
    db.execute.return_value.scalar_one.return_value = 1
    check.check_connection(db)
    assert str(db.execute.call_args.args[0]) == "SELECT 1"


def test_check_rejects_unexpected_result():
    db = MagicMock(spec=Session)
    db.execute.return_value.scalar_one.return_value = 0
    with pytest.raises(RuntimeError):
        check.check_connection(db)


@pytest.mark.parametrize("fail", [False, True])
def test_check_command_exit_status_and_cleanup(monkeypatch, capsys, fail):
    engine = MagicMock()
    factory = MagicMock()
    db = factory.return_value.__enter__.return_value
    db.execute.return_value.scalar_one.return_value = 1
    if fail:
        db.execute.side_effect = OperationalError(
            "SELECT 1", {}, Exception("private-password")
        )
    monkeypatch.setattr(check, "get_engine", lambda: engine)
    monkeypatch.setattr(check, "get_session_factory", lambda: factory)
    assert check.main() == (1 if fail else 0)
    output = capsys.readouterr()
    assert "private-password" not in output.out + output.err
    assert ("failed" in output.err) if fail else ("passed" in output.out)
    engine.dispose.assert_called_once()
    factory.return_value.__exit__.assert_called_once()


def test_check_command_missing_configuration(isolated_config, capsys):
    assert check.main() == 1
    assert "failed" in capsys.readouterr().err
