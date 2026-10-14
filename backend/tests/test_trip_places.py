from datetime import datetime

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import OperationalError

from app.models import ItineraryItem, TripPlace
from test_api_contract import error_contract
from test_membership import TRIP, collaboration, invite


PREFIX = "/api/v1"
PLACE = {"name": " Senso-ji ", "latitude": 35.7148, "longitude": 139.7967}
FIELDS = {
    "id", "trip_id", "proposed_by_user_id", "name", "address", "latitude", "longitude",
    "provider", "provider_place_id", "note", "created_at", "updated_at",
}


@pytest.fixture
def shared(collaboration):
    client, _, _, users, _ = collaboration
    invitation = invite(collaboration)
    assert client.post(f"/invitations/{invitation['id']}/accept",
                       headers=users["bob"][1]).status_code == 200
    return collaboration


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def places_path(trip):
    return f"{PREFIX}/trips/{trip['id']}/places"


def add(context, actor="alice", trip=None, **fields):
    client, _, _, users, default_trip = context
    response = client.post(places_path(trip or default_trip), headers=users[actor][1],
                           json={**PLACE, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_member_crud_and_shared_editing(shared):
    client, _, _, users, trip = shared
    path = places_path(trip)
    ah, bh = users["alice"][1], users["bob"][1]
    assert client.get(path, headers=bh).json() == []
    place = add(shared, actor="bob", address=" 2-3-1 Asakusa ", note=" keep spaces ")
    assert set(place) == FIELDS
    assert place["trip_id"] == trip["id"]
    assert place["proposed_by_user_id"] == users["bob"][0]["id"]
    assert place["name"] == "Senso-ji" and place["address"] == "2-3-1 Asakusa"
    assert place["note"] == " keep spaces "
    assert place["provider"] == "manual" and place["provider_place_id"] is None
    # Coordinates are JSON numbers, not decimal strings.
    assert place["latitude"] == 35.7148 and place["longitude"] == 139.7967
    second = add(shared, name="Tokyo Tower", latitude=35.6586, longitude=139.7454)
    assert [p["id"] for p in client.get(path, headers=bh).json()] == [place["id"], second["id"]]
    assert client.get(f"{path}/{place['id']}", headers=ah).json() == place

    # The owner may edit another member's place, matching itinerary collaboration.
    response = client.patch(f"{path}/{place['id']}", headers=ah,
                            json={"name": " Asakusa Temple ", "address": None})
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Asakusa Temple" and updated["address"] is None
    assert updated["note"] == place["note"]
    assert updated["proposed_by_user_id"] == place["proposed_by_user_id"]
    assert updated["latitude"] == place["latitude"]
    assert updated["created_at"] == place["created_at"]
    assert instant(updated["updated_at"]) > instant(place["updated_at"])
    unchanged = client.patch(f"{path}/{place['id']}", headers=bh, json={})
    assert unchanged.status_code == 200 and unchanged.json()["name"] == "Asakusa Temple"

    assert client.delete(f"{path}/{place['id']}", headers=bh).status_code == 204
    error_contract(client.get(f"{path}/{place['id']}", headers=ah), 404, "PLACE_NOT_FOUND")
    error_contract(client.delete(f"{path}/{place['id']}", headers=ah), 404, "PLACE_NOT_FOUND")
    assert client.get(path, headers=ah).json() == [second]


def test_outsiders_and_pending_invitees_get_hidden_404(collaboration):
    client, conn, _, users, trip = collaboration
    place = add(collaboration)
    invite(collaboration, "charlie")
    bh = users["bob"][1]
    _, ch = users["charlie"]
    for headers in (bh, ch):
        for method, suffix, body in (
            ("POST", "", PLACE), ("GET", "", None), ("GET", f"/{place['id']}", None),
            ("PATCH", f"/{place['id']}", {"name": "Taken"}), ("DELETE", f"/{place['id']}", None),
        ):
            response = client.request(method, places_path(trip) + suffix, headers=headers, json=body)
            error_contract(response, 404, "TRIP_NOT_FOUND")
    error_contract(client.get(f"{PREFIX}/trips/2147483647/places", headers=users["alice"][1]),
                   404, "TRIP_NOT_FOUND")
    assert conn.scalar(select(func.count()).select_from(TripPlace)) == 1
    assert conn.scalar(select(TripPlace.name)) == "Senso-ji"


def test_place_ids_cannot_cross_trips(shared):
    client, conn, _, users, trip = shared
    ah = users["alice"][1]
    other_trip = client.post("/trips", headers=ah, json={**TRIP, "name": "Other"}).json()
    foreign = add(shared, trip=other_trip, name="Foreign")
    path = places_path(trip)
    # Alice can access both Trips, but IDs remain scoped to the Trip in the path.
    for method, body in (("GET", None), ("PATCH", {"name": "Hijacked"}), ("DELETE", None)):
        response = client.request(method, f"{path}/{foreign['id']}", headers=ah, json=body)
        error_contract(response, 404, "PLACE_NOT_FOUND")
    assert client.get(path, headers=ah).json() == []
    assert client.get(f"{places_path(other_trip)}/{foreign['id']}", headers=ah).json() == foreign


def test_places_have_no_legacy_alias(shared):
    client, _, _, users, trip = shared
    response = client.get(f"/trips/{trip['id']}/places", headers=users["alice"][1])
    assert response.status_code == 404


@pytest.mark.parametrize("latitude,longitude", [
    (-90, -180), (90, 180), (0, 0), (35, 139), (-33.868820, 151.209296), (1e-6, -1e-6),
])
def test_coordinate_boundaries_accepted(shared, latitude, longitude):
    place = add(shared, latitude=latitude, longitude=longitude)
    assert (place["latitude"], place["longitude"]) == (latitude, longitude)


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"name": "x" * 201}, {"name": None}, {"name": "bad\x00name"},
    {"address": ""}, {"address": "x" * 501}, {"note": "x" * 501},
    {"latitude": 90.000001}, {"latitude": -90.000001},
    {"longitude": 180.000001}, {"longitude": -180.000001},
    {"latitude": 35.1234567}, {"latitude": 1e-7},
    {"latitude": "35.1"}, {"latitude": True}, {"latitude": None}, {"longitude": [1]},
    {"provider": "nominatim"}, {"provider_place_id": "N1"}, {"proposed_by_user_id": 1},
    {"id": 1}, {"trip_id": 1}, {"created_at": "2027-01-01T00:00:00Z"},
])
def test_create_validation(shared, changes):
    client, conn, _, users, trip = shared
    body = {**PLACE, **changes}
    response = client.post(places_path(trip), headers=users["alice"][1], json=body)
    error_contract(response, 422, "VALIDATION_ERROR")
    assert conn.scalar(select(func.count()).select_from(TripPlace)) == 0


