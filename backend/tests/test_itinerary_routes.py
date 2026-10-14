import pytest
from sqlalchemy import select

from app.models import ItineraryItem
from test_api_contract import error_contract
from test_membership import TRIP, collaboration, invite
from test_itinerary import shared


PREFIX = "/api/v1"
DAY = "2027-06-10"


def api(trip):
    return f"{PREFIX}/trips/{trip['id']}"


def place(context, name, offset, actor="alice", trip=None):
    """Places on one east-west line, `offset` hundredths of a degree apart."""
    client, _, _, users, default_trip = context
    response = client.post(api(trip or default_trip) + "/places", headers=users[actor][1], json={
        "name": name, "latitude": 35.0, "longitude": round(139.0 + 0.01 * offset, 6),
    })
    assert response.status_code == 201, response.text
    return response.json()


def item(context, title, place_id=None, actor="alice", day=DAY, **fields):
    client, _, _, users, trip = context
    body = {"title": title, "date": day, **fields}
    if place_id is not None:
        body["place_id"] = place_id
    response = client.post(api(trip) + "/itinerary", headers=users[actor][1], json=body)
    assert response.status_code == 201, response.text
    return response.json()


def zigzag(context):
    """Hotel at 0, then stops at 3, 1, 4, 2: the shortest walk is 0-1-2-3-4."""
    return [item(context, f"Stop {offset}", place(context, f"P{offset}", offset)["id"])
            for offset in (0, 3, 1, 4, 2)]


def day_ids(context):
    client, _, _, users, trip = context
    return [row["id"] for row in client.get(api(trip) + "/itinerary", headers=users["alice"][1]).json()]


# ---- Binding places to itinerary items -----------------------------------

def test_place_binding_snapshot_and_unlink(shared):
    client, _, _, users, trip = shared
    bh = users["bob"][1]
    temple = place(shared, "Senso-ji", 0, actor="bob")
    linked = item(shared, "Morning", temple["id"], actor="bob")
    assert linked["place_id"] == temple["id"] and linked["location"] == "Senso-ji"
    explicit = item(shared, "Lunch", temple["id"], location="Near the gate")
    assert explicit["location"] == "Near the gate"
    assert item(shared, "Free time")["place_id"] is None
    # Renaming the place does not rewrite the location snapshot.
    client.patch(f"{api(trip)}/places/{temple['id']}", headers=bh, json={"name": "Asakusa Temple"})
    path = f"{api(trip)}/itinerary/{linked['id']}"
    assert client.get(path, headers=bh).json()["location"] == "Senso-ji"
    unlinked = client.patch(path, headers=bh, json={"place_id": None})
    assert unlinked.status_code == 200
    assert unlinked.json()["place_id"] is None and unlinked.json()["location"] == "Senso-ji"
    relinked = client.patch(path, headers=bh, json={"place_id": temple["id"]})
    assert relinked.json()["place_id"] == temple["id"]
    # Legacy paths share the schema, so they see the additive field too.
    assert client.get(f"/trips/{trip['id']}/itinerary/{linked['id']}", headers=bh).json()["place_id"] == temple["id"]


def test_place_from_another_trip_is_rejected(shared):
    client, conn, _, users, trip = shared
    ah = users["alice"][1]
    other = client.post("/trips", headers=ah, json={**TRIP, "name": "Other"}).json()
    foreign = place(shared, "Foreign", 0, trip=other)
    own = item(shared, "Mine")
    for response in (
        client.post(api(trip) + "/itinerary", headers=ah,
                    json={"title": "x", "date": DAY, "place_id": foreign["id"]}),
        client.post(api(trip) + "/itinerary", headers=ah,
                    json={"title": "x", "date": DAY, "place_id": 2147483647}),
        client.patch(f"{api(trip)}/itinerary/{own['id']}", headers=ah, json={"place_id": foreign["id"]}),
    ):
        body = error_contract(response, 422, "VALIDATION_ERROR")
        assert "place in this trip" in body["details"][0]["msg"]
    assert conn.scalar(select(ItineraryItem.place_id).where(ItineraryItem.id == own["id"])) is None


