from decimal import Decimal
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
from app.models import Expense, ExpenseSplit, User
from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate
from app.services.expenses import equal_split
from test_membership import collaboration, invite, TRIP


BODY = {
    "description": " Dinner ", "amount": "120.00", "currency": "USD",
    "expense_date": "2027-05-01", "paid_by_user_id": 1, "participant_user_ids": [1, 2],
}
ROUTES = [("POST", "", BODY), ("GET", "", None), ("GET", "/1", None),
          ("PATCH", "/1", {"amount": "150.00"}), ("DELETE", "/1", None)]


@pytest.mark.parametrize("amount,shares", [
    ("120.00", ["60.00", "60.00"]), ("100.00", ["33.34", "33.33", "33.33"]),
    ("0.01", ["0.01", "0.00", "0.00"]), ("9999999999.99", ["3333333333.33"] * 3),
])
def test_exact_split(amount, shares):
    ids = list(range(len(shares), 0, -1))
    result = equal_split(Decimal(amount), ids)
    assert [user_id for user_id, _ in result] == sorted(ids)
    assert [share for _, share in result] == list(map(Decimal, shares))
    assert all(isinstance(share, Decimal) for _, share in result)
    assert sum(share for _, share in result) == Decimal(amount)
    assert equal_split(Decimal(amount), ids[::-1]) == result


def test_split_conservation_many_sizes():
    for units in range(1, 101):
        for count in range(1, 11):
            amount = Decimal(units).scaleb(-2)
            shares = [share for _, share in equal_split(amount, list(range(1, count + 1)))]
            assert sum(shares) == amount
            assert max(shares) - min(shares) <= Decimal("0.01")


@pytest.mark.parametrize("amount", [
    120.0, 120, True, None, "0", "-1", "NaN", "Infinity", "1e2", "1.001",
    "10000000000.00", " 1.00", "", Decimal("NaN"), Decimal("Infinity"), Decimal("1.001"),
])
def test_bad_amounts(amount):
    with pytest.raises(ValidationError):
        ExpenseCreate(**{**BODY, "amount": amount})
    with pytest.raises(ValidationError):
        ExpenseUpdate(amount=amount)


@pytest.mark.parametrize("field,value", [
    ("description", " "), ("description", "x" * 201), ("description", "\x00"),
    ("description", "\ud800"), ("currency", "usd"), ("currency", "US"),
    ("currency", "USD\n"), ("currency", "U1D"), ("participant_user_ids", []),
    ("participant_user_ids", [1, 1]), ("participant_user_ids", [True]),
    ("participant_user_ids", ["1"]), ("participant_user_ids", [2147483648]),
    ("paid_by_user_id", 0), ("expense_date", "2027-02-30"),
    ("expense_date", "2027-06-10T00:00:00"), ("expense_date", 1),
    ("id", 1), ("trip_id", 1), ("created_by_user_id", 1), ("splits", []),
    ("created_at", "2027-05-01"), ("updated_at", "2027-05-01"),
])
def test_strict_inputs(field, value):
    with pytest.raises(ValidationError):
        ExpenseCreate(**{**BODY, field: value})
    with pytest.raises(ValidationError):
        ExpenseUpdate(**{field: value})


@pytest.mark.parametrize("field", list(BODY))
def test_patch_cannot_clear_required_fields(field):
    with pytest.raises(ValidationError):
        ExpenseUpdate(**{field: None})


def test_schema_keeps_decimal_and_documents_string():
    parsed = ExpenseCreate(**BODY)
    assert isinstance(parsed.amount, Decimal)
    assert parsed.description == "Dinner"
    assert ExpenseCreate.model_json_schema()["properties"]["amount"]["type"] == "string"


@pytest.fixture
def expense_context(collaboration):
    client, conn, sessions, users, trip = collaboration
    invitation = invite(collaboration)
    assert client.post(f"/invitations/{invitation['id']}/accept",
                       headers=users["bob"][1]).status_code == 200
    return collaboration


