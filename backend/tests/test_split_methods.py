"""Weighted and exact splits: the apportionment rule and the API around it."""
from decimal import Decimal
from random import Random

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models import ExpenseSplit
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.services.expenses import InvalidExpenseError, equal_split, exact_split, weighted_split
from test_expenses import BODY
from test_membership import collaboration, invite


@pytest.mark.parametrize("amount,weights,expected", [
    ("100.00", [(1, 1), (2, 2), (3, 4)], ["14.29", "28.57", "57.14"]),
    ("1.00", [(1, 1), (2, 2)], ["0.33", "0.67"]),            # the larger remainder wins the cent
    ("10.00", [(3, 1), (2, 1), (1, 1)], ["3.34", "3.33", "3.33"]),  # equal remainders: lowest id
    ("0.05", [(1, 1), (2, 1), (3, 1)], ["0.02", "0.02", "0.01"]),
    ("0.01", [(1, 1), (2, 1000000)], ["0.00", "0.01"]),
    ("9999999999.99", [(1, 3), (2, 7)], ["3000000000.00", "6999999999.99"]),
])
def test_largest_remainder_examples(amount, weights, expected):
    result = weighted_split(Decimal(amount), weights)
    assert [user_id for user_id, _ in result] == sorted(user_id for user_id, _ in weights)
    assert [share for _, share in result] == list(map(Decimal, expected))
    assert sum(share for _, share in result) == Decimal(amount)
    assert weighted_split(Decimal(amount), weights[::-1]) == result


def test_weighted_split_conserves_and_stays_within_a_cent_of_proportional():
    random = Random(7)
    for _ in range(300):
        count = random.randint(1, 12)
        weights = [(user_id, random.randint(1, 50)) for user_id in range(1, count + 1)]
        amount = Decimal(random.randint(1, 10_000_000)).scaleb(-2)
        result = weighted_split(amount, weights)
        total = sum(weight for _, weight in weights)
        assert sum(share for _, share in result) == amount
        for (user_id, share), (_, weight) in zip(result, weights):
            assert abs(share - amount * weight / total) < Decimal("0.01")


def test_equal_split_is_the_unit_weight_case():
    assert equal_split(Decimal("100.00"), [3, 1, 2]) == weighted_split(Decimal("100.00"), [(1, 1), (2, 1), (3, 1)])


@pytest.mark.parametrize("weights", [[], [(1, 0)], [(1, True)], [(1, 1.0)], [(1, 1), (1, 2)], [(1, -1)]])
def test_weighted_split_rejects_bad_weights(weights):
    with pytest.raises(ValueError):
        weighted_split(Decimal("1.00"), weights)


def test_exact_split_must_add_up():
    assert exact_split(Decimal("10.00"), [(2, Decimal("7.50")), (1, Decimal("2.50"))]) == [
        (1, Decimal("2.50")), (2, Decimal("7.50"))]
    with pytest.raises(InvalidExpenseError, match="add up to 9.99, not 10.00"):
        exact_split(Decimal("10.00"), [(1, Decimal("9.99"))])


SHARES = {**BODY, "split_method": "shares", "participant_user_ids": None,
          "splits": [{"user_id": 1, "weight": 1}, {"user_id": 2, "weight": 3}]}
EXACT = {**BODY, "split_method": "exact", "participant_user_ids": None,
         "splits": [{"user_id": 1, "amount": "20.00"}, {"user_id": 2, "amount": "100.00"}]}