def test_switching_place_refreshes_location_unless_sent(shared):
    client, _, _, users, trip = shared
    ah = users["alice"][1]
    first = place(shared, "Senso-ji", 0)
    second = place(shared, "Tokyo Tower", 1)
    third = place(shared, "Shibuya", 2)
    linked = item(shared, "Visit", first["id"])
    path = f"{api(trip)}/itinerary/{linked['id']}"
    # Another place, no location in the request: location follows the new place.
    switched = client.patch(path, headers=ah, json={"place_id": second["id"]}).json()
    assert switched["place_id"] == second["id"] and switched["location"] == "Tokyo Tower"
    # Re-sending the same place keeps a hand-edited location.
    client.patch(path, headers=ah, json={"location": "Observation deck"})
    same = client.patch(path, headers=ah, json={"place_id": second["id"]}).json()
    assert same["location"] == "Observation deck"
    # An explicit location in the same request wins, including null.
    explicit = client.patch(path, headers=ah, json={"place_id": third["id"], "location": "Scramble"}).json()
    assert explicit["place_id"] == third["id"] and explicit["location"] == "Scramble"
    cleared = client.patch(path, headers=ah, json={"place_id": first["id"], "location": None}).json()
    assert cleared["place_id"] == first["id"] and cleared["location"] is None
    # Unlinking keeps the location; linking a previously unlinked item fills it.
    client.patch(path, headers=ah, json={"location": "Kept"})
    unlinked = client.patch(path, headers=ah, json={"place_id": None}).json()
    assert unlinked["place_id"] is None and unlinked["location"] == "Kept"
    relinked = client.patch(path, headers=ah, json={"place_id": second["id"]}).json()
    assert relinked["location"] == "Tokyo Tower"


@pytest.mark.parametrize("value", [0, -1, "1", True, 1.5, 2147483648])
def test_place_id_is_strict(shared, value):
    client, _, _, users, trip = shared
    error_contract(client.post(api(trip) + "/itinerary", headers=users["alice"][1],
                               json={"title": "x", "date": DAY, "place_id": value}),
                   422, "VALIDATION_ERROR")


# ---- Day route -----------------------------------------------------------

def test_route_legs_skip_unlocated_items(shared):
    client, _, _, users, trip = shared
    a = place(shared, "A", 0)
    b = place(shared, "B", 2)
    first = item(shared, "A", a["id"])
    free = item(shared, "Free time")
    second = item(shared, "B", b["id"])
    item(shared, "Elsewhere", a["id"], day="2027-06-11")
    response = client.get(api(trip) + "/itinerary/route", headers=users["bob"][1], params={"date": DAY})
    assert response.status_code == 200
    route = response.json()
    assert route["date"] == DAY and route["unlocated_item_ids"] == [free["id"]]
    assert [stop["item_id"] for stop in route["stops"]] == [first["id"], second["id"]]
    assert route["stops"][0] == {"item_id": first["id"], "place_id": a["id"], "name": "A",
                                 "latitude": 35.0, "longitude": 139.0}
    leg, = route["legs"]
    assert (leg["from_item_id"], leg["to_item_id"]) == (first["id"], second["id"])
    # 0.02 degrees of longitude at 35°N is about 1.82 km in a straight line.
    assert leg["distance_km"] == pytest.approx(1.822, abs=0.002)
    assert route["total_distance_km"] == leg["distance_km"]


def test_route_empty_and_single_stop(shared):
    client, _, _, users, trip = shared
    ah = users["alice"][1]
    empty = client.get(api(trip) + "/itinerary/route", headers=ah, params={"date": DAY}).json()
    assert empty == {"date": DAY, "stops": [], "legs": [], "total_distance_km": 0.0, "unlocated_item_ids": []}
    item(shared, "Only", place(shared, "Only", 0)["id"])
    single = client.get(api(trip) + "/itinerary/route", headers=ah, params={"date": DAY}).json()
    assert len(single["stops"]) == 1 and single["legs"] == [] and single["total_distance_km"] == 0.0


@pytest.mark.parametrize("params", [{}, {"date": "2027-06-30"}, {"date": "June 10"}])
def test_route_validates_date(shared, params):
    client, _, _, users, trip = shared
    error_contract(client.get(api(trip) + "/itinerary/route", headers=users["alice"][1], params=params),
                   422, "VALIDATION_ERROR")