def create(context, actor="alice", **changes):
    client, _, _, users, trip = context
    body = {
        **BODY, "paid_by_user_id": users["alice"][0]["id"],
        "participant_user_ids": [users["bob"][0]["id"], users["alice"][0]["id"]],
        **changes,
    }
    response = client.post(f"/trips/{trip['id']}/expenses", headers=users[actor][1], json=body)
    assert response.status_code == 201, response.text
    return response.json()


def assert_shares(response, amounts):
    assert isinstance(response["amount"], str)
    assert [s["share_amount"] for s in response["splits"]] == amounts
    assert sum(Decimal(s["share_amount"]) for s in response["splits"]) == Decimal(response["amount"])
    assert "password" not in str(response)


def test_shared_flow_update_and_creator_payer(expense_context):
    client, conn, _, users, trip = expense_context
    ah, bh = users["alice"][1], users["bob"][1]
    path = f"/trips/{trip['id']}/expenses"
    row = create(expense_context)
    assert_shares(row, ["60.00", "60.00"])
    parsed_response = ExpenseResponse.model_validate(row)
    assert isinstance(parsed_response.amount, Decimal)
    assert all(isinstance(split.share_amount, Decimal) for split in parsed_response.splits)
    assert client.get(path, headers=bh).json() == [row]
    result = client.patch(f"{path}/{row['id']}", headers=bh, json={"amount": "150.00"})
    assert result.status_code == 200
    changed = result.json()
    assert_shares(changed, ["75.00", "75.00"])
    assert changed["created_by_user_id"] == row["created_by_user_id"]
    assert changed["created_at"] == row["created_at"]
    assert changed["updated_at"] > row["updated_at"]
    assert client.get(f"{path}/{row['id']}", headers=ah).json() == changed
    assert client.patch(f"{path}/{row['id']}", headers=bh, json={}).json() == changed
    assert client.patch(f"{path}/{row['id']}", headers=bh, json={"amount": "150"}).json() == changed
    updated = client.patch(f"{path}/{row['id']}", headers=bh, json={
        "participant_user_ids": [users["bob"][0]["id"]],
    })
    assert updated.status_code == 200
    assert_shares(updated.json(), ["150.00"])
    assert updated.json()["updated_at"] > changed["updated_at"]
    assert conn.scalar(select(func.count()).select_from(ExpenseSplit)) == 1
    second = create(expense_context, actor="bob", participant_user_ids=[users["bob"][0]["id"]])
    assert second["created_by_user_id"] == users["bob"][0]["id"]
    assert second["paid_by_user_id"] == users["alice"][0]["id"]
    assert_shares(second, ["120.00"])
    with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
        expense = db.get(Expense, row["id"])
        assert isinstance(expense.amount, Decimal)
        assert all(isinstance(split.share_amount, Decimal) for split in expense.splits)
    assert client.delete(f"{path}/{row['id']}", headers=bh).status_code == 204
    assert conn.scalar(select(ExpenseSplit.id).where(ExpenseSplit.expense_id == row["id"])) is None
    assert client.delete(f"/trips/{trip['id']}", headers=ah).status_code == 204
    assert conn.scalar(select(func.count()).select_from(Expense)) == 0
    assert conn.scalar(select(func.count()).select_from(ExpenseSplit)) == 0


@pytest.mark.parametrize("method,suffix,body", ROUTES)
def test_other_and_pending_denied(collaboration, method, suffix, body):
    client, _, _, users, trip = collaboration
    invite(collaboration)
    for actor in ("bob", "charlie"):
        assert client.request(method, f"/trips/{trip['id']}/expenses{suffix}",
                              headers=users[actor][1], json=body).status_code == 404


