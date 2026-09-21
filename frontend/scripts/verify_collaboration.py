"""Opt-in real PostgreSQL/FastAPI collaboration and itinerary smoke test."""
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


def wait_until_ready(client: httpx.Client, server: subprocess.Popen) -> None:
    for _ in range(50):
        if server.poll() is not None:
            raise RuntimeError("Temporary backend failed to start.")
        try:
            if client.get("/ready").status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Temporary backend did not become ready.")


def main() -> int:
    identity = uuid4().hex
    owner_username = "step15_owner_" + identity
    owner_email = owner_username + "@example.com"
    member_username = "step15_member_" + identity
    member_email = member_username + "@example.com"
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
            wait_until_ready(client, server)
            for username, email in (
                (owner_username, owner_email), (member_username, member_email),
            ):
                response = client.post("/api/v1/auth/register", json={
                    "username": username, "email": email, "password": password,
                })
                assert response.status_code == 201

            tokens = {}
            for key, email in (("owner", owner_email), ("member", member_email)):
                response = client.post("/api/v1/auth/login", json={
                    "email": email, "password": password,
                })
                assert response.status_code == 200
                tokens[key] = {"Authorization": f"Bearer {response.json()['access_token']}"}

            trip = client.post("/api/v1/trips", headers=tokens["owner"], json={
                "name": "Step 15 smoke trip", "destination": "Tokyo",
                "start_date": "2027-06-10", "end_date": "2027-06-15",
            })
            assert trip.status_code == 201
            trip_id = trip.json()["id"]

            invitation = client.post(
                f"/api/v1/trips/{trip_id}/invitations",
                headers=tokens["owner"], json={"email": member_email},
            )
            assert invitation.status_code == 201
            invitation_id = invitation.json()["id"]
            inbox = client.get("/api/v1/invitations", headers=tokens["member"])
            assert inbox.status_code == 200 and inbox.json()[0]["id"] == invitation_id
            accepted = client.post(
                f"/api/v1/invitations/{invitation_id}/accept",
                headers=tokens["member"],
            )
            assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
            members = client.get(f"/api/v1/trips/{trip_id}/members", headers=tokens["member"])
            assert members.status_code == 200 and len(members.json()) == 2

            first = client.post(f"/api/v1/trips/{trip_id}/itinerary", headers=tokens["member"], json={
                "title": "Temple", "date": "2027-06-10", "start_time": "09:30",
            })
            second = client.post(f"/api/v1/trips/{trip_id}/itinerary", headers=tokens["owner"], json={
                "title": "Dinner", "date": "2027-06-10", "start_time": "18:00",
            })
            assert first.status_code == 201 and second.status_code == 201
            first_id, second_id = first.json()["id"], second.json()["id"]
            updated = client.patch(
                f"/api/v1/trips/{trip_id}/itinerary/{first_id}",
                headers=tokens["owner"], json={"title": "Updated Temple"},
            )
            assert updated.status_code == 200
            reordered = client.patch(
                f"/api/v1/trips/{trip_id}/itinerary/reorder",
                headers=tokens["member"],
                json={"date": "2027-06-10", "item_ids": [second_id, first_id]},
            )
            assert reordered.status_code == 200
            assert [item["id"] for item in reordered.json()] == [second_id, first_id]
            removed = client.delete(
                f"/api/v1/trips/{trip_id}/itinerary/{second_id}",
                headers=tokens["member"],
            )
            assert removed.status_code == 204
            print("Collaboration and itinerary integration check passed.", flush=True)
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
            owner_id = connection.execute(
                User.__table__.select().with_only_columns(User.id).where(
                    User.username == owner_username, User.email == owner_email,
                )
            ).scalar_one_or_none()
            if owner_id is not None:
                connection.execute(delete(Trip).where(Trip.owner_id == owner_id))
            connection.execute(delete(User).where(
                User.username.in_([owner_username, member_username]),
                User.email.in_([owner_email, member_email]),
            ))
        engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("Collaboration integration failed. Check local PostgreSQL schema and permissions.", file=sys.stderr)
        raise