@pytest.mark.parametrize("field", ["name", "latitude", "longitude"])
def test_create_requires_fields(shared, field):
    client, _, _, users, trip = shared
    body = {key: value for key, value in PLACE.items() if key != field}
    error_contract(client.post(places_path(trip), headers=users["alice"][1], json=body),
                   422, "VALIDATION_ERROR")


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_numbers_rejected(shared, literal):
    client, conn, _, users, trip = shared
    content = '{"name": "x", "latitude": %s, "longitude": 1}' % literal
    response = client.post(places_path(trip), content=content,
                           headers={**users["alice"][1], "Content-Type": "application/json"})
    error_contract(response, 422, "VALIDATION_ERROR")
    assert conn.scalar(select(func.count()).select_from(TripPlace)) == 0


@pytest.mark.parametrize("changes", [
    {"latitude": 1}, {"longitude": 1}, {"name": None}, {"name": " "},
    {"provider": "nominatim"}, {"proposed_by_user_id": 1}, {"trip_id": 2},
])
def test_update_rejects_immutable_and_invalid_fields(shared, changes):
    client, _, _, users, trip = shared
    place = add(shared)
    path = f"{places_path(trip)}/{place['id']}"
    error_contract(client.patch(path, headers=users["alice"][1], json=changes),
                   422, "VALIDATION_ERROR")
    assert client.get(path, headers=users["alice"][1]).json() == place


def test_delete_linked_place_preserves_itinerary(shared):
    client, conn, _, users, trip = shared
    ah = users["alice"][1]
    place = add(shared)
    item = client.post(f"/trips/{trip['id']}/itinerary", headers=ah, json={
        "title": "Temple visit", "date": "2027-06-10", "location": "Original location",
    }).json()
    # No binding API exists yet; link through SQL to exercise the P1 foreign key.
    conn.execute(text("UPDATE itinerary_items SET place_id = :place WHERE id = :item"),
                 {"place": place["id"], "item": item["id"]})
    assert client.delete(f"{places_path(trip)}/{place['id']}", headers=ah).status_code == 204
    row = conn.execute(select(ItineraryItem.__table__)).mappings().one()
    assert row["place_id"] is None and row["location"] == "Original location"
    after = client.get(f"/trips/{trip['id']}/itinerary/{item['id']}", headers=ah)
    # The legacy itinerary response is unchanged, including its field set.
    assert after.status_code == 200 and after.json() == item


@pytest.mark.parametrize("method,suffix", [
    ("POST", ""), ("GET", ""), ("GET", "/{id}"), ("PATCH", "/{id}"), ("DELETE", "/{id}"),
])
def test_database_failure_is_safe_and_rolls_back(shared, method, suffix):
    client, conn, _, users, trip = shared
    place = add(shared)
    before = client.get(places_path(trip), headers=users["alice"][1]).json()

    def fail(connection, cursor, statement, parameters, context, executemany):
        if "trip_places" in statement:
            raise OperationalError("private SQL", {}, Exception("private detail"))

    event.listen(conn, "before_cursor_execute", fail)
    try:
        response = client.request(method, places_path(trip) + suffix.format(id=place["id"]),
                                  headers=users["alice"][1], json={**PLACE} if method == "POST"
                                  else {"name": "Changed"} if method == "PATCH" else None)
    finally:
        event.remove(conn, "before_cursor_execute", fail)
    error_contract(response, 503, "PLACES_UNAVAILABLE")
    assert "private" not in response.text
    assert client.get(places_path(trip), headers=users["alice"][1]).json() == before
