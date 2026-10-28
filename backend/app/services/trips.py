from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ItineraryItem, Trip, TripMember
from app.realtime import TripEvent, stage
from app.schemas.trip import TripCreate, TripUpdate
from app.services.pagination import Page, paginate
from app.services.versioning import require_version


class TripNotFoundError(Exception):
    pass


class InvalidTripDatesError(Exception):
    pass


class TripUnavailableError(Exception):
    pass


class TripItineraryConflictError(Exception):
    pass


@contextmanager
def database_errors(db: Session) -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError:
        db.rollback()
        raise TripUnavailableError() from None
    except (TripNotFoundError, InvalidTripDatesError, TripItineraryConflictError):
        db.rollback()
        raise


def get_owned_trip(
    db: Session, trip_id: int, owner_id: int, *, for_update: bool = False
) -> Trip:
    with database_errors(db):
        statement = select(Trip).where(Trip.id == trip_id, Trip.owner_id == owner_id)
        if for_update:
            statement = statement.with_for_update()
        trip = db.scalar(statement)
        if trip is None:
            raise TripNotFoundError()
        return trip


def create_trip(db: Session, payload: TripCreate, owner_id: int) -> Trip:
    with database_errors(db):
        trip = Trip(**payload.model_dump(), owner_id=owner_id)
        db.add(trip)
        db.flush()
        db.add(TripMember(trip_id=trip.id, user_id=owner_id, role="owner"))
        db.commit()
        db.refresh(trip)
        return trip


def accessible_to(user_id: int):
    membership = select(TripMember.id).where(
        TripMember.trip_id == Trip.id, TripMember.user_id == user_id
    ).exists()
    return or_(Trip.owner_id == user_id, membership)


def get_accessible_trip(
    db: Session, trip_id: int, user_id: int, *, for_update: bool = False,
) -> Trip:
    with database_errors(db):
        statement = select(Trip).where(Trip.id == trip_id, accessible_to(user_id))
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        trip = db.scalar(statement)
        if trip is None:
            raise TripNotFoundError()
        return trip


def list_trips(db: Session, user_id: int, page: Page = Page()) -> tuple[list[Trip], int]:
    with database_errors(db):
        return paginate(db, select(Trip).where(accessible_to(user_id)).order_by(Trip.id), page)


def update_trip(
    db: Session, trip_id: int, owner_id: int, payload: TripUpdate,
    expected_version: Optional[int] = None,
) -> Trip:
    # Lock before merging so concurrent partial updates validate the latest row.
    trip = get_owned_trip(db, trip_id, owner_id, for_update=True)
    with database_errors(db):
        require_version(trip, expected_version)
        changes = payload.model_dump(exclude_unset=True)
        start_date = changes.get("start_date", trip.start_date)
        end_date = changes.get("end_date", trip.end_date)
        if end_date < start_date:
            raise InvalidTripDatesError()
        if start_date != trip.start_date or end_date != trip.end_date:
            outside = db.scalar(select(ItineraryItem.id).where(
                ItineraryItem.trip_id == trip_id,
                or_(ItineraryItem.date < start_date, ItineraryItem.date > end_date),
            ).limit(1))
            if outside is not None:
                raise TripItineraryConflictError()
        for field, value in changes.items():
            setattr(trip, field, value)
        db.flush()
        stage(db, TripEvent(trip_id, "trip", "updated", owner_id, trip.id, trip.version))
        db.commit()
        db.refresh(trip)
        return trip


def delete_trip(db: Session, trip_id: int, owner_id: int) -> None:
    trip = get_owned_trip(db, trip_id, owner_id, for_update=True)
    with database_errors(db):
        db.delete(trip)
        stage(db, TripEvent(trip_id, "trip", "deleted", owner_id, trip_id))
        db.commit()
