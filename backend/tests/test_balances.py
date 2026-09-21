from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, insert, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import Expense, ExpenseSplit, TripMember, User
from test_expenses import collaboration, create, expense_context, invite, TRIP


def read(context, actor="alice"):
    client, _, _, users, trip = context
    response = client.get(f"/trips/{trip['id']}/balances", headers=users[actor][1])
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    result = response.json()
    assert result["trip_id"] == trip["id"]
    final = {m["user_id"]: Decimal(m["balance"]) for m in result["members"]}
    assert sum(final.values(), Decimal(0)) == 0
    for member in result["members"]:
        assert set(member) == {"user_id", "username", "paid", "share", "balance"}
        for key in ("paid", "share", "balance"):
            assert isinstance(member[key], str)
            assert member[key] == format(Decimal(member[key]), ".2f")
    for suggestion in result["suggested_settlements"]:
        amount = Decimal(suggestion["amount"])
        assert amount > 0
        final[suggestion["from_user_id"]] += amount
        final[suggestion["to_user_id"]] -= amount
    assert all(value == 0 for value in final.values())
    return result


def amounts(result):
    return [(m["paid"], m["share"], m["balance"]) for m in result["members"]]


def test_empty_and_zero_member(expense_context):
    result = read(expense_context)
    assert result["currency"] is None and result["suggested_settlements"] == []
    assert amounts(result) == [("0.00", "0.00", "0.00")] * 2
    alice = expense_context[3]["alice"][0]["id"]
    create(expense_context, participant_user_ids=[alice])
    assert amounts(read(expense_context)) == [
        ("120.00", "120.00", "0.00"), ("0.00", "0.00", "0.00"),
    ]


def test_owner_without_membership_row_and_solo_expense(collaboration):
    client, conn, _, users, trip = collaboration
    alice = users["alice"][0]["id"]
    conn.execute(delete(TripMember).where(TripMember.trip_id == trip["id"]))
    create(collaboration, amount="100", participant_user_ids=[alice])
    assert amounts(read(collaboration)) == [("100.00", "100.00", "0.00")]


def test_shared_expense_update_delete(expense_context):
    client, _, _, users, trip = expense_context
    expense = create(expense_context)
    path = f"/trips/{trip['id']}/expenses/{expense['id']}"
    assert amounts(read(expense_context)) == [
        ("120.00", "60.00", "60.00"), ("0.00", "60.00", "-60.00"),
    ]
    assert read(expense_context) == read(expense_context, "bob")
    assert client.patch(path, headers=users["bob"][1], json={"amount": "150"}).status_code == 200
    assert amounts(read(expense_context)) == [
        ("150.00", "75.00", "75.00"), ("0.00", "75.00", "-75.00"),
    ]
    assert client.delete(path, headers=users["bob"][1]).status_code == 204
    assert read(expense_context)["currency"] is None
    assert read(expense_context)["suggested_settlements"] == []
    assert client.delete(f"/trips/{trip['id']}", headers=users["alice"][1]).status_code == 204
    assert client.get(f"/trips/{trip['id']}/balances", headers=users["alice"][1]).status_code == 404


def test_payer_not_split_participant(expense_context):
    users = expense_context[3]
    create(expense_context, amount="50", participant_user_ids=[users["bob"][0]["id"]])
    result = read(expense_context)
    assert amounts(result) == [("50.00", "0.00", "50.00"), ("0.00", "50.00", "-50.00")]
    assert result["suggested_settlements"] == [{
        "from_user_id": users["bob"][0]["id"], "to_user_id": users["alice"][0]["id"], "amount": "50.00",
    }]


@pytest.fixture
def three_people(expense_context):
    client, _, _, users, _ = expense_context
    invitation = invite(expense_context, "charlie")
    assert client.post(f"/invitations/{invitation['id']}/accept",
                       headers=users["charlie"][1]).status_code == 200
    return expense_context


def test_three_people_multiple_payments_and_freshness(three_people):
    client, _, _, users, trip = three_people
    ids = [u[0]["id"] for u in users.values()]
    create(three_people, amount="300", description="Hotel", participant_user_ids=ids)
    dinner = create(three_people, actor="bob", amount="90", description="Dinner",
                    paid_by_user_id=ids[1], participant_user_ids=ids)
    tickets = create(three_people, amount="60", description="Tickets", participant_user_ids=ids)
    assert amounts(read(three_people)) == [
        ("360.00", "150.00", "210.00"), ("90.00", "150.00", "-60.00"),
        ("0.00", "150.00", "-150.00"),
    ]
    path = f"/trips/{trip['id']}/expenses"
    assert client.patch(f"{path}/{dinner['id']}", headers=users["bob"][1],
                        json={"amount": "150"}).status_code == 200
    assert amounts(read(three_people)) == [
        ("360.00", "170.00", "190.00"), ("150.00", "170.00", "-20.00"),
        ("0.00", "170.00", "-170.00"),
    ]
    assert client.delete(f"{path}/{tickets['id']}", headers=users["charlie"][1]).status_code == 204
    assert amounts(read(three_people)) == [
        ("300.00", "150.00", "150.00"), ("150.00", "150.00", "0.00"),
        ("0.00", "150.00", "-150.00"),
    ]


