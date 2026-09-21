from contextlib import contextmanager
from datetime import date
from typing import Iterator

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ItineraryItem, Trip
from app.schemas.itinerary import (
    ItineraryItemCreate, ItineraryItemResponse, ItineraryItemUpdate, ItineraryReorderRequest, validate_times,
)
from app.services.trips import get_accessible_trip


class ItineraryNotFoundError(Exception):
    pass


class InvalidItineraryError(Exception):
    pass


class ItineraryUnavailableError(Exception):
    pass


@contextmanager
def itinerary_errors(db: Session) -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError:
        db.rollback()
        raise ItineraryUnavailableError() from None
    except (ItineraryNotFoundError, InvalidItineraryError):
        db.rollback()
        raise


def validate_date(trip: Trip, day: date) -> None:
    if not trip.start_date <= day <= trip.end_date:
        raise InvalidItineraryError("date must be inside the trip date range")


def day_items(db: Session, trip_id: int, day: date) -> list[ItineraryItem]:
    return list(db.scalars(select(ItineraryItem).where(
        ItineraryItem.trip_id == trip_id, ItineraryItem.date == day,
    ).order_by(ItineraryItem.position)))


def find_item(db: Session, trip_id: int, item_id: int) -> ItineraryItem:
    item = db.scalar(select(ItineraryItem).where(
        ItineraryItem.id == item_id, ItineraryItem.trip_id == trip_id,
    ))
    if item is None:
        raise ItineraryNotFoundError()
    return item


def next_position(db: Session, trip_id: int, day: date) -> int:
    maximum = db.scalar(select(func.max(ItineraryItem.position)).where(
        ItineraryItem.trip_id == trip_id, ItineraryItem.date == day,
    ))
    return (maximum or 0) + 1


def assign_positions(db: Session, items: list[ItineraryItem]) -> None:
    if all(item.position == index for index, item in enumerate(items, 1)):
        return
    # Vacate all final slots before swaps; both flushes remain in one transaction.
    offset = max((item.position for item in items), default=0)
    for index, item in enumerate(items, 1):
        item.position = offset + index
    db.flush()
    for index, item in enumerate(items, 1):
        item.position = index
    db.flush()


def list_items(db: Session, trip_id: int, user_id: int) -> list[ItineraryItem]:
    get_accessible_trip(db, trip_id, user_id)
    with itinerary_errors(db):
        return list(db.scalars(select(ItineraryItem).where(
            ItineraryItem.trip_id == trip_id,
        ).order_by(ItineraryItem.date, ItineraryItem.position)))


def get_item(db: Session, trip_id: int, user_id: int, item_id: int) -> ItineraryItem:
    get_accessible_trip(db, trip_id, user_id)
    with itinerary_errors(db):
        return find_item(db, trip_id, item_id)


def create_item(
    db: Session, trip_id: int, user_id: int, payload: ItineraryItemCreate,
) -> ItineraryItem:
    trip = get_accessible_trip(db, trip_id, user_id, for_update=True)
    with itinerary_errors(db):
        validate_date(trip, payload.date)
        item = ItineraryItem(
            **payload.model_dump(), trip_id=trip_id, created_by_user_id=user_id,
            position=next_position(db, trip_id, payload.date),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item


def update_item(
    db: Session, trip_id: int, user_id: int, item_id: int, payload: ItineraryItemUpdate,
) -> ItineraryItem:
    trip = get_accessible_trip(db, trip_id, user_id, for_update=True)
    with itinerary_errors(db):
        item = find_item(db, trip_id, item_id)
        changes = payload.model_dump(exclude_unset=True)
        day = changes.get("date", item.date)
        validate_date(trip, day)
        try:
            validate_times(changes.get("start_time", item.start_time),
                           changes.get("end_time", item.end_time))
        except ValueError as error:
            raise InvalidItineraryError(str(error)) from None
        old_day = item.date
        if day != old_day:
            item.position = next_position(db, trip_id, day)
        for field, value in changes.items():
            setattr(item, field, value)
        db.flush()
        if day != old_day:
            assign_positions(db, day_items(db, trip_id, old_day))
        db.commit()
        db.refresh(item)
        return item


def delete_item(db: Session, trip_id: int, user_id: int, item_id: int) -> None:
    get_accessible_trip(db, trip_id, user_id, for_update=True)
    with itinerary_errors(db):
        item = find_item(db, trip_id, item_id)
        day = item.date
        db.delete(item)
        db.flush()
        assign_positions(db, day_items(db, trip_id, day))
        db.commit()


def reorder_items(
    db: Session, trip_id: int, user_id: int, payload: ItineraryReorderRequest,
) -> list[ItineraryItemResponse]:
    trip = get_accessible_trip(db, trip_id, user_id, for_update=True)
    with itinerary_errors(db):
        validate_date(trip, payload.date)
        items = day_items(db, trip_id, payload.date)
        by_id = {item.id: item for item in items}
        if len(payload.item_ids) != len(items) or set(payload.item_ids) != set(by_id):
            raise InvalidItineraryError("item_ids must contain every item for this trip and date exactly once")
        ordered = [by_id[item_id] for item_id in payload.item_ids]
        assign_positions(db, ordered)
        # Refresh server-generated timestamps in bulk, then detach the locked result.
        final_items = db.scalars(select(ItineraryItem).where(
            ItineraryItem.trip_id == trip_id, ItineraryItem.date == payload.date,
        ).order_by(ItineraryItem.position).execution_options(populate_existing=True))
        result = [ItineraryItemResponse.model_validate(item) for item in final_items]
        db.commit()
        return result
