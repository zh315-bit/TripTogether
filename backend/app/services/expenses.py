from contextlib import contextmanager
from decimal import Decimal
from typing import Iterator, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.models import Expense, ExpenseSplit, Trip, TripMember
from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate, SplitInput
from app.realtime import TripEvent, stage
from app.services.trips import get_accessible_trip
from app.services.versioning import require_version


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


def weighted_split(amount: Decimal, weights: list[tuple[int, int]]) -> list[tuple[int, Decimal]]:
    """Apportion exact hundredths by weight with the largest-remainder method.

    Every participant gets the floor of their proportional share; the leftover
    cents go one each to the largest fractional remainders, ties broken by
    ascending user ID. The result is deterministic and sums to the amount.
    """
    if not isinstance(amount, Decimal) or not amount.is_finite() or not (
        Decimal("0") < amount <= Decimal("9999999999.99")
    ) or amount.as_tuple().exponent < -2:
        raise ValueError("Invalid exact amount")
    user_ids = [user_id for user_id, _ in weights]
    if not weights or len(set(user_ids)) != len(user_ids):
        raise ValueError("Participants must be nonempty and unique")
    if any(type(weight) is not int or weight < 1 for _, weight in weights):
        raise ValueError("Weights must be positive integers")
    units = int(amount * 100)
    total = sum(weight for _, weight in weights)
    floors = {user_id: units * weight // total for user_id, weight in weights}
    remainders = {user_id: units * weight % total for user_id, weight in weights}
    leftover = units - sum(floors.values())
    for user_id in sorted(user_ids, key=lambda user_id: (-remainders[user_id], user_id))[:leftover]:
        floors[user_id] += 1
    return [(user_id, Decimal(floors[user_id]).scaleb(-2)) for user_id in sorted(user_ids)]


def equal_split(amount: Decimal, participant_user_ids: list[int]) -> list[tuple[int, Decimal]]:
    """Distribute exact hundredths, giving the remainder to ascending user IDs."""
    return weighted_split(amount, [(user_id, 1) for user_id in participant_user_ids])


def exact_split(amount: Decimal, amounts: list[tuple[int, Decimal]]) -> list[tuple[int, Decimal]]:
    """Accept typed-in shares only when they add up to the amount exactly."""
    total = sum((share for _, share in amounts), Decimal("0.00"))
    if total != amount:
        raise InvalidExpenseError(f"Exact shares add up to {total:.2f}, not {amount:.2f}")
    return sorted(amounts)


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


def make_splits(
    method: str, amount: Decimal, participants: Optional[list[int]], splits: Optional[list[SplitInput]],
) -> list[ExpenseSplit]:
    if method == "equal":
        return [ExpenseSplit(user_id=user_id, share_amount=share)
                for user_id, share in equal_split(amount, participants or [])]
    if method == "shares":
        weights = {split.user_id: split.weight for split in splits or []}
        return [ExpenseSplit(user_id=user_id, share_amount=share, weight=weights[user_id])
                for user_id, share in weighted_split(amount, list(weights.items()))]
    return [ExpenseSplit(user_id=user_id, share_amount=share)
            for user_id, share in exact_split(amount, [(s.user_id, s.amount) for s in splits or []])]


def split_participants(
    participants: Optional[list[int]], splits: Optional[list[SplitInput]],
) -> list[int]:
    return participants if participants is not None else [split.user_id for split in splits or []]


def resolve_split(
    expense: Expense, payload: ExpenseUpdate, amount: Decimal,
) -> tuple[str, Optional[list[int]], Optional[list[SplitInput]]]:
    """Merge a partial update with the stored split so the result is complete.

    Fields the client did not send are carried over from the stored split:
    participants stay, weights default to 1 when switching to `shares`, and an
    `exact` split keeps its amounts unless the amount changes, which needs new ones.
    """
    method = payload.split_method or expense.split_method
    participants, splits = payload.participant_user_ids, payload.splits
    if method == "equal":
        if splits is not None:
            raise InvalidExpenseError("An equal split takes participant_user_ids, not splits")
        return method, participants or [split.user_id for split in expense.splits], None
    if participants is not None:
        raise InvalidExpenseError(f"A {method} split takes splits, not participant_user_ids")
    if splits is None:
        if method == "shares":
            splits = [SplitInput(user_id=s.user_id, weight=s.weight or 1) for s in expense.splits]
        elif amount != expense.amount:
            raise InvalidExpenseError("Send exact shares when changing the amount of an exact split")
        else:
            splits = [SplitInput(user_id=s.user_id, amount=s.share_amount) for s in expense.splits]
    elif (splits[0].weight is None) == (method == "shares"):
        raise InvalidExpenseError("Shares need a weight per split; exact needs an amount per split")
    return method, None, splits


def create_expense(
    db: Session, trip_id: int, user_id: int, payload: ExpenseCreate,
) -> ExpenseResponse:
    trip = get_accessible_trip(db, trip_id, user_id, for_update=True)
    with expense_errors(db):
        participants = split_participants(payload.participant_user_ids, payload.splits)
        validate_people(db, trip, payload.paid_by_user_id, participants)
        validate_currency(db, trip_id, payload.currency)
        expense = Expense(
            **payload.model_dump(exclude={"participant_user_ids", "splits"}),
            trip_id=trip_id, created_by_user_id=user_id,
            splits=make_splits(
                payload.split_method, payload.amount, payload.participant_user_ids, payload.splits),
        )
        db.add(expense)
        db.flush()
        result = ExpenseResponse.model_validate(expense)
        stage(db, TripEvent(trip_id, "expense", "created", user_id, expense.id, expense.version))
        db.commit()
        return result


def update_expense(
    db: Session, trip_id: int, user_id: int, expense_id: int, payload: ExpenseUpdate,
    expected_version: Optional[int] = None,
) -> ExpenseResponse:
    trip = get_accessible_trip(db, trip_id, user_id, for_update=True)
    with expense_errors(db):
        expense = find_expense(db, trip_id, expense_id)
        require_version(expense, expected_version)
        changes = payload.model_dump(exclude_unset=True, exclude={"participant_user_ids", "splits"})
        amount = changes.get("amount", expense.amount)
        method, participants, splits = resolve_split(expense, payload, amount)
        validate_people(db, trip, changes.get("paid_by_user_id", expense.paid_by_user_id),
                        split_participants(participants, splits))
        validate_currency(db, trip_id, changes.get("currency", expense.currency), expense_id)
        new_splits = make_splits(method, amount, participants, splits)
        # Rewrite the split rows only when the stored ones would actually differ.
        recalculate = method != expense.split_method or [
            (s.user_id, s.share_amount, s.weight) for s in new_splits
        ] != [(s.user_id, s.share_amount, s.weight) for s in expense.splits]
        for field, value in changes.items():
            setattr(expense, field, value)
        if recalculate:
            # Delete old pairs before inserting replacements with the same unique keys.
            expense.splits = []
            expense.split_method = method
            expense.updated_at = func.statement_timestamp()
            db.flush()
            expense.splits = new_splits
        db.flush()
        result = ExpenseResponse.model_validate(expense)
        stage(db, TripEvent(trip_id, "expense", "updated", user_id, expense.id, expense.version))
        db.commit()
        return result


def delete_expense(db: Session, trip_id: int, user_id: int, expense_id: int) -> None:
    get_accessible_trip(db, trip_id, user_id, for_update=True)
    with expense_errors(db):
        expense = find_expense(db, trip_id, expense_id)
        db.delete(expense)
        stage(db, TripEvent(trip_id, "expense", "deleted", user_id, expense_id))
        db.commit()
