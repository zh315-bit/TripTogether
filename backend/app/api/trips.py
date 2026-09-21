from contextlib import contextmanager
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.errors import APIError, ErrorResponse, ValidationErrorResponse
from app.db.session import get_db
from app.models import User
from app.schemas.trip import TripCreate, TripResponse, TripUpdate
from app.schemas.membership import TripMemberResponse
from app.services.memberships import list_members
from app.services import trips


router = APIRouter(
    prefix="/trips", tags=["trips"],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ValidationErrorResponse},
        503: {"model": ErrorResponse},
    },
)
TripID = Annotated[int, Path(ge=1, le=2147483647)]


@contextmanager
def trip_http_errors() -> Iterator[None]:
    """Translate shared Trip service errors without exposing resource existence."""
    try:
        yield
    except trips.TripNotFoundError:
        raise APIError(status_code=404, detail="Trip not found", code="TRIP_NOT_FOUND") from None
    except trips.TripItineraryConflictError:
        raise APIError(
            status_code=409, detail="Existing itinerary falls outside the requested trip dates",
            code="TRIP_ITINERARY_CONFLICT",
        ) from None
    except trips.InvalidTripDatesError:
        raise APIError(status_code=422, detail=[{
            "loc": ["body", "end_date"],
            "msg": "end_date must be on or after start_date",
            "type": "value_error",
        }]) from None
    except trips.TripUnavailableError:
        raise APIError(status_code=503, detail="Trips temporarily unavailable", code="TRIPS_UNAVAILABLE") from None


@router.post("", response_model=TripResponse, status_code=201)
def create(
    payload: TripCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TripResponse:
    with trip_http_errors():
        return TripResponse.model_validate(trips.create_trip(db, payload, current_user.id))


@router.get("", response_model=list[TripResponse])
def collection(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[TripResponse]:
    with trip_http_errors():
        return [TripResponse.model_validate(trip) for trip in trips.list_trips(db, current_user.id)]


@router.get("/{trip_id}", response_model=TripResponse)
def detail(
    trip_id: TripID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TripResponse:
    with trip_http_errors():
        return TripResponse.model_validate(trips.get_accessible_trip(db, trip_id, current_user.id))


@router.get("/{trip_id}/members", response_model=list[TripMemberResponse])
def members(
    trip_id: TripID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TripMemberResponse]:
    with trip_http_errors():
        return list_members(db, trip_id, current_user.id)


@router.patch("/{trip_id}", response_model=TripResponse)
def update(
    trip_id: TripID, payload: TripUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TripResponse:
    with trip_http_errors():
        return TripResponse.model_validate(trips.update_trip(db, trip_id, current_user.id, payload))


@router.delete("/{trip_id}", status_code=204)
def delete(
    trip_id: TripID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    with trip_http_errors():
        trips.delete_trip(db, trip_id, current_user.id)
    return Response(status_code=204)
