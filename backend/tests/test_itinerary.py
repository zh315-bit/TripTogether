from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import ItineraryItem, TripInvitation, TripMember, User
from app.schemas.itinerary import ItineraryItemCreate, ItineraryItemUpdate, ItineraryReorderRequest
from test_membership import TRIP, collaboration, invite


DAY = "2027-06-10"
BODY = {"title": " Senso-ji ", "date": DAY}
ROUTES = [
    ("POST", "", BODY), ("GET", "", None), ("GET", "/1", None),
    ("PATCH", "/1", {"title": "Changed"}), ("DELETE", "/1", None),
    ("PATCH", "/reorder", {"date": DAY, "item_ids": []}),
]


@pytest.fixture
def shared(collaboration):
    client, _, _, users, _ = collaboration
    invitation = invite(collaboration)
    assert client.post(f"/invitations/{invitation['id']}/accept",
                       headers=users["bob"][1]).status_code == 200
    return collaboration


def add(context, title="Senso-ji", day=DAY, actor="alice", **fields):
    client, _, _, users, trip = context
    response = client.post(f"/trips/{trip['id']}/itinerary", headers=users[actor][1],
                           json={"title": title, "date": day, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_shared_editing_and_creator_is_not_owner(shared):
    client, conn, _, users, trip = shared
    path = f"/trips/{trip['id']}/itinerary"
    first = add(shared)
    assert first["created_by_user_id"] == users["alice"][0]["id"]
    assert first["position"] == 1
    bh, ah = users["bob"][1], users["alice"][1]
    assert client.get(path, headers=bh).json() == [first]
    updated = client.patch(f"{path}/{first['id']}", headers=bh, json={
        "title": "Temple", "notes": "Meet at gate", "start_time": "09:30", "end_time": "10:00",
    })
    assert updated.status_code == 200
    updated = updated.json()
    assert updated["created_by_user_id"] == first["created_by_user_id"]
    assert updated["created_at"] == first["created_at"]
    assert updated["updated_at"] > first["updated_at"]
    assert client.get(f"{path}/{first['id']}", headers=ah).json() == updated
    second = add(shared, actor="bob", title="Lunch")
    assert second["created_by_user_id"] == users["bob"][0]["id"]
    assert client.patch(f"{path}/{second['id']}", headers=ah,
                        json={"notes": "Alice edited Bob's item"}).status_code == 200
    assert client.delete(f"{path}/{first['id']}", headers=bh).status_code == 204
    assert conn.scalar(select(ItineraryItem.id).where(ItineraryItem.id == first["id"])) is None
    assert client.get(path, headers=ah).json()[0]["position"] == 1
    for method, suffix, body in [
        ("PATCH", "", {"name": "No"}), ("DELETE", "", None),
        ("POST", "/invitations", {"email": "charlie@example.com"}),
    ]:
        assert client.request(method, f"/trips/{trip['id']}{suffix}",
                              headers=bh, json=body).status_code == 404


@pytest.mark.parametrize("method,suffix,body", ROUTES)
def test_other_and_pending_member_denied(collaboration, method, suffix, body):
    client, _, _, users, trip = collaboration
    add(collaboration)
    invite(collaboration)
    for name in ("bob", "charlie"):
        response = client.request(method, f"/trips/{trip['id']}/itinerary{suffix}",
                                  json=body, headers=users[name][1])
        assert response.status_code == 404


@pytest.mark.parametrize("method,suffix,body", ROUTES)
def test_anonymous_denied_without_database(method, suffix, body):
    def no_db():
        raise AssertionError("Anonymous request accessed DB")
    app.dependency_overrides[get_db] = no_db
    try:
        with TestClient(app) as client:
            assert client.request(method, "/trips/1/itinerary" + suffix,
                                  json=body).status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("field,value", [
    ("title", ""), ("title", " \t "), ("title", "x" * 161), ("title", None),
    ("title", "\x00"), ("notes", "\ud800"), ("notes", "x" * 2001),
    ("location", "x" * 201), ("date", "2027-02-30"), ("date", 1800000000),
    ("date", "2027-06-10T00:00:00"), ("start_time", "09:30Z"),
    ("start_time", "09:30+09:00"), ("start_time", 100), ("start_time", "24:00"),
    ("position", 999), ("trip_id", 1), ("id", 1), ("created_by_user_id", 2),
    ("created_at", "2027-06-10"), ("updated_at", "2027-06-10"),
])
def test_strict_inputs(field, value):
    with pytest.raises(ValidationError):
        ItineraryItemCreate(**{**BODY, field: value})
    with pytest.raises(ValidationError):
        ItineraryItemUpdate(**{field: value})


@pytest.mark.parametrize("fields,valid", [
    ({}, True), ({"start_time": "09:30"}, True),
    ({"start_time": "09:30", "end_time": "09:30"}, True),
    ({"start_time": "09:30", "end_time": "10:00"}, True),
    ({"end_time": "10:00"}, False),
    ({"start_time": "23:00", "end_time": "01:00"}, False),
])
def test_create_time_rules(fields, valid):
    if valid:
        assert ItineraryItemCreate(**BODY, **fields).title == "Senso-ji"
    else:
        with pytest.raises(ValidationError):
            ItineraryItemCreate(**BODY, **fields)


@pytest.mark.parametrize("day,status", [
    ("2027-06-09", 422), (DAY, 201), ("2027-06-20", 201), ("2027-06-21", 422),
])
def test_trip_date_boundaries(collaboration, day, status):
    client, _, _, users, trip = collaboration
    assert client.post(f"/trips/{trip['id']}/itinerary", headers=users["alice"][1],
                       json={**BODY, "date": day}).status_code == status


def test_patch_merges_time_and_can_clear_nullable_fields(shared):
    client, _, _, users, trip = shared
    item = add(shared, start_time="09:00", end_time="10:00", notes="hi", location="Tokyo")
    path = f"/trips/{trip['id']}/itinerary/{item['id']}"
    headers = users["bob"][1]
    for changes in ({"start_time": "11:00"}, {"start_time": None},
                    {"date": "2027-06-21"}, {"title": None}, {"date": None}):
        assert client.patch(path, headers=headers, json=changes).status_code == 422
        assert client.get(path, headers=headers).json() == item
    assert client.patch(path, headers=headers, json={}).json() == item
    result = client.patch(path, headers=headers, json={
        "start_time": None, "end_time": None, "notes": None, "location": None,
    })
    assert result.status_code == 200
    assert all(result.json()[field] is None for field in ("start_time", "end_time", "notes", "location"))


def test_reorder_compact_move_and_sql_order(shared):
    client, _, _, users, trip = shared
    path = f"/trips/{trip['id']}/itinerary"
    ah, bh = users["alice"][1], users["bob"][1]
    later = add(shared, "Later", "2027-06-11")
    a, b, c = [add(shared, title) for title in ("A", "B", "C")]
    assert [i["position"] for i in (a, b, c)] == [1, 2, 3]
    order = [c["id"], a["id"], b["id"]]
    response = client.patch(path + "/reorder", headers=bh, json={"date": DAY, "item_ids": order})
    assert response.status_code == 200
    assert [i["id"] for i in response.json()] == order
    assert [i["position"] for i in response.json()] == [1, 2, 3]
    assert [i["id"] for i in client.get(path, headers=ah).json()] == order + [later["id"]]
    assert client.delete(f"{path}/{a['id']}", headers=bh).status_code == 204
    moved = client.patch(f"{path}/{c['id']}", headers=bh, json={"date": "2027-06-11"})
    assert moved.status_code == 200 and moved.json()["position"] == 2
    assert [(i["id"], i["position"]) for i in client.get(path, headers=ah).json()] == [
        (b["id"], 1), (later["id"], 1), (c["id"], 2),
    ]


def test_invalid_reorders_and_cross_trip_item_ids(shared):
    client, _, _, users, trip = shared
    ah = users["alice"][1]
    path = f"/trips/{trip['id']}/itinerary"
    a, b = add(shared), add(shared, "B")
    other_day = add(shared, "Next", "2027-06-11")
    other_trip = client.post("/trips", headers=ah, json=TRIP).json()
    foreign = client.post(f"/trips/{other_trip['id']}/itinerary", headers=ah, json=BODY).json()
    original = client.get(path, headers=ah).json()
    for ids in ([a["id"], a["id"]], [a["id"]], [], [a["id"], foreign["id"]],
                [a["id"], other_day["id"]], [a["id"], 2147483647]):
        assert client.patch(path + "/reorder", headers=ah,
                            json={"date": DAY, "item_ids": ids}).status_code == 422
        assert client.get(path, headers=ah).json() == original
    for method, body in (("GET", None), ("PATCH", {"title": "No"}), ("DELETE", None)):
        assert client.request(method, f"{path}/{foreign['id']}", headers=ah, json=body).status_code == 404
    assert client.patch(path + "/reorder", headers=ah,
                        json={"date": "2027-06-12", "item_ids": []}).json() == []


def test_trip_shrink_and_cascade(shared):
    client, conn, _, users, trip = shared
    ah = users["alice"][1]
    add(shared, day="2027-06-14")
    for changes in ({"end_date": "2027-06-12"}, {"start_date": "2027-06-15"}):
        assert client.patch(f"/trips/{trip['id']}", headers=ah, json=changes).status_code == 409
        assert client.get(f"/trips/{trip['id']}", headers=ah).json() == trip
    assert client.patch(f"/trips/{trip['id']}", headers=ah,
                        json={"start_date": "2027-06-14", "end_date": "2027-06-14"}).status_code == 200
    assert client.delete(f"/trips/{trip['id']}", headers=ah).status_code == 204
    for model in (ItineraryItem, TripMember, TripInvitation):
        assert conn.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("operation", ["reorder", "delete", "move"])
def test_ordering_failure_rolls_back_all_writes(shared, operation):
    client, conn, _, users, trip = shared
    a, b, c = [add(shared, title) for title in ("A", "B", "C")]
    path = f"/trips/{trip['id']}/itinerary"
    ah = users["alice"][1]
    original = client.get(path, headers=ah).json()
    updates = []

    def fail_later(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE itinerary_items"):
            updates.append(statement)
            if len(updates) == 2:
                raise OperationalError("private SQL", {}, Exception("private detail"))

    event.listen(conn, "before_cursor_execute", fail_later)
    try:
        if operation == "reorder":
            response = client.patch(path + "/reorder", headers=ah,
                                    json={"date": DAY, "item_ids": [c["id"], a["id"], b["id"]]})
        elif operation == "delete":
            response = client.delete(f"{path}/{a['id']}", headers=ah)
        else:
            response = client.patch(f"{path}/{a['id']}", headers=ah, json={"date": "2027-06-11"})
    finally:
        event.remove(conn, "before_cursor_execute", fail_later)
    assert len(updates) == 2
    assert response.status_code == 503 and "private" not in response.text
    assert client.get(path, headers=ah).json() == original


@pytest.mark.parametrize("method,suffix,body", ROUTES)
def test_safe_db_errors(method, suffix, body):
    db = MagicMock(spec=Session)
    db.scalar.side_effect = OperationalError("secret SQL", {}, Exception("secret"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(id=1)
    try:
        with TestClient(app) as client:
            response = client.request(method, "/trips/1/itinerary" + suffix, json=body)
        assert response.status_code == 503 and "secret" not in response.text
        db.rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("ids", [[1, 1], [True], ["1"], [0], [2147483648]])
def test_reorder_ids_are_strict(ids):
    with pytest.raises(ValidationError):
        ItineraryReorderRequest(date=DAY, item_ids=ids)
