"""The postgres realtime backend: NOTIFY inside the transaction, one relay per instance."""
import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_database_url
from app.realtime import (
    CHANNEL, RESYNC, PostgresRelay, TripEvent, TripEventBroker, listen_dsn, realtime_backend, stage,
)


pytestmark = pytest.mark.usefixtures("postgres_only")


@pytest.fixture
def postgres_only(monkeypatch):
    import os
    if os.environ.get("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_TESTS=1 with a real PostgreSQL DATABASE_URL.")
    monkeypatch.setenv("REALTIME_BACKEND", "postgres")


def test_backend_setting(monkeypatch):
    monkeypatch.delenv("REALTIME_BACKEND", raising=False)
    assert realtime_backend() == "memory"
    monkeypatch.setenv("REALTIME_BACKEND", " Postgres ")
    assert realtime_backend() == "postgres"
    monkeypatch.setenv("REALTIME_BACKEND", "redis")
    with pytest.raises(ValueError):
        realtime_backend()


def test_listen_dsn_is_the_libpq_form():
    dsn = listen_dsn()
    assert dsn.startswith("postgresql://") and "+psycopg" not in dsn
    assert get_database_url().database in dsn


async def wait_until(predicate, timeout=5.0):
    for _ in range(int(timeout / 0.02)):
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


async def notify(payload: dict) -> None:
    import psycopg
    async with await psycopg.AsyncConnection.connect(listen_dsn(), autocommit=True) as connection:
        await connection.execute("SELECT pg_notify(%s, %s)", (CHANNEL, json.dumps(payload)))


def test_relay_feeds_local_subscribers_and_ends_deleted_trips():
    async def scenario():
        target = TripEventBroker()
        target.bind(asyncio.get_running_loop())
        relay = PostgresRelay(listen_dsn(), target, retry=0.05)
        task = asyncio.create_task(relay.run())
        try:
            await wait_until(lambda: relay.connected)
            async with target.subscribe(7) as queue, target.subscribe(8) as other:
                event = TripEvent(7, "itinerary", "updated", 3, 11, 2, "2027-06-10").payload()
                await notify(event)
                assert await asyncio.wait_for(queue.get(), 5) == event
                await notify({"garbage": True})
                await notify({"type": "trip.deleted", "trip_id": 7, "entity": "trip", "action": "deleted", "actor_id": 3})
                assert (await asyncio.wait_for(queue.get(), 5))["type"] == "trip.deleted"
                assert await asyncio.wait_for(queue.get(), 5) is None
                assert other.empty()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(scenario())


def test_committed_sessions_notify_once_and_rollbacks_never():
    async def scenario():
        target = TripEventBroker()
        target.bind(asyncio.get_running_loop())
        relay = PostgresRelay(listen_dsn(), target, retry=0.05)
        task = asyncio.create_task(relay.run())
        engine = create_engine(get_database_url())
        try:
            await wait_until(lambda: relay.connected)
            async with target.subscribe(5) as queue:
                def write(commit: bool):
                    with Session(engine) as db:
                        stage(db, TripEvent(5, "expense", "created", 2, 9, 1))
                        if commit:
                            db.commit()
                        else:
                            db.rollback()
                await asyncio.to_thread(write, True)
                received = await asyncio.wait_for(queue.get(), 5)
                assert received["type"] == "expense.created" and received["trip_id"] == 5
                await asyncio.to_thread(write, False)
                await asyncio.sleep(0.5)
                # One delivery for the commit (via PostgreSQL, not locally), none for the rollback.
                assert queue.empty()
        finally:
            engine.dispose()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(scenario())


def test_relay_reconnects_and_asks_subscribers_to_resync():
    async def scenario():
        target = TripEventBroker()
        target.bind(asyncio.get_running_loop())
        relay = PostgresRelay(listen_dsn(), target, retry=0.05)
        task = asyncio.create_task(relay.run())
        try:
            await wait_until(lambda: relay.connected)
            async with target.subscribe(1) as queue:
                await relay.disconnect()
                await wait_until(lambda: relay.connections == 2)
                assert await asyncio.wait_for(queue.get(), 5) == RESYNC
                event = TripEvent(1, "place", "created", 4, 2, 1).payload()
                await notify(event)
                assert await asyncio.wait_for(queue.get(), 5) == event
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(scenario())


def test_application_starts_and_stops_the_relay(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        relay = app.state.relay
        assert isinstance(relay, PostgresRelay)
        for _ in range(100):
            if relay.connected:
                break
            import time
            time.sleep(0.05)
        assert relay.connected and relay.channel == CHANNEL
        assert client.get("/health").status_code == 200
    assert not relay.connected