def test_route_and_optimize_hide_other_trips(collaboration):
    client, _, _, users, trip = collaboration
    invite(collaboration, "charlie")
    for name in ("bob", "charlie"):
        headers = users[name][1]
        error_contract(client.get(api(trip) + "/itinerary/route", headers=headers, params={"date": DAY}),
                       404, "TRIP_NOT_FOUND")
        error_contract(client.post(api(trip) + "/itinerary/optimize", headers=headers, json={"date": DAY}),
                       404, "TRIP_NOT_FOUND")


def test_new_routes_are_versioned_only_and_not_shadowed(shared):
    client, _, _, users, trip = shared
    ah = users["alice"][1]
    # /route must not be captured by GET /{item_id} (which would 422 on "route").
    assert client.get(api(trip) + "/itinerary/route", headers=ah, params={"date": DAY}).status_code == 200
    assert client.get(f"/trips/{trip['id']}/itinerary/route", headers=ah,
                      params={"date": DAY}).status_code == 422
    assert client.post(f"/trips/{trip['id']}/itinerary/optimize", headers=ah,
                       json={"date": DAY}).status_code == 405


# ---- Optimize preview ----------------------------------------------------

def test_optimize_previews_without_writing(shared):
    client, conn, _, users, trip = shared
    stops = zigzag(shared)
    ids = [stop["id"] for stop in stops]
    before = conn.execute(select(ItineraryItem.__table__).order_by(ItineraryItem.id)).mappings().all()
    response = client.post(api(trip) + "/itinerary/optimize", headers=users["bob"][1], json={"date": DAY})
    assert response.status_code == 200
    plan = response.json()
    assert plan["changed"] is True and plan["keep_first"] is True
    assert plan["original_item_ids"] == ids
    assert plan["proposed_item_ids"] == [ids[0], ids[2], ids[4], ids[1], ids[3]]
    assert plan["anchored_item_ids"] == [ids[0]]
    assert plan["proposed_route"]["total_distance_km"] < plan["original_route"]["total_distance_km"]
    assert [s["item_id"] for s in plan["proposed_route"]["stops"]] == plan["proposed_item_ids"]
    # Nothing was saved: rows, positions and timestamps are untouched.
    assert conn.execute(select(ItineraryItem.__table__).order_by(ItineraryItem.id)).mappings().all() == before


def test_optimize_keeps_timed_and_unlocated_items_in_place(shared):
    client, _, _, users, trip = shared
    hotel = item(shared, "Hotel", place(shared, "Hotel", 0)["id"])
    far = item(shared, "Far", place(shared, "Far", 3)["id"])
    timed = item(shared, "Booked lunch", place(shared, "Lunch", 1)["id"], start_time="12:00")
    near = item(shared, "Near", place(shared, "Near", 2)["id"])
    rest = item(shared, "Rest")
    plan = client.post(api(trip) + "/itinerary/optimize", headers=users["alice"][1],
                       json={"date": DAY}).json()
    assert plan["anchored_item_ids"] == [hotel["id"], timed["id"], rest["id"]]
    proposed = plan["proposed_item_ids"]
    assert proposed.index(timed["id"]) == 2 and proposed.index(rest["id"]) == 4
    assert proposed[0] == hotel["id"] and proposed[1] == far["id"] and proposed[3] == near["id"]
    assert plan["changed"] is False and proposed == plan["original_item_ids"]


def test_keep_first_false_lets_the_first_item_move(shared):
    client, _, _, users, trip = shared
    ids = [item(shared, f"S{o}", place(shared, f"P{o}", o)["id"])["id"] for o in (2, 0, 1, 3)]
    plan = client.post(api(trip) + "/itinerary/optimize", headers=users["alice"][1],
                       json={"date": DAY, "keep_first": False}).json()
    assert plan["anchored_item_ids"] == [] and plan["changed"] is True
    assert plan["proposed_item_ids"] in ([ids[1], ids[2], ids[0], ids[3]], [ids[3], ids[0], ids[2], ids[1]])


def test_optimize_is_capped(shared):
    client, _, _, users, trip = shared
    for index in range(51):
        item(shared, f"Item {index}")
    body = error_contract(client.post(api(trip) + "/itinerary/optimize", headers=users["alice"][1],
                                      json={"date": DAY}), 422, "VALIDATION_ERROR")
    assert "at most 50" in body["details"][0]["msg"]


