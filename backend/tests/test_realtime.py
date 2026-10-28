"""Live change notifications and optimistic concurrency (versions, If-Match, 412)."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import realtime
from app.api.events import event_stream
from app.realtime import TripEvent, TripEventBroker, broker, stage
from test_api_contract import error_contract
from test_expenses import BODY as EXPENSE
from test_itinerary import DAY, add, shared, collaboration, invite  # noqa: F401 fixtures
from test_trip_places import PLACE


# ---------------------------------------------------------------- broker unit tests

def test_broker_fans_out_per_trip_and_asks_slow_consumers_to_resync():
    async def scenario():
        hub = TripEventBroker()
        hub.bind(asyncio.get_running_loop())
        async with hub.subscribe(7) as seven, hub.subscribe(8) as eight:
            assert hub.subscribers(7) == 1
            hub.publish([TripEvent(7, "itinerary", "updated", 1, 5, 2, DAY)])
            got = await asyncio.wait_for(seven.get(), 1)
            assert got == {"type": "itinerary.updated", "trip_id": 7, "entity": "itinerary",
                           "action": "updated", "actor_id": 1, "entity_id": 5, "version": 2,
                           "date": DAY, "occurred_at": got["occurred_at"]}
            assert eight.empty()
            # More than the queue holds collapses into a single resync marker.
            hub.publish([TripEvent(7, "expense", "created", 1, i) for i in range(realtime.QUEUE_LIMIT + 5)])
            await asyncio.sleep(0)
            drained = []
            while not seven.empty():
                drained.append(seven.get_nowait())
            # The backlog is replaced by one resync marker; later events still follow it.
            assert drained[0] == realtime.RESYNC and len(drained) == 5
            assert drained[-1]["entity_id"] == realtime.QUEUE_LIMIT + 4
            # Deleting the trip delivers the event and then ends the stream.
            hub.publish([TripEvent(7, "trip", "deleted", 1, 7)])
            assert (await asyncio.wait_for(seven.get(), 1))["type"] == "trip.deleted"
            assert await asyncio.wait_for(seven.get(), 1) is None
        assert hub.subscribers(7) == 0 and hub.subscribers(8) == 0
        hub.close()
    asyncio.run(scenario())


def test_publish_without_a_bound_loop_is_a_safe_no_op():
    hub = TripEventBroker()
    hub.publish([TripEvent(1, "trip", "updated", 1, 1, 2)])
    hub.close()


def test_stream_generator_heartbeats_while_idle_and_relays_events():
    async def scenario():
        broker.bind(asyncio.get_running_loop())
        try:
            chunks = event_stream(3, 9, heartbeat=0.01)
            assert await chunks.__anext__() == 'event: ready\ndata: {"trip_id": 3, "user_id": 9}\n\n'
            assert await chunks.__anext__() == ": keep-alive\n\n"
            broker.publish([TripEvent(3, "place", "deleted", 9, 4)])
            chunk = await chunks.__anext__()
            assert chunk.startswith("event: place.deleted\ndata: ")
            assert json.loads(chunk.split("data: ", 1)[1])["entity_id"] == 4
            await chunks.aclose()
            assert broker.subscribers(3) == 0
        finally:
            broker.close()
    asyncio.run(scenario())


# ---------------------------------------------------------- staging follows the transaction

def test_staged_events_publish_after_commit_and_vanish_on_rollback(monkeypatch):
    published = []
    monkeypatch.setattr(broker, "publish", published.extend)
    # Only the Session hooks are under test here; no business table is touched.
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        stage(db, TripEvent(1, "trip", "updated", 1, 1, 2))
        db.rollback()
        assert published == []
        stage(db, TripEvent(1, "trip", "updated", 1, 1, 2))
        stage(db, TripEvent(1, "place", "created", 1, 4, 1))
        db.commit()
        assert [item.type for item in published] == ["trip.updated", "place.created"]
        db.commit()
        assert len(published) == 2
    engine.dispose()


# ------------------------------------------------------------------ versions and If-Match

def test_versions_etags_and_if_match_on_every_editable_resource(shared):
    client, _, _, users, trip = shared
    alice, ah = users["alice"]
    bob, bh = users["bob"]
    base = f"/api/v1/trips/{trip['id']}"
    item = add(shared)
    expense = client.post(f"{base}/expenses", headers=ah, json={
        **EXPENSE, "paid_by_user_id": alice["id"], "participant_user_ids": [alice["id"], bob["id"]],
    }).json()
    place = client.post(f"{base}/places", headers=ah, json=PLACE).json()
    assert item["version"] == expense["version"] == place["version"] == 1
    assert client.get(base, headers=ah).json()["version"] == 1

    for path, change, other in [
        (f"{base}/itinerary/{item['id']}", {"title": "Changed"}, {"title": "Other"}),
        (f"{base}/expenses/{expense['id']}", {"amount": "150.00"}, {"amount": "160.00"}),
        (f"{base}/places/{place['id']}", {"note": "Changed"}, {"note": "Other"}),
        (base, {"name": "Changed"}, {"name": "Other"}),
    ]:
        current = client.get(path, headers=ah)
        assert current.headers["etag"] == '"1"' and current.json()["version"] == 1
        saved = client.patch(path, headers={**ah, "If-Match": '"1"'}, json=change)
        assert saved.status_code == 200, saved.text
        assert saved.json()["version"] == 2 and saved.headers["etag"] == '"2"'
        # The same stale version from the owner answers 412 and changes nothing.
        stale = client.patch(path, headers={**ah, "If-Match": '"1"'}, json=other)
        error_contract(stale, 412, "STALE_VERSION")
        assert client.get(path, headers=ah).json() == saved.json()
        # Omitting the header or sending "*" keeps the previous last-write-wins behaviour.
        assert client.patch(path, headers=ah, json=other).json()["version"] == 3
        assert client.patch(path, headers={**ah, "If-Match": "*"}, json=change).json()["version"] == 4
        # A bare number is accepted; a weak tag or non-version is not.
        assert client.patch(path, headers={**ah, "If-Match": "4"}, json=other).status_code == 200
        for bad in ('W/"5"', "abc", "0", '"5" , "6"', '"99999999999"'):
            error_contract(client.patch(path, headers={**ah, "If-Match": bad}, json=change),
                           400, "INVALID_IF_MATCH")


def test_reorder_bumps_item_versions_so_a_stale_edit_is_refused(shared):
    client, _, _, users, trip = shared
    ah = users["alice"][1]
    base = f"/api/v1/trips/{trip['id']}/itinerary"
    first, second = add(shared, title="A"), add(shared, title="B")
    assert client.patch(f"{base}/reorder", headers=ah,
                        json={"date": DAY, "item_ids": [second["id"], first["id"]]}).status_code == 200
    moved = client.get(f"{base}/{first['id']}", headers=ah).json()
    assert moved["position"] == 2 and moved["version"] > 1
    error_contract(client.patch(f"{base}/{first['id']}", headers={**ah, "If-Match": '"1"'},
                                json={"title": "Stale"}), 412, "STALE_VERSION")


# -------------------------------------------------------------------- the SSE endpoint

def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        if lines[0].startswith(":"):
            continue
        assert lines[0].startswith("event: ") and lines[1].startswith("data: "), block
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    return events


def wait_for_subscriber(trip_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while broker.subscribers(trip_id) == 0:
        assert time.monotonic() < deadline, "the stream never subscribed"
        time.sleep(0.01)


def test_stream_requires_membership_and_rejects_anonymous(shared):
    client, _, _, users, trip = shared
    path = f"/api/v1/trips/{trip['id']}/events"
    error_contract(client.get(path, headers=users["charlie"][1]), 404, "TRIP_NOT_FOUND")
    error_contract(client.get(f"/api/v1/trips/{trip['id'] + 1}/events", headers=users["alice"][1]),
                   404, "TRIP_NOT_FOUND")
    error_contract(client.get(path), 401, "INVALID_CREDENTIALS")


def test_stream_delivers_committed_changes_and_ends_when_the_trip_is_deleted(shared):
    client, _, _, users, trip = shared
    alice, ah = users["alice"]
    bob, bh = users["bob"]
    base = f"/api/v1/trips/{trip['id']}"

    def collaborate():
        # Runs while the main thread holds the stream open; each call is its own request.
        wait_for_subscriber(trip["id"])
        created = client.post(f"{base}/itinerary", headers=bh, json={"title": "Temple", "date": DAY})
        rejected = client.patch(f"{base}/itinerary/{created.json()['id']}", headers={**ah, "If-Match": '"9"'},
                                json={"title": "Stale"})
        reordered = client.patch(f"{base}/itinerary/reorder", headers=ah,
                                 json={"date": DAY, "item_ids": [created.json()["id"]]})
        deleted = client.delete(base, headers=ah)
        return created.status_code, rejected.status_code, reordered.status_code, deleted.status_code, created.json()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(collaborate)
        response = client.get(f"{base}/events", headers=ah)
        created_status, rejected_status, reordered_status, deleted_status, item = future.result(timeout=20)

    assert (created_status, rejected_status, reordered_status, deleted_status) == (201, 412, 200, 204)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["ready", "itinerary.created", "itinerary.reordered", "trip.deleted"]
    assert events[0][1] == {"trip_id": trip["id"], "user_id": alice["id"]}
    assert events[1][1] == {"type": "itinerary.created", "trip_id": trip["id"], "entity": "itinerary",
                            "action": "created", "actor_id": bob["id"], "entity_id": item["id"],
                            "version": 1, "date": DAY, "occurred_at": events[1][1]["occurred_at"]}
    assert events[2][1]["actor_id"] == alice["id"] and events[2][1]["date"] == DAY
    assert events[3][1]["entity_id"] == trip["id"]
    assert broker.subscribers(trip["id"]) == 0


def test_rolled_back_writes_publish_nothing(shared):
    client, _, _, users, trip = shared
    ah = users["alice"][1]
    base = f"/api/v1/trips/{trip['id']}"

    def collaborate():
        wait_for_subscriber(trip["id"])
        # Rejected before commit: a date outside the trip, then a stale version.
        outside = client.post(f"{base}/itinerary", headers=ah, json={"title": "X", "date": "2030-01-01"})
        place = client.post(f"{base}/places", headers=ah, json=PLACE)
        stale = client.patch(f"{base}/places/{place.json()['id']}", headers={**ah, "If-Match": '"7"'},
                             json={"note": "no"})
        deleted = client.delete(base, headers=ah)
        return outside.status_code, place.status_code, stale.status_code, deleted.status_code

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(collaborate)
        response = client.get(f"{base}/events", headers=ah)
        assert future.result(timeout=20) == (422, 201, 412, 204)
    assert [name for name, _ in parse_sse(response.text)] == ["ready", "place.created", "trip.deleted"]
