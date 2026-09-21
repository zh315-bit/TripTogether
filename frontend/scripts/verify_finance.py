"""Opt-in real PostgreSQL/FastAPI expense and balance smoke test."""
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
    owner_username = "step16_owner_" + identity
    owner_email = owner_username + "@example.com"
    member_username = "step16_member_" + identity
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

            for username, email in ((owner_username, owner_email), (member_username, member_email)):
                assert client.post("/api/v1/auth/register", json={
                    "username": username, "email": email, "password": password,
                }).status_code == 201
            tokens = {}
            for key, email in (("owner", owner_email), ("member", member_email)):
                login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
                assert login.status_code == 200
                tokens[key] = {"Authorization": f"Bearer {login.json()['access_token']}"}

            trip = client.post("/api/v1/trips", headers=tokens["owner"], json={
                "name": "Step 16 finance trip", "destination": "Tokyo",
                "start_date": "2027-06-10", "end_date": "2027-06-15",
            })
            assert trip.status_code == 201
            trip_id = trip.json()["id"]
            invitation = client.post(
                f"/api/v1/trips/{trip_id}/invitations",
                headers=tokens["owner"], json={"email": member_email},
            )
            invitation_id = invitation.json()["id"]
            assert client.post(
                f"/api/v1/invitations/{invitation_id}/accept",
                headers=tokens["member"],
            ).status_code == 200
            member_ids = [row["user_id"] for row in client.get(
                f"/api/v1/trips/{trip_id}/members", headers=tokens["owner"],
            ).json()]
            expense = client.post(f"/api/v1/trips/{trip_id}/expenses", headers=tokens["member"], json={
                "description": "Dinner", "amount": "100.00", "currency": "USD",
                "paid_by_user_id": member_ids[0], "participant_user_ids": member_ids,
                "expense_date": "2027-06-10",
            })
            assert expense.status_code == 201
            expense_id = expense.json()["id"]
            assert expense.json()["splits"][0]["share_amount"] == "50.00"
            balances = client.get(f"/api/v1/trips/{trip_id}/balances", headers=tokens["owner"])
            assert balances.status_code == 200
            assert balances.json()["currency"] == "USD"
            updated = client.patch(
                f"/api/v1/trips/{trip_id}/expenses/{expense_id}",
                headers=tokens["owner"], json={"amount": "90.00"},
            )
            assert updated.status_code == 200
            assert client.delete(
                f"/api/v1/trips/{trip_id}/expenses/{expense_id}",
                headers=tokens["member"],
            ).status_code == 204
            assert client.get(f"/api/v1/trips/{trip_id}/balances", headers=tokens["owner"]).json()["currency"] is None
            print("Expense and balance integration check passed.", flush=True)
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
        print("Finance integration failed. Check local PostgreSQL schema and permissions.", file=sys.stderr)
        raise
