from fastapi.testclient import TestClient

from app.main import app
from app.db import session as database


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_does_not_access_database(monkeypatch) -> None:
    def fail_if_called():
        raise AssertionError("Health must not access the database")

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "get_engine", fail_if_called)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
