from contextlib import contextmanager
from decimal import Decimal
from typing import Iterator, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.models import Expense, ExpenseSplit, Trip, TripMember
from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate
from app.services.trips import get_accessible_trip


class ExpenseNotFoundError(Exception):
    pass


class InvalidExpenseError(Exception):
    pass


class ExpenseCurrencyConflictError(Exception):
    pass


class ExpenseUnavailableError(Exception):
    pass


@contextmanager
def expense_errors(db: Session) -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError:
        db.rollback()
        raise ExpenseUnavailableError() from None
    except (ExpenseNotFoundError, InvalidExpenseError, ExpenseCurrencyConflictError):
        db.rollback()
        raise


def equal_split(amount: Decimal, participant_user_ids: list[int]) -> list[tuple[int, Decimal]]:
    """Distribute exact hundredths, giving the remainder to ascending user IDs."""
    if not isinstance(amount, Decimal) or not amount.is_finite() or not (
        Decimal("0") < amount <= Decimal("9999999999.99")
    ) or amount.as_tuple().exponent < -2:
        raise ValueError("Invalid exact amount")
    if not participant_user_ids or len(set(participant_user_ids)) != len(participant_user_ids):
        raise ValueError("Participants must be nonempty and unique")
    units = int(amount * 100)
    quotient, remainder = divmod(units, len(participant_user_ids))
    return [
        (user_id, Decimal(quotient + (index < remainder)).scaleb(-2))
        for index, user_id in enumerate(sorted(participant_user_ids))
    ]


def validate_people(db: Session, trip: Trip, payer: int, participants: list[int]) -> None:
    requested = set(participants) | {payer}
    members = set(db.scalars(select(TripMember.user_id).where(
        TripMember.trip_id == trip.id, TripMember.user_id.in_(requested),
    )))
    if not requested <= members | {trip.owner_id}:
        raise InvalidExpenseError("Payer and participants must belong to this trip")


def validate_currency(
    db: Session, trip_id: int, currency: str, expense_id: Optional[int] = None,
) -> None:
    statement = select(Expense.id).where(Expense.trip_id == trip_id, Expense.currency != currency)
    if expense_id is not None:
        statement = statement.where(Expense.id != expense_id)
    if db.scalar(statement.limit(1)) is not None:
        raise ExpenseCurrencyConflictError()


def expense_query(trip_id: int):
    # One SQL snapshot includes both amount and splits, even during concurrent PATCH.
    return select(Expense).where(Expense.trip_id == trip_id).options(joinedload(Expense.splits))


def find_expense(db: Session, trip_id: int, expense_id: int) -> Expense:
    expense = db.execute(expense_query(trip_id).where(Expense.id == expense_id)).unique().scalar_one_or_none()
    if expense is None:
        raise ExpenseNotFoundError()
    return expense


def list_expenses(db: Session, trip_id: int, user_id: int) -> list[ExpenseResponse]:
    get_accessible_trip(db, trip_id, user_id)
    with expense_errors(db):
        rows = db.execute(expense_query(trip_id).order_by(
            Expense.expense_date.desc(), Expense.created_at.desc(), Expense.id.desc(),
        )).unique().scalars()
        return [ExpenseResponse.model_validate(row) for row in rows]


def get_expense(db: Session, trip_id: int, user_id: int, expense_id: int) -> ExpenseResponse:
    get_accessible_trip(db, trip_id, user_id)
    with expense_errors(db):
        return ExpenseResponse.model_validate(find_expense(db, trip_id, expense_id))


def make_splits(amount: Decimal, participants: list[int]) -> list[ExpenseSplit]:
    return [ExpenseSplit(user_id=user_id, share_amount=share)
            for user_id, share in equal_split(amount, participants)]


def create_expense(
    db: Session, trip_id: int, user_id: int, payload: ExpenseCreate,
) -> ExpenseResponse:
    trip = get_accessible_trip(db, trip_id, user_id, for_update=True)
    with expense_errors(db):
        validate_people(db, trip, payload.paid_by_user_id, payload.participant_user_ids)
        validate_currency(db, trip_id, payload.currency)
        expense = Expense(
            **payload.model_dump(exclude={"participant_user_ids"}),
            trip_id=trip_id, created_by_user_id=user_id,
            splits=make_splits(payload.amount, payload.participant_user_ids),
        )
        db.add(expense)
        db.flush()
        result = ExpenseResponse.model_validate(expense)
        db.commit()
        return result


def update_expense(
    db: Session, trip_id: int, user_id: int, expense_id: int, payload: ExpenseUpdate,
) -> ExpenseResponse:
    trip = get_accessible_trip(db, trip_id, user_id, for_update=True)
    with expense_errors(db):
        expense = find_expense(db, trip_id, expense_id)
        changes = payload.model_dump(exclude_unset=True)
        old_participants = [split.user_id for split in expense.splits]
        participants = changes.pop("participant_user_ids", old_participants)
        amount = changes.get("amount", expense.amount)
        validate_people(db, trip, changes.get("paid_by_user_id", expense.paid_by_user_id), participants)
        validate_currency(db, trip_id, changes.get("currency", expense.currency), expense_id)
        recalculate = amount != expense.amount or participants != old_participants
        for field, value in changes.items():
            setattr(expense, field, value)
        if recalculate:
            # Delete old pairs before inserting replacements with the same unique keys.
            expense.splits = []
            expense.updated_at = func.statement_timestamp()
            db.flush()
            expense.splits = make_splits(amount, participants)
        db.flush()
        result = ExpenseResponse.model_validate(expense)
        db.commit()
        return result


def delete_expense(db: Session, trip_id: int, user_id: int, expense_id: int) -> None:
    get_accessible_trip(db, trip_id, user_id, for_update=True)
    with expense_errors(db):
        expense = find_expense(db, trip_id, expense_id)
        db.delete(expense)
        db.commit()
