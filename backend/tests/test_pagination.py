"""List routes accept optional limit/offset and always report X-Total-Count."""
import pytest

from test_expenses import BODY
from test_membership import collaboration, invite


@pytest.fixture
def filled(collaboration):
    client, _, _, users, trip = collaboration
    ah = users["alice"][1]
    invitation = invite(collaboration)
    assert client.post(f"/invitations/{invitation['id']}/accept", headers=users["bob"][1]).status_code == 200
    base = f"/api/v1/trips/{trip['id']}"
    for index in range(5):
        assert client.post(f"{base}/itinerary", headers=ah, json={
            "title": f"Stop {index}", "date": "2027-06-10", "location": None,
            "start_time": None, "end_time": None, "notes": None, "place_id": None}).status_code == 201
        assert client.post(f"{base}/places", headers=ah, json={
            "name": f"Place {index}", "latitude": 35.0 + index, "longitude": 139.0}).status_code == 201
        assert client.post(f"{base}/expenses", headers=ah, json={
            **BODY, "description": f"Expense {index}", "expense_date": f"2027-06-1{index}",
            "paid_by_user_id": users["alice"][0]["id"],
            "participant_user_ids": [users["alice"][0]["id"], users["bob"][0]["id"]]}).status_code == 201
    for index in range(2):
        assert client.post("/api/v1/trips", headers=ah, json={
            "name": f"Other {index}", "destination": "X", "start_date": "2027-07-01", "end_date": "2027-07-02",
        }).status_code == 201
    return client, ah, base


@pytest.mark.parametrize("suffix,label", [
    ("/itinerary", "title"), ("/places", "name"), ("/expenses", "description"),
])
def test_trip_lists_page_in_their_natural_order(filled, suffix, label):
    client, ah, base = filled
    everything = client.get(base + suffix, headers=ah)
    assert everything.status_code == 200 and everything.headers["X-Total-Count"] == "5"
    names = [row[label] for row in everything.json()]
    page = client.get(f"{base}{suffix}?limit=2&offset=1", headers=ah)
    assert page.status_code == 200 and page.headers["X-Total-Count"] == "5"
    assert [row[label] for row in page.json()] == names[1:3]
    tail = client.get(f"{base}{suffix}?offset=4", headers=ah)
    assert [row[label] for row in tail.json()] == names[4:] and tail.headers["X-Total-Count"] == "5"
    beyond = client.get(f"{base}{suffix}?limit=5&offset=50", headers=ah)
    assert beyond.json() == [] and beyond.headers["X-Total-Count"] == "5"


def test_trip_collection_pages_too(filled):
    client, ah, _ = filled
    first = client.get("/api/v1/trips?limit=1", headers=ah)
    assert first.status_code == 200 and len(first.json()) == 1 and first.headers["X-Total-Count"] == "3"
    rest = client.get("/api/v1/trips?offset=1", headers=ah)
    assert [t["name"] for t in rest.json()] == ["Other 0", "Other 1"]


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1", "limit=abc", "limit=1.5"])
def test_bad_page_params_are_422(filled, query):
    client, ah, base = filled
    response = client.get(f"{base}/expenses?{query}", headers=ah)
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"][0]["loc"][0] == "query"


def test_expense_pages_keep_their_splits(filled):
    client, ah, base = filled
    page = client.get(f"{base}/expenses?limit=2", headers=ah).json()
    assert all(len(row["splits"]) == 2 for row in page)
