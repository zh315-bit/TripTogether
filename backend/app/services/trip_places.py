from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import TripPlace
from app.schemas.trip_place import TripPlaceCreate, TripPlaceUpdate
from app.services.trips import get_accessible_trip


class PlaceNotFoundError(Exception):
    pass


class PlaceUnavailableError(Exception):
    pass


class PlaceDuplicateError(Exception):
    pass


class InvalidPlaceError(Exception):
    pass


@contextmanager
def place_errors(db: Session) -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError:
        db.rollback()
        raise PlaceUnavailableError() from None
    except (PlaceNotFoundError, PlaceDuplicateError, InvalidPlaceError):
        db.rollback()
        raise


def find_place(db: Session, trip_id: int, place_id: int) -> TripPlace:
    # Scoping by trip_id keeps another accessible Trip's place IDs unusable here.
    place = db.scalar(select(TripPlace).where(
        TripPlace.id == place_id, TripPlace.trip_id == trip_id,
    ))
    if place is None:
        raise PlaceNotFoundError()
    return place


def list_places(db: Session, trip_id: int, user_id: int) -> list[TripPlace]:
    get_accessible_trip(db, trip_id, user_id)
    with place_errors(db):
        return list(db.scalars(
            select(TripPlace).where(TripPlace.trip_id == trip_id).order_by(TripPlace.id)
        ))


def get_place(db: Session, trip_id: int, user_id: int, place_id: int) -> TripPlace:
    get_accessible_trip(db, trip_id, user_id)
    with place_errors(db):
        return find_place(db, trip_id, place_id)


def create_place(
    db: Session, trip_id: int, user_id: int, payload: TripPlaceCreate,
    configured_provider: Optional[str] = None,
) -> TripPlace:
    """configured_provider is the active geocoder's name, or None when search is off.

    Only results that geocoder could have returned are accepted, so a production
    pool never holds "fake" rows and a disabled geocoder admits manual places only.
    Application policy, not a database constraint: existing rows stay valid when
    the operator changes GEOCODER_PROVIDER.
    """
    get_accessible_trip(db, trip_id, user_id, for_update=True)
    with place_errors(db):
        if payload.provider is not None and payload.provider != configured_provider:
            raise InvalidPlaceError(
                "provider must match the configured place search "
                f"({configured_provider or 'disabled'}); omit provider for a manual place"
            )
        if payload.provider is not None and db.scalar(select(TripPlace.id).where(
            TripPlace.trip_id == trip_id, TripPlace.provider == payload.provider,
            TripPlace.provider_place_id == payload.provider_place_id,
        )) is not None:
            # The Trip row lock serializes creates, so this check cannot race.
            raise PlaceDuplicateError()
        # Omitted provider falls back to the database default, 'manual'.
        place = TripPlace(**payload.model_dump(exclude_none=True), trip_id=trip_id,
                          proposed_by_user_id=user_id)
        db.add(place)
        db.commit()
        db.refresh(place)
        return place


def update_place(
    db: Session, trip_id: int, user_id: int, place_id: int, payload: TripPlaceUpdate,
) -> TripPlace:
    get_accessible_trip(db, trip_id, user_id, for_update=True)
    with place_errors(db):
        place = find_place(db, trip_id, place_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(place, field, value)
        db.commit()
        db.refresh(place)
        return place


def delete_place(db: Session, trip_id: int, user_id: int, place_id: int) -> None:
    get_accessible_trip(db, trip_id, user_id, for_update=True)
    with place_errors(db):
        # fk_itinerary_trip_place clears linked itinerary place_id values only.
        db.delete(find_place(db, trip_id, place_id))
        db.commit()