def test_uses_stored_remainder_and_not_recomputed_splits(three_people):
    _, conn, _, users, _ = three_people
    ids = [u[0]["id"] for u in users.values()]
    expense = create(three_people, amount="100", participant_user_ids=ids)
    assert amounts(read(three_people)) == [
        ("100.00", "33.34", "66.66"), ("0.00", "33.33", "-33.33"),
        ("0.00", "33.33", "-33.33"),
    ]
    # A valid historical distribution proves aggregation reads stored shares.
    for user_id, share in zip(ids, ("20", "30", "50")):
        conn.execute(update(ExpenseSplit).where(
            ExpenseSplit.expense_id == expense["id"], ExpenseSplit.user_id == user_id,
        ).values(share_amount=Decimal(share)))
    assert [m["share"] for m in read(three_people)["members"]] == ["20.00", "30.00", "50.00"]


def test_aggregate_can_exceed_one_expense_limit(expense_context):
    for _ in range(2):
        create(expense_context, amount="9999999999.99")
    assert amounts(read(expense_context)) == [
        ("19999999999.98", "10000000000.00", "9999999999.98"),
        ("0.00", "9999999999.98", "-9999999999.98"),
    ]


def test_scope_and_pending(collaboration):
    client, _, _, users, trip = collaboration
    invite(collaboration)
    for actor in ("bob", "charlie"):
        assert client.get(f"/trips/{trip['id']}/balances", headers=users[actor][1]).status_code == 404
    assert client.get("/trips/2147483647/balances", headers=users["alice"][1]).status_code == 404
    other = client.post("/trips", headers=users["alice"][1], json=TRIP).json()
    create(collaboration, participant_user_ids=[users["alice"][0]["id"]])
    assert client.get(f"/trips/{other['id']}/balances",
                      headers=users["alice"][1]).json()["currency"] is None


@pytest.mark.parametrize("corruption", ["total", "offsetting", "currency", "historical", "missing_splits"])
def test_inconsistent_ledger_no_suggestions(expense_context, corruption):
    client, conn, _, users, trip = expense_context
    first = create(expense_context)
    second = create(expense_context)
    if corruption in ("total", "offsetting"):
        conn.execute(update(Expense).where(Expense.id == first["id"]).values(amount=Decimal("121")))
        if corruption == "offsetting":
            conn.execute(update(Expense).where(Expense.id == second["id"]).values(amount=Decimal("119")))
    elif corruption == "currency":
        conn.execute(update(Expense).where(Expense.id == first["id"]).values(currency="EUR"))
    elif corruption == "historical":
        conn.execute(delete(TripMember).where(
            TripMember.trip_id == trip["id"], TripMember.user_id == users["bob"][0]["id"],
        ))
    else:
        conn.execute(delete(ExpenseSplit).where(ExpenseSplit.expense_id == first["id"]))
    response = client.get(f"/trips/{trip['id']}/balances", headers=users["alice"][1])
    assert response.status_code == 409
    assert response.json() == {"detail": "Trip expense ledger is inconsistent"}


def test_ten_members_constant_query_count_no_writes(expense_context):
    client, conn, _, users, trip = expense_context
    create(expense_context)

    def captured_read():
        statements = []
        def capture(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(conn, "before_cursor_execute", capture)
        try:
            result = read(expense_context)
        finally:
            event.remove(conn, "before_cursor_execute", capture)
        queries = [s for s in statements if s.startswith(("SELECT", "WITH"))]
        assert len(queries) == 2  # Current user, then the complete authorized balance snapshot.
        assert not any(s.startswith(("INSERT", "UPDATE", "DELETE", "COMMIT")) for s in statements)
        assert "FOR UPDATE" not in " ".join(statements)
        return result

    captured_read()
    for index in range(8):
        user_id = conn.scalar(insert(User).values(
            username=f"extra{index}", email=f"extra{index}@example.com", password_hash="test-placeholder",
        ).returning(User.id))
        conn.execute(insert(TripMember).values(trip_id=trip["id"], user_id=user_id, role="member"))
    assert len(captured_read()["members"]) == 10


def test_anonymous_and_contract():
    def no_db():
        raise AssertionError("Anonymous DB access")
    app.dependency_overrides[get_db] = no_db
    try:
        with TestClient(app) as client:
            assert client.get("/trips/1/balances").status_code == 401
            assert client.post("/trips/1/balances", json={"balance": "100"}).status_code == 405
        operation = app.openapi()["paths"]["/api/v1/trips/{trip_id}/balances"]["get"]
        assert "requestBody" not in operation and operation["security"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_safe_database_failure():
    db = MagicMock(spec=Session)
    db.execute.side_effect = OperationalError("secret SQL", {}, Exception("secret"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(id=1)
    try:
        with TestClient(app) as client:
            response = client.get("/trips/1/balances")
        assert response.status_code == 503 and "secret" not in response.text
        db.rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
