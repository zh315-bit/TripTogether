import pytest
from sqlalchemy import select

from app.models import ItineraryItem
from test_membership_concurrency import concurrent_client, simultaneous_requests


@pytest.fixture
def participants(concurrent_client):
    client, engine, factory, trip_id, alice_id, bob_id, ah, bh = concurrent_client
    invitation = client.post(f"/trips/{trip_id}/invitations", headers=ah,
                             json={"email": "bob@example.com"}).json()
    assert client.post(f"/invitations/{invitation['id']}/accept", headers=bh).status_code == 200
    return client, engine, factory, trip_id, ah, bh


def test_concurrent_creates_get_distinct_contiguous_positions(participants):
    client, engine, factory, trip_id, ah, bh = participants
    path = f"/trips/{trip_id}/itinerary"
    results = simultaneous_requests(engine, [
        lambda h=h: client.post(path, headers=h, json={"title": "Temple", "date": "2027-06-10"})
        for h in (ah, bh)
    ])
    assert [r.status_code for r in results] == [201, 201]
    assert sorted(r.json()["position"] for r in results) == [1, 2]
    with factory() as db:
        assert list(db.scalars(select(ItineraryItem.position).order_by(ItineraryItem.position))) == [1, 2]


def test_concurrent_patch_is_last_write_wins(participants):
    client, engine, _, trip_id, ah, bh = participants
    path = f"/trips/{trip_id}/itinerary"
    item = client.post(path, headers=ah, json={"title": "Original", "date": "2027-06-10"}).json()
    results = simultaneous_requests(engine, [
        lambda h=h, title=title: client.patch(f"{path}/{item['id']}", headers=h, json={"title": title})
        for h, title in ((ah, "Alice"), (bh, "Bob"))
    ])
    assert [r.status_code for r in results] == [200, 200]
    assert client.get(f"{path}/{item['id']}", headers=ah).json()["title"] in ("Alice", "Bob")


def test_concurrent_reorders_keep_one_complete_order(participants):
    client, engine, _, trip_id, ah, bh = participants
    path = f"/trips/{trip_id}/itinerary"
    ids = [client.post(path, headers=ah, json={"title": title, "date": "2027-06-10"}).json()["id"]
           for title in ("A", "B", "C")]
    orders = [ids[::-1], [ids[1], ids[2], ids[0]]]
    results = simultaneous_requests(engine, [
        lambda h=h, order=order: client.patch(path + "/reorder", headers=h,
                                             json={"date": "2027-06-10", "item_ids": order})
        for h, order in zip((ah, bh), orders)
    ])
    assert [r.status_code for r in results] == [200, 200]
    rows = client.get(path, headers=ah).json()
    assert [r["id"] for r in rows] in orders
    assert [r["position"] for r in rows] == [1, 2, 3]


def test_trip_shrink_racing_create_preserves_boundary(participants):
    client, engine, _, trip_id, ah, bh = participants
    path = f"/trips/{trip_id}"
    results = simultaneous_requests(engine, [
        lambda: client.patch(path, headers=ah, json={"end_date": "2027-06-12"}),
        lambda: client.post(path + "/itinerary", headers=bh,
                            json={"title": "Later", "date": "2027-06-14"}),
    ])
    assert [r.status_code for r in results] in ([200, 422], [409, 201])
    trip = client.get(path, headers=ah).json()
    assert all(trip["start_date"] <= item["date"] <= trip["end_date"]
               for item in client.get(path + "/itinerary", headers=ah).json())
