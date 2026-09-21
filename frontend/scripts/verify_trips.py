"""Opt-in real frontend/API/PostgreSQL Trip CRUD smoke test."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import delete

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import get_engine  # noqa: E402
from app.models import Trip, User  # noqa: E402


def main() -> int:
    identity = uuid4().hex
    username = "step14_" + identity
    email = "step14_" + identity + "@example.com"
    password = secrets.token_urlsafe(24)
    engine = get_engine()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "APP_ENV": "development",
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "CORS_ORIGINS": '["http://127.0.0.1:5173"]',
    }
    server = None
    try:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT / "backend", env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
            for _ in range(50):
                if server.poll() is not None:
                    raise RuntimeError("Temporary backend failed to start.")
                try:
                    if client.get("/ready").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Temporary backend did not become ready.")

            registered = client.post("/api/v1/auth/register", json={
                "username": username, "email": email, "password": password,
            })
            assert registered.status_code == 201
            login = client.post("/api/v1/auth/login", json={
                "email": email, "password": password,
            })
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            payload = {
                "name": "Step 14 smoke trip",
                "destination": "Tokyo",
                "start_date": "2027-06-10",
                "end_date": "2027-06-15",
            }
            created = client.post("/api/v1/trips", json=payload, headers=headers)
            assert created.status_code == 201
            trip_id = created.json()["id"]
            assert client.get("/api/v1/trips", headers=headers).status_code == 200
            assert client.get(f"/api/v1/trips/{trip_id}", headers=headers).status_code == 200
            updated = client.patch(
                f"/api/v1/trips/{trip_id}",
                json={"name": "Updated smoke trip"},
                headers=headers,
            )
            assert updated.status_code == 200
            assert updated.json()["name"] == "Updated smoke trip"
            assert client.delete(f"/api/v1/trips/{trip_id}", headers=headers).status_code == 204
            assert client.get(f"/api/v1/trips/{trip_id}", headers=headers).status_code == 404
            print("Trip CRUD integration check passed.", flush=True)
            return 0
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        with engine.begin() as connection:
            connection.execute(delete(Trip).where(Trip.owner_id == (
                connection.execute(
                    User.__table__.select().with_only_columns(User.id).where(
                        User.username == username, User.email == email,
                    )
                ).scalar_one_or_none()
            )))
            connection.execute(delete(User).where(
                User.username == username, User.email == email,
            ))
        engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("Trip integration failed. Check local PostgreSQL schema and permissions.", file=sys.stderr)
        raise