@pytest.mark.parametrize("body", [
    {}, {"date": "2027-06-30"}, {"date": DAY, "keep_first": "yes"}, {"date": DAY, "extra": 1},
])
def test_optimize_validation(shared, body):
    client, _, _, users, trip = shared
    error_contract(client.post(api(trip) + "/itinerary/optimize", headers=users["alice"][1], json=body),
                   422, "VALIDATION_ERROR")


# ---- Guarded reorder -----------------------------------------------------

def test_apply_preview_with_expected_order(shared):
    client, _, _, users, trip = shared
    zigzag(shared)
    bh = users["bob"][1]
    plan = client.post(api(trip) + "/itinerary/optimize", headers=bh, json={"date": DAY}).json()
    body = {"date": DAY, "item_ids": plan["proposed_item_ids"], "expected_item_ids": plan["original_item_ids"]}
    applied = client.patch(api(trip) + "/itinerary/reorder", headers=bh, json=body)
    assert applied.status_code == 200
    assert [row["id"] for row in applied.json()] == plan["proposed_item_ids"]
    # A duplicate submit (double click, retry) is idempotent rather than a conflict.
    again = client.patch(api(trip) + "/itinerary/reorder", headers=bh, json=body)
    assert again.status_code == 200 and again.json() == applied.json()
    route = client.get(api(trip) + "/itinerary/route", headers=bh, params={"date": DAY}).json()
    assert route["total_distance_km"] == plan["proposed_route"]["total_distance_km"]
    rerun = client.post(api(trip) + "/itinerary/optimize", headers=bh, json={"date": DAY}).json()
    assert rerun["changed"] is False


def test_stale_preview_conflicts_without_writing(shared):
    client, _, _, users, trip = shared
    ah, bh = users["alice"][1], users["bob"][1]
    ids = [stop["id"] for stop in zigzag(shared)]
    plan = client.post(api(trip) + "/itinerary/optimize", headers=bh, json={"date": DAY}).json()
    # Alice reorders after Bob's preview, with the same set of items.
    alice_order = [ids[0], ids[4], ids[3], ids[2], ids[1]]
    assert client.patch(api(trip) + "/itinerary/reorder", headers=ah,
                        json={"date": DAY, "item_ids": alice_order}).status_code == 200
    stale = client.patch(api(trip) + "/itinerary/reorder", headers=bh, json={
        "date": DAY, "item_ids": plan["proposed_item_ids"], "expected_item_ids": plan["original_item_ids"],
    })
    error_contract(stale, 409, "ITINERARY_CONFLICT")
    assert day_ids(shared) == alice_order


def test_added_item_after_preview_conflicts(shared):
    client, _, _, users, trip = shared
    zigzag(shared)
    bh = users["bob"][1]
    plan = client.post(api(trip) + "/itinerary/optimize", headers=bh, json={"date": DAY}).json()
    item(shared, "Added later")
    error_contract(client.patch(api(trip) + "/itinerary/reorder", headers=bh, json={
        "date": DAY, "item_ids": plan["proposed_item_ids"], "expected_item_ids": plan["original_item_ids"],
    }), 409, "ITINERARY_CONFLICT")


def test_reorder_without_expected_is_unchanged(shared):
    client, _, _, users, trip = shared
    ids = [stop["id"] for stop in zigzag(shared)]
    reordered = ids[::-1]
    response = client.patch(api(trip) + "/itinerary/reorder", headers=users["alice"][1],
                            json={"date": DAY, "item_ids": reordered})
    assert response.status_code == 200 and day_ids(shared) == reordered
    # Incomplete sets remain 422, as before.
    error_contract(client.patch(api(trip) + "/itinerary/reorder", headers=users["alice"][1],
                                json={"date": DAY, "item_ids": ids[:2]}), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("expected", [[1, 1], ["1"], [0], [True]])
def test_expected_ids_are_strict(shared, expected):
    client, _, _, users, trip = shared
    error_contract(client.patch(api(trip) + "/itinerary/reorder", headers=users["alice"][1],
                                json={"date": DAY, "item_ids": [], "expected_item_ids": expected}),
                   422, "VALIDATION_ERROR")
