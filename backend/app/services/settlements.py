"""Recorded payments between members. They reduce balances; they are not suggestions."""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Expense, Settlement
from app.realtime import TripEvent, stage
from app.schemas.settlement import SettlementCreate
from app.services.expenses import validate_people
from app.services.pagination import Page, paginate
from app.services.trips import get_accessible_trip


class SettlementNotFoundError(Exception):
    pass


class InvalidSettlementError(Exception):
    pass


class SettlementCurrencyConflictError(Exception):
    pass


class SettlementUnavailableError(Exception):
    pass


@contextmanager
def settlement_errors(db: Session) -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError:
        db.rollback()
        raise SettlementUnavailableError() from None
    except (SettlementNotFoundError, InvalidSettlementError, SettlementCurrencyConflictError):
        db.rollback()
        raise


def ledger_currency(db: Session, trip_id: int) -> str:
    """The trip's expense currency; a payment only makes sense against a ledger."""
    currency = db.scalar(select(Expense.currency).where(Expense.trip_id == trip_id).limit(1))
    if currency is None:
        raise SettlementCurrencyConflictError("Record an expense before a payment")
    return currency


def list_settlements(
    db: Session, trip_id: int, user_id: int, page: Page = Page(),
) -> tuple[list[Settlement], int]:
    get_accessible_trip(db, trip_id, user_id)
    with settlement_errors(db):
        return paginate(db, select(Settlement).where(Settlement.trip_id == trip_id).order_by(
            Settlement.paid_on.desc(), Settlement.id.desc()), page)


def create_settlement(db: Session, trip_id: int, user_id: int, payload: SettlementCreate) -> Settlement:
    trip = get_accessible_trip(db, trip_id, user_id, for_update=True)
    with settlement_errors(db):
        try:
            validate_people(db, trip, payload.from_user_id, [payload.to_user_id])
        except Exception as error:  # InvalidExpenseError carries the same meaning here
            raise InvalidSettlementError("Payer and payee must belong to this trip") from error
        if payload.currency != ledger_currency(db, trip_id):
            raise SettlementCurrencyConflictError("Payments must use the trip's expense currency")
        settlement = Settlement(**payload.model_dump(), trip_id=trip_id, recorded_by_user_id=user_id)
        db.add(settlement)
        db.flush()
        stage(db, TripEvent(trip_id, "settlement", "created", user_id, settlement.id))
        db.commit()
        db.refresh(settlement)
        return settlement


def delete_settlement(db: Session, trip_id: int, user_id: int, settlement_id: int) -> None:
    get_accessible_trip(db, trip_id, user_id, for_update=True)
    with settlement_errors(db):
        settlement = db.scalar(select(Settlement).where(
            Settlement.trip_id == trip_id, Settlement.id == settlement_id))
        if settlement is None:
            raise SettlementNotFoundError()
        db.delete(settlement)
        stage(db, TripEvent(trip_id, "settlement", "deleted", user_id, settlement_id))
        db.commit()
