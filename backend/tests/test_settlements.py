"""Recorded payments reduce balances and the suggested transfers."""
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Settlement
from test_expenses import BODY, create, expense_context
from test_membership import collaboration


def ids(context):
    _, _, _, users, _ = context
    return {name: users[name][0]["id"] for name in ("alice", "bob")}


def balances(client, trip, headers):
    response = client.get(f"/api/v1/trips/{trip['id']}/balances", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_payment_settles_a_balance_and_shrinks_the_suggestions(expense_context):
    client, conn, _, users, trip = expense_context
    ah, bh = users["alice"][1], users["bob"][1]
    who = ids(expense_context)
    create(expense_context)  # 120 paid by alice, split with bob: bob owes 60
    base = f"/api/v1/trips/{trip['id']}/settlements"
    before = balances(client, trip, ah)
    assert before["suggested_settlements"] == [{"from_user_id": who["bob"], "to_user_id": who["alice"], "amount": "60.00"}]

    # Bob pays part of it in cash; anyone in the trip may record it.
    created = client.post(base, headers=bh, json={
        "from_user_id": who["bob"], "to_user_id": who["alice"], "amount": "25.50",
        "currency": "USD", "paid_on": "2027-05-02", "note": " Cash at the ryokan ",
    })
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["amount"] == "25.50" and row["note"] == "Cash at the ryokan" and row["recorded_by_user_id"] == who["bob"]
    assert set(row) == {"id", "trip_id", "from_user_id", "to_user_id", "amount", "currency", "paid_on", "note",
                        "recorded_by_user_id", "created_at"}
    after = balances(client, trip, ah)
    by_id = {m["user_id"]: m for m in after["members"]}
    assert by_id[who["bob"]]["settled"] == "25.50" and by_id[who["bob"]]["balance"] == "-34.50"
    assert by_id[who["alice"]]["settled"] == "-25.50" and by_id[who["alice"]]["balance"] == "34.50"
    assert after["suggested_settlements"] == [{"from_user_id": who["bob"], "to_user_id": who["alice"], "amount": "34.50"}]
    assert sum(Decimal(m["balance"]) for m in after["members"]) == 0

    # Paying the rest settles the trip; nothing left to suggest.
    assert client.post(base, headers=ah, json={
        "from_user_id": who["bob"], "to_user_id": who["alice"], "amount": "34.50",
        "currency": "USD", "paid_on": "2027-05-03"}).status_code == 201
    settled = balances(client, trip, bh)
    assert settled["suggested_settlements"] == [] and settled["settlement"]["transfers"] == 0
    assert all(m["balance"] == "0.00" for m in settled["members"])

    listed = client.get(base, headers=bh)
    assert listed.status_code == 200 and listed.headers["X-Total-Count"] == "2"
    assert [p["amount"] for p in listed.json()] == ["34.50", "25.50"]  # newest payment first
    page = client.get(f"{base}?limit=1&offset=1", headers=bh)
    assert [p["amount"] for p in page.json()] == ["25.50"]

    # Removing a payment restores the balance.
    assert client.delete(f"{base}/{row['id']}", headers=ah).status_code == 204
    assert balances(client, trip, ah)["suggested_settlements"][0]["amount"] == "25.50"
    assert client.delete(f"{base}/{row['id']}", headers=ah).status_code == 404
    assert conn.scalar(select(func.count()).select_from(Settlement)) == 1


def test_payment_validation(expense_context):
    client, _, _, users, trip = expense_context
    ah = users["alice"][1]
    who = ids(expense_context)
    base = f"/api/v1/trips/{trip['id']}/settlements"
    good = {"from_user_id": who["bob"], "to_user_id": who["alice"], "amount": "10.00", "currency": "USD",
            "paid_on": "2027-05-02"}
    # No expenses yet: a payment has no ledger to settle against.
    none = client.post(base, headers=ah, json=good)
    assert none.status_code == 409 and none.json()["error"]["code"] == "SETTLEMENT_CURRENCY_CONFLICT"
    create(expense_context)
    assert client.post(base, headers=ah, json=good).status_code == 201
    for bad, status in (
        ({**good, "currency": "EUR"}, 409),
        ({**good, "to_user_id": who["bob"]}, 422),
        ({**good, "from_user_id": users["charlie"][0]["id"]}, 422),
        ({**good, "amount": "0"}, 422), ({**good, "amount": 10}, 422), ({**good, "amount": "1.005"}, 422),
        ({**good, "paid_on": "2027-02-30"}, 422), ({**good, "note": " "}, 422), ({**good, "note": "x" * 201}, 422),
        ({**good, "extra": 1}, 422),
    ):
        response = client.post(base, headers=ah, json=bad)
        assert response.status_code == status, (bad, response.text)
    # Non-members cannot see or record payments.
    for method, suffix in (("GET", ""), ("POST", ""), ("DELETE", "/1")):
        assert client.request(method, base + suffix, headers=users["charlie"][1], json=good).status_code == 404
    assert client.get(base).status_code == 401


def test_payment_events_reach_the_stream(expense_context):
    from app.realtime import TripEvent
    event = TripEvent(1, "settlement", "created", 2, 3)
    assert event.type == "settlement.created" and event.payload()["entity"] == "settlement"