@pytest.mark.parametrize("changes", [
    {"split_method": "shares"},                                     # shares without splits
    {"split_method": "exact", "splits": EXACT["splits"]},           # exact plus participants
    {"split_method": "equal", "splits": SHARES["splits"], "participant_user_ids": None},
    {**SHARES, "splits": [{"user_id": 1, "weight": 1}, {"user_id": 2, "amount": "1.00"}]},
    {**SHARES, "splits": [{"user_id": 1, "amount": "60.00"}, {"user_id": 2, "amount": "60.00"}]},
    {**EXACT, "splits": [{"user_id": 1, "weight": 1}, {"user_id": 2, "weight": 1}]},
    {**EXACT, "splits": [{"user_id": 1, "amount": "20.00"}, {"user_id": 2, "amount": "99.99"}]},
    {**SHARES, "splits": [{"user_id": 1, "weight": 1}, {"user_id": 1, "weight": 2}]},
    {**SHARES, "splits": [{"user_id": 1, "weight": 0}]},
    {**SHARES, "splits": [{"user_id": 1, "weight": 1000001}]},
    {**SHARES, "splits": [{"user_id": 1, "weight": "2"}]},
    {**SHARES, "splits": [{"user_id": 1, "weight": 1, "amount": "120.00"}]},
    {**SHARES, "splits": [{"user_id": 1}]},
    {**EXACT, "splits": [{"user_id": 1, "amount": 120}]},
    {**EXACT, "splits": [{"user_id": 1, "amount": "0"}]},
    {**SHARES, "split_method": "halves"},
    {**SHARES, "splits": []},
])
def test_create_schema_rejects_inconsistent_splits(changes):
    with pytest.raises(ValidationError):
        ExpenseCreate(**{**BODY, **changes})


def test_create_schema_accepts_each_method():
    assert ExpenseCreate(**BODY).split_method == "equal"
    assert [s.weight for s in ExpenseCreate(**SHARES).splits] == [1, 3]
    assert [s.amount for s in ExpenseCreate(**EXACT).splits] == [Decimal("20.00"), Decimal("100.00")]
    # Splits come back sorted by user, whatever the client's order.
    swapped = ExpenseCreate(**{**SHARES, "splits": SHARES["splits"][::-1]})
    assert [s.user_id for s in swapped.splits] == [1, 2]


@pytest.mark.parametrize("changes", [
    {"split_method": "equal", "splits": SHARES["splits"]},
    {"split_method": "shares", "participant_user_ids": [1]},
    {"participant_user_ids": [1], "splits": SHARES["splits"]},
    {"amount": "10.00", "splits": EXACT["splits"]},
    {"splits": None}, {"split_method": None},
])
def test_update_schema_rejects_inconsistent_splits(changes):
    with pytest.raises(ValidationError):
        ExpenseUpdate(**changes)


@pytest.fixture
def three_members(collaboration):
    client, _, _, users, _ = collaboration
    for name in ("bob", "charlie"):
        invitation = invite(collaboration, name)
        assert client.post(f"/invitations/{invitation['id']}/accept",
                           headers=users[name][1]).status_code == 200
    return collaboration


def ids(context):
    _, _, _, users, _ = context
    return {name: users[name][0]["id"] for name in ("alice", "bob", "charlie")}


def shares_of(row):
    return [(s["user_id"], s["share_amount"], s["weight"]) for s in row["splits"]]


