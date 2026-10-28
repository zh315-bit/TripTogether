"""The demo sign-in: three members, one seeded trip, rebuilt when stale."""
from datetime import timedelta

from sqlalchemy import select, update

from app.models import Expense, ItineraryItem, Trip, TripPlace, User
from app.services.demo import TRIP_NAME, ensure_demo
from test_membership import collaboration


def test_demo_is_off_unless_enabled(collaboration, monkeypatch):
    client, conn, _, _, _ = collaboration
    monkeypatch.delenv("DEMO_MODE", raising=False)
    response = client.post("/api/v1/auth/demo", json={})
    assert response.status_code == 404 and response.json()["error"]["code"] == "DEMO_DISABLED"
    assert conn.scalar(select(User.id).where(User.username == "mika_demo")) is None


def test_demo_session_seeds_once_and_shares_the_trip(collaboration, monkeypatch):
    client, conn, _, _, _ = collaboration
    monkeypatch.setenv("DEMO_MODE", "1")
    mika = client.post("/api/v1/auth/demo", json={})
    assert mika.status_code == 200, mika.text
    body = mika.json()
    assert body["member"] == "mika" and body["username"] == "mika_demo" and body["token_type"] == "bearer"
    assert mika.headers["Cache-Control"] == "no-store"
    jonas = client.post("/api/v1/auth/demo", json={"member": "jonas"}).json()
    assert jonas["trip_id"] == body["trip_id"] and jonas["username"] == "jonas_demo"
    assert jonas["access_token"] != body["access_token"]
    # Both sessions work and see the same seeded trip.
    for token in (body["access_token"], jonas["access_token"]):
        headers = {"Authorization": f"Bearer {token}"}
        trip = client.get(f"/api/v1/trips/{body['trip_id']}", headers=headers).json()
        assert trip["name"] == TRIP_NAME
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    base = f"/api/v1/trips/{body['trip_id']}"
    assert len(client.get(f"{base}/members", headers=headers).json()) == 3
    assert len(client.get(f"{base}/places", headers=headers).json()) == 5
    items = client.get(f"{base}/itinerary", headers=headers).json()
    assert len(items) == 6 and sum(item["place_id"] is not None for item in items) == 5
    expenses = client.get(f"{base}/expenses", headers=headers).json()
    assert sorted(e["split_method"] for e in expenses) == ["equal", "exact", "shares"]
    balance = client.get(f"{base}/balances", headers=headers).json()
    assert balance["currency"] == "USD" and balance["settlement"]["minimal"]
    assert sum(float(m["balance"]) for m in balance["members"]) == 0
    # A third sign-in reuses the trip rather than seeding another.
    client.post("/api/v1/auth/demo", json={"member": "aiko"})
    assert conn.scalar(select(Trip.id).where(Trip.name == TRIP_NAME).limit(2)) is not None
    assert len(conn.scalars(select(Trip.id).where(Trip.name == TRIP_NAME)).all()) == 1


def test_stale_demo_trip_is_rebuilt(collaboration, monkeypatch):
    client, conn, _, _, _ = collaboration
    monkeypatch.setenv("DEMO_MODE", "1")
    first = client.post("/api/v1/auth/demo", json={}).json()
    headers = {"Authorization": f"Bearer {first['access_token']}"}
    # A visitor's edit survives while the trip is fresh.
    assert client.post(f"/api/v1/trips/{first['trip_id']}/itinerary", headers=headers, json={
        "title": "Visitor's addition", "date": "2027-04-03"}).status_code == 201
    assert client.post("/api/v1/auth/demo", json={}).json()["trip_id"] == first["trip_id"]
    conn.execute(update(Trip).where(Trip.id == first["trip_id"]).values(
        created_at=Trip.created_at - timedelta(hours=7)))
    rebuilt = client.post("/api/v1/auth/demo", json={}).json()
    assert rebuilt["trip_id"] != first["trip_id"]
    assert conn.scalar(select(Trip.id).where(Trip.id == first["trip_id"])) is None
    assert conn.scalar(select(ItineraryItem.id).where(ItineraryItem.title == "Visitor's addition")) is None
    assert conn.scalar(select(Trip.name).where(Trip.id == rebuilt["trip_id"])) == TRIP_NAME
    assert len(conn.scalars(select(TripPlace.id).where(TripPlace.trip_id == rebuilt["trip_id"])).all()) == 5
    assert len(conn.scalars(select(Expense.id).where(Expense.trip_id == rebuilt["trip_id"])).all()) == 3


def test_demo_accepts_only_known_members(collaboration, monkeypatch):
    client, _, _, _, _ = collaboration
    monkeypatch.setenv("DEMO_MODE", "1")
    assert client.post("/api/v1/auth/demo", json={"member": "root"}).status_code == 422
    assert client.post("/api/v1/auth/demo", json={"member": "mika", "extra": 1}).status_code == 422


def test_reset_rebuilds_on_demand(collaboration, monkeypatch):
    _, conn, sessions, _, _ = collaboration
    from sqlalchemy.orm import Session
    with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
        users, trip = ensure_demo(db)
        _, again = ensure_demo(db)
        assert again.id == trip.id
        _, rebuilt = ensure_demo(db, reset=True)
        assert rebuilt.id != trip.id and set(users) == {"mika", "jonas", "aiko"}
