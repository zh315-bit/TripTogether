from contextlib import contextmanager
from datetime import date
from typing import Iterator, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ItineraryItem, Trip, TripPlace
from app.schemas.itinerary import (
    ItineraryItemCreate, ItineraryItemResponse, ItineraryItemUpdate, ItineraryOptimizeRequest,
    ItineraryOptimizeResponse, ItineraryReorderRequest, RouteLeg, RouteResponse, RouteStop,
    validate_times,
)
from app.services import routing
from app.services.trips import get_accessible_trip


MAX_OPTIMIZE_ITEMS = 50


class ItineraryNotFoundError(Exception):
    pass


class InvalidItineraryError(Exception):
    pass


class ItineraryUnavailableError(Exception):
    pass


class ItineraryConflictError(Exception):
    pass


@contextmanager
def itinerary_errors(db: Session) -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError:
        db.rollback()
        raise ItineraryUnavailableError() from None
    except (ItineraryNotFoundError, InvalidItineraryError, ItineraryConflictError):
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


def validate_place(db: Session, trip_id: int, place_id: int) -> TripPlace:
    # Same message whether the ID is missing or another Trip's: existence stays hidden.
    place = db.scalar(select(TripPlace).where(TripPlace.id == place_id, TripPlace.trip_id == trip_id))
    if place is None:
        raise InvalidItineraryError("place_id must reference a place in this trip")
    return place


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
        values = payload.model_dump()
        if payload.place_id is not None:
            place = validate_place(db, trip_id, payload.place_id)
            # location is a text snapshot: later place renames do not rewrite it.
            if values["location"] is None:
                values["location"] = place.name
        item = ItineraryItem(
            **values, trip_id=trip_id, created_by_user_id=user_id,
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
        if changes.get("place_id") is not None:
            validate_place(db, trip_id, changes["place_id"])
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
        current = [item.id for item in items]
        # Checked under the Trip lock, so a preview cannot silently overwrite a newer order.
        if payload.expected_item_ids is not None and current != payload.item_ids:
            if current != payload.expected_item_ids:
                raise ItineraryConflictError()
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


def located_day(db: Session, trip_id: int, day: date) -> list[tuple[ItineraryItem, Optional[TripPlace]]]:
    """One statement, so items and their place coordinates come from one snapshot."""
    return list(db.execute(
        select(ItineraryItem, TripPlace).outerjoin(TripPlace, and_(
            TripPlace.trip_id == ItineraryItem.trip_id, TripPlace.id == ItineraryItem.place_id,
        )).where(ItineraryItem.trip_id == trip_id, ItineraryItem.date == day)
        .order_by(ItineraryItem.position)
    ).tuples())


def build_route(day: date, rows: list[tuple[ItineraryItem, Optional[TripPlace]]]) -> RouteResponse:
    stops = [RouteStop(item_id=item.id, place_id=place.id, name=place.name,
                       latitude=float(place.latitude), longitude=float(place.longitude))
             for item, place in rows if place is not None]
    distances = [routing.haversine_km((a.latitude, a.longitude), (b.latitude, b.longitude))
                 for a, b in zip(stops, stops[1:])]
    return RouteResponse(
        date=day, stops=stops,
        legs=[RouteLeg(from_item_id=a.item_id, to_item_id=b.item_id, distance_km=round(km, 3))
              for (a, b), km in zip(zip(stops, stops[1:]), distances)],
        total_distance_km=round(sum(distances), 3),
        unlocated_item_ids=[item.id for item, place in rows if place is None],
    )


def day_route(db: Session, trip_id: int, user_id: int, day: date) -> RouteResponse:
    trip = get_accessible_trip(db, trip_id, user_id)
    with itinerary_errors(db):
        validate_date(trip, day)
        return build_route(day, located_day(db, trip_id, day))


def optimize_day(
    db: Session, trip_id: int, user_id: int, payload: ItineraryOptimizeRequest,
) -> ItineraryOptimizeResponse:
    """Read-only preview; nothing is written and no lock is taken."""
    trip = get_accessible_trip(db, trip_id, user_id)
    with itinerary_errors(db):
        validate_date(trip, payload.date)
        rows = located_day(db, trip_id, payload.date)
        if len(rows) > MAX_OPTIMIZE_ITEMS:
            raise InvalidItineraryError(f"Route optimization supports at most {MAX_OPTIMIZE_ITEMS} items per day")
        # Timed and unlocated items keep their slots, so appointments never move.
        stops = [routing.Stop(
            item_id=item.id,
            point=(float(place.latitude), float(place.longitude)) if place is not None else None,
            anchored=place is None or item.start_time is not None or (payload.keep_first and index == 0),
        ) for index, (item, place) in enumerate(rows)]
        original = [stop.item_id for stop in stops]
        proposed = routing.propose_order(stops)
        by_id = {item.id: (item, place) for item, place in rows}
        return ItineraryOptimizeResponse(
            date=payload.date, keep_first=payload.keep_first, changed=proposed != original,
            original_item_ids=original, proposed_item_ids=proposed,
            anchored_item_ids=[stop.item_id for stop in stops if stop.anchored],
            original_route=build_route(payload.date, rows),
            proposed_route=build_route(payload.date, [by_id[item_id] for item_id in proposed]),
        )
