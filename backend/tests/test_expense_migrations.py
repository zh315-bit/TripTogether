from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Expense, ExpenseSplit, Trip, User


@pytest.fixture
def expense_values(migrated_database):
    conn, _ = migrated_database
    user_id = conn.scalar(User.__table__.insert().values(
        username="owner", email="owner@example.com", password_hash="test-placeholder",
    ).returning(User.id))
    trip_id = conn.scalar(Trip.__table__.insert().values(
        name="Trip", destination="Tokyo", owner_id=user_id,
        start_date=date(2027, 6, 10), end_date=date(2027, 6, 20),
    ).returning(Trip.id))
    return {
        "trip_id": trip_id, "created_by_user_id": user_id, "paid_by_user_id": user_id,
        "description": "Dinner", "expense_date": date(2027, 5, 1),
        "amount": Decimal("120.00"), "currency": "USD",
    }


def test_money_metadata():
    for column in (Expense.__table__.c.amount, ExpenseSplit.__table__.c.share_amount):
        assert column.type.precision == 12 and column.type.scale == 2 and column.type.asdecimal


def test_0005_round_trip(migrated_database, expense_values):
    conn, config = migrated_database
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0005"
    command.check(config)
    command.downgrade(config, "0004")
    assert "expenses" not in inspect(conn).get_table_names()
    assert "expense_splits" not in inspect(conn).get_table_names()
    assert conn.scalar(select(Trip.id)) == expense_values["trip_id"]
    command.upgrade(config, "head")
    command.check(config)
    row = conn.execute(Expense.__table__.insert().values(**expense_values).returning(
        Expense.amount, Expense.created_at, Expense.updated_at,
    )).one()
    assert isinstance(row.amount, Decimal)
    assert row.created_at.tzinfo is not None and row.updated_at.tzinfo is not None


@pytest.mark.parametrize("column", list(Expense.__table__.c.keys()))
def test_expense_not_null(migrated_database, expense_values, column):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(Expense.__table__.insert().values(**{**expense_values, column: None}))
    assert error.value.orig.sqlstate == "23502"


@pytest.mark.parametrize("changes,constraint", [
    ({"amount": Decimal("0")}, "ck_expenses_amount"),
    ({"amount": Decimal("-1")}, "ck_expenses_amount"),
    ({"amount": Decimal("NaN")}, "ck_expenses_amount"),
    ({"currency": "usd"}, "ck_expenses_currency"),
    ({"currency": "US"}, "ck_expenses_currency"),
    ({"description": " "}, "ck_expenses_description"),
    ({"trip_id": 2147483647}, "fk_expenses_trip"),
    ({"paid_by_user_id": 2147483647}, "fk_expenses_payer"),
    ({"created_by_user_id": 2147483647}, "fk_expenses_creator"),
])
def test_expense_constraints(migrated_database, expense_values, changes, constraint):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(Expense.__table__.insert().values(**{**expense_values, **changes}))
    assert error.value.orig.diag.constraint_name == constraint


@pytest.fixture
def split_values(migrated_database, expense_values):
    conn, _ = migrated_database
    expense_id = conn.scalar(Expense.__table__.insert().values(**expense_values).returning(Expense.id))
    return {"expense_id": expense_id, "user_id": expense_values["paid_by_user_id"],
            "share_amount": Decimal("120.00")}


@pytest.mark.parametrize("column", list(ExpenseSplit.__table__.c.keys()))
def test_split_not_null(migrated_database, split_values, column):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(ExpenseSplit.__table__.insert().values(**{**split_values, column: None}))
    assert error.value.orig.sqlstate == "23502"


@pytest.mark.parametrize("changes,constraint", [
    ({"share_amount": Decimal("-0.01")}, "ck_expense_splits_amount"),
    ({"share_amount": Decimal("NaN")}, "ck_expense_splits_amount"),
    ({"expense_id": 2147483647}, "fk_expense_splits_expense"),
    ({"user_id": 2147483647}, "fk_expense_splits_user"),
])
def test_split_constraints(migrated_database, split_values, changes, constraint):
    conn, _ = migrated_database
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(ExpenseSplit.__table__.insert().values(**{**split_values, **changes}))
    assert error.value.orig.diag.constraint_name == constraint


def test_split_unique_and_sql_cascade(migrated_database, split_values):
    conn, _ = migrated_database
    conn.execute(ExpenseSplit.__table__.insert().values(**split_values))
    with pytest.raises(IntegrityError) as error:
        with conn.begin_nested():
            conn.execute(ExpenseSplit.__table__.insert().values(**split_values))
    assert error.value.orig.diag.constraint_name == "uq_expense_splits_expense_user"
    conn.execute(delete(Expense).where(Expense.id == split_values["expense_id"]))
    assert conn.scalar(select(ExpenseSplit.id)) is None