def test_shares_and_exact_over_the_api(three_members):
    client, conn, _, users, trip = three_members
    ah = users["alice"][1]
    who = ids(three_members)
    path = f"/trips/{trip['id']}/expenses"
    created = client.post(path, headers=ah, json={
        **BODY, "amount": "100.00", "paid_by_user_id": who["alice"], "split_method": "shares",
        "participant_user_ids": None, "splits": [
            {"user_id": who["charlie"], "weight": 4}, {"user_id": who["alice"], "weight": 1},
            {"user_id": who["bob"], "weight": 2},
        ],
    })
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["split_method"] == "shares"
    assert shares_of(row) == [(who["alice"], "14.29", 1), (who["bob"], "28.57", 2), (who["charlie"], "57.14", 4)]
    assert client.get(f"{path}/{row['id']}", headers=users["bob"][1]).json() == row

    # Changing the amount keeps the weights and re-apportions.
    rescaled = client.patch(f"{path}/{row['id']}", headers=ah, json={"amount": "7.00"})
    assert rescaled.status_code == 200
    assert shares_of(rescaled.json()) == [(who["alice"], "1.00", 1), (who["bob"], "2.00", 2), (who["charlie"], "4.00", 4)]
    assert rescaled.json()["version"] == row["version"] + 1

    # Switching to equal without participants keeps the same people, drops the weights.
    equal = client.patch(f"{path}/{row['id']}", headers=ah, json={"split_method": "equal"})
    assert equal.status_code == 200 and equal.json()["split_method"] == "equal"
    assert shares_of(equal.json()) == [(who["alice"], "2.34", None), (who["bob"], "2.33", None), (who["charlie"], "2.33", None)]

    # Switching to shares without splits starts every weight at 1.
    back = client.patch(f"{path}/{row['id']}", headers=ah, json={"split_method": "shares"})
    assert shares_of(back.json()) == [(who["alice"], "2.34", 1), (who["bob"], "2.33", 1), (who["charlie"], "2.33", 1)]

    # Exact amounts must add up to the stored amount.
    short = client.patch(f"{path}/{row['id']}", headers=ah, json={
        "split_method": "exact", "splits": [{"user_id": who["bob"], "amount": "6.99"}]})
    assert short.status_code == 422 and "add up to 6.99, not 7.00" in short.text
    exact = client.patch(f"{path}/{row['id']}", headers=ah, json={
        "split_method": "exact",
        "splits": [{"user_id": who["bob"], "amount": "6.99"}, {"user_id": who["charlie"], "amount": "0.01"}],
    })
    assert exact.status_code == 200 and exact.json()["split_method"] == "exact"
    assert shares_of(exact.json()) == [(who["bob"], "6.99", None), (who["charlie"], "0.01", None)]
    # An exact split cannot be rescaled blindly: new amounts are required.
    blind = client.patch(f"{path}/{row['id']}", headers=ah, json={"amount": "8.00"})
    assert blind.status_code == 422 and "Send exact shares" in blind.text
    both = client.patch(f"{path}/{row['id']}", headers=ah, json={
        "amount": "8.00", "splits": [{"user_id": who["bob"], "amount": "8.00"}]})
    assert both.status_code == 200
    assert shares_of(both.json()) == [(who["bob"], "8.00", None)]
    # Re-sending the same exact split is a no-op: no new version, no split rewrite.
    same = client.patch(f"{path}/{row['id']}", headers=ah, json={
        "splits": [{"user_id": who["bob"], "amount": "8.00"}]})
    assert same.json() == both.json()
    assert conn.scalar(select(func.count()).select_from(ExpenseSplit)) == 1

    # Participants of any method must belong to the trip; method/field mismatches are 422.
    for bad in (
        {"split_method": "shares", "splits": [{"user_id": 2147483647, "weight": 1}]},
        {"split_method": "shares", "participant_user_ids": [who["bob"]]},
        {"split_method": "equal", "splits": [{"user_id": who["bob"], "weight": 1}]},
        {"split_method": "shares", "splits": [{"user_id": who["bob"], "amount": "8.00"}]},
        {"splits": [{"user_id": who["bob"], "weight": 1}]},  # stored method is exact
    ):
        response = client.patch(f"{path}/{row['id']}", headers=ah, json=bad)
        assert response.status_code == 422, (bad, response.text)
        assert client.get(f"{path}/{row['id']}", headers=ah).json() == both.json()


def test_shares_feed_balances_and_the_settlement_summary(three_members):
    client, _, _, users, trip = three_members
    ah = users["alice"][1]
    who = ids(three_members)
    path = f"/trips/{trip['id']}/expenses"
    assert client.post(path, headers=ah, json={
        **BODY, "amount": "90.00", "paid_by_user_id": who["alice"], "split_method": "shares",
        "participant_user_ids": None, "splits": [
            {"user_id": who["alice"], "weight": 1}, {"user_id": who["bob"], "weight": 1},
            {"user_id": who["charlie"], "weight": 4},
        ],
    }).status_code == 201
    assert client.post(path, headers=ah, json={
        **BODY, "amount": "30.00", "paid_by_user_id": who["bob"], "split_method": "exact",
        "participant_user_ids": None, "splits": [
            {"user_id": who["alice"], "amount": "10.00"}, {"user_id": who["charlie"], "amount": "20.00"},
        ],
    }).status_code == 201
    balance = client.get(f"/trips/{trip['id']}/balances", headers=users["charlie"][1]).json()
    assert [(m["paid"], m["share"], m["balance"]) for m in balance["members"]] == [
        ("90.00", "25.00", "65.00"), ("30.00", "15.00", "15.00"), ("0.00", "80.00", "-80.00"),
    ]
    assert balance["suggested_settlements"] == [
        {"from_user_id": who["charlie"], "to_user_id": who["alice"], "amount": "65.00"},
        {"from_user_id": who["charlie"], "to_user_id": who["bob"], "amount": "15.00"},
    ]
    assert balance["settlement"] == {"transfers": 2, "unsettled_members": 3, "minimal": True}