@pytest.mark.parametrize("method,suffix,body", ROUTES)
def test_anonymous_no_db(method, suffix, body):
    def no_db():
        raise AssertionError("Anonymous DB access")
    app.dependency_overrides[get_db] = no_db
    try:
        with TestClient(app) as client:
            assert client.request(method, "/trips/1/expenses" + suffix, json=body).status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_people_validation_and_scope(expense_context):
    client, _, _, users, trip = expense_context
    ah = users["alice"][1]
    path = f"/trips/{trip['id']}/expenses"
    row = create(expense_context)
    for bad_id in (users["charlie"][0]["id"], 2147483647):
        for change in ({"paid_by_user_id": bad_id}, {"participant_user_ids": [bad_id]}):
            assert client.post(path, headers=ah, json={**BODY, **change}).status_code == 422
            assert client.patch(f"{path}/{row['id']}", headers=ah, json=change).status_code == 422
            assert client.get(f"{path}/{row['id']}", headers=ah).json() == row
    other = client.post("/trips", headers=ah, json=TRIP).json()
    for method, body in (("GET", None), ("PATCH", {"amount": "1.00"}), ("DELETE", None)):
        assert client.request(method, f"/trips/{other['id']}/expenses/{row['id']}",
                              headers=ah, json=body).status_code == 404


def test_currency_policy_and_date_order(expense_context):
    client, _, _, users, trip = expense_context
    ah = users["alice"][1]
    path = f"/trips/{trip['id']}/expenses"
    first = create(expense_context)
    second = create(expense_context, expense_date="2027-08-01")
    third = create(expense_context, expense_date="2027-08-01")
    assert [e["id"] for e in client.get(path, headers=ah).json()] == [third["id"], second["id"], first["id"]]
    assert client.post(path, headers=ah, json={**BODY, "currency": "EUR"}).status_code == 409
    assert client.patch(f"{path}/{first['id']}", headers=ah, json={"currency": "EUR"}).status_code == 409
    for row in (second, third):
        assert client.delete(f"{path}/{row['id']}", headers=ah).status_code == 204
    changed = client.patch(f"{path}/{first['id']}", headers=ah, json={"currency": "EUR"})
    assert changed.status_code == 200 and changed.json()["currency"] == "EUR"
    assert_shares(changed.json(), ["60.00", "60.00"])
    assert client.delete(f"{path}/{first['id']}", headers=ah).status_code == 204
    assert create(expense_context, currency="JPY")["currency"] == "JPY"


@pytest.mark.parametrize("operation", ["create", "update"])
def test_split_failure_rolls_back_everything(expense_context, operation):
    client, conn, _, users, trip = expense_context
    ah = users["alice"][1]
    path = f"/trips/{trip['id']}/expenses"
    original = create(expense_context)
    seen = []

    def fail_split(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith(("INSERT INTO expenses", "UPDATE expenses")):
            seen.append(True)
        if statement.startswith("INSERT INTO expense_splits"):
            raise OperationalError("secret SQL", {}, Exception("secret"))

    event.listen(conn, "before_cursor_execute", fail_split)
    try:
        if operation == "create":
            response = client.post(path, headers=ah, json=BODY)
        else:
            response = client.patch(f"{path}/{original['id']}", headers=ah, json={"amount": "150.00"})
    finally:
        event.remove(conn, "before_cursor_execute", fail_split)
    assert seen and response.status_code == 503 and "secret" not in response.text
    assert client.get(path, headers=ah).json() == [original]
    assert_shares(create(expense_context), ["60.00", "60.00"])


@pytest.mark.parametrize("method,suffix,body", ROUTES)
def test_safe_db_failure(method, suffix, body):
    db = MagicMock(spec=Session)
    db.scalar.side_effect = OperationalError("secret SQL", {}, Exception("secret"))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(id=1)
    try:
        with TestClient(app) as client:
            response = client.request(method, "/trips/1/expenses" + suffix, json=body)
        assert response.status_code == 503 and "secret" not in response.text
        db.rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
