from decimal import Decimal

from sqlalchemy import select

from app.models import Expense, ExpenseSplit
from test_membership_concurrency import concurrent_client, simultaneous_requests
from test_itinerary_concurrency import participants


def test_concurrent_expense_patch_stays_consistent(participants):
    client, engine, factory, trip_id, ah, bh = participants
    members = client.get(f"/trips/{trip_id}/members", headers=ah).json()
    ids = [member["user_id"] for member in members]
    path = f"/trips/{trip_id}/expenses"
    original = client.post(path, headers=ah, json={
        "description": "Dinner", "amount": "120.00", "currency": "USD",
        "paid_by_user_id": ids[0], "participant_user_ids": ids, "expense_date": "2027-05-01",
    })
    assert original.status_code == 201
    expense_id = original.json()["id"]
    results = simultaneous_requests(engine, [
        lambda: client.patch(f"{path}/{expense_id}", headers=ah, json={"amount": "100.00"}),
        lambda: client.patch(f"{path}/{expense_id}", headers=bh, json={
            "amount": "0.01", "participant_user_ids": [ids[1]],
        }),
    ])
    assert [r.status_code for r in results] == [200, 200]
    for response in results:
        row = response.json()
        assert sum(Decimal(s["share_amount"]) for s in row["splits"]) == Decimal(row["amount"])
    with factory() as db:
        expense = db.get(Expense, expense_id)
        assert sum(db.scalars(select(ExpenseSplit.share_amount).where(
            ExpenseSplit.expense_id == expense_id,
        ))) == expense.amount


def test_concurrent_first_currency_has_one_winner(participants):
    client, engine, _, trip_id, ah, bh = participants
    ids = [m["user_id"] for m in client.get(f"/trips/{trip_id}/members", headers=ah).json()]
    path = f"/trips/{trip_id}/expenses"
    results = simultaneous_requests(engine, [
        lambda h=h, currency=currency: client.post(path, headers=h, json={
            "description": "Dinner", "amount": "120.00", "currency": currency,
            "paid_by_user_id": ids[0], "participant_user_ids": ids, "expense_date": "2027-05-01",
        })
        for h, currency in ((ah, "USD"), (bh, "EUR"))
    ])
    assert sorted(r.status_code for r in results) == [201, 409]
    assert len(client.get(path, headers=ah).json()) == 1
