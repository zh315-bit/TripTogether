from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.errors import APIError, ErrorResponse, ValidationErrorResponse
from app.api.trips import TripID, trip_http_errors
from app.db.session import get_db
from app.models import User
from app.schemas.itinerary import (
    ItineraryItemCreate, ItineraryItemResponse, ItineraryItemUpdate, ItineraryReorderRequest,
)
from app.services import itinerary


router = APIRouter(prefix="/trips/{trip_id}/itinerary", tags=["itinerary"], responses={
    401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
    422: {"model": ValidationErrorResponse}, 503: {"model": ErrorResponse},
})


@contextmanager
def itinerary_http_errors() -> Iterator[None]:
    with trip_http_errors():
        try:
            yield
        except itinerary.ItineraryNotFoundError:
            raise APIError(status_code=404, detail="Itinerary item not found", code="ITINERARY_NOT_FOUND") from None
        except itinerary.InvalidItineraryError as error:
            raise APIError(status_code=422, detail=[{
                "loc": ["body"], "msg": str(error), "type": "value_error",
            }]) from None
        except itinerary.ItineraryUnavailableError:
            raise APIError(status_code=503, detail="Itinerary temporarily unavailable",
                           code="ITINERARY_UNAVAILABLE") from None


@router.post("", response_model=ItineraryItemResponse, status_code=201)
def create(
    trip_id: TripID, payload: ItineraryItemCreate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> ItineraryItemResponse:
    with itinerary_http_errors():
        return ItineraryItemResponse.model_validate(
            itinerary.create_item(db, trip_id, current_user.id, payload))


@router.get("", response_model=list[ItineraryItemResponse])
def collection(
    trip_id: TripID, current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ItineraryItemResponse]:
    with itinerary_http_errors():
        return [ItineraryItemResponse.model_validate(item)
                for item in itinerary.list_items(db, trip_id, current_user.id)]


@router.patch("/reorder", response_model=list[ItineraryItemResponse])
def reorder(
    trip_id: TripID, payload: ItineraryReorderRequest,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[ItineraryItemResponse]:
    with itinerary_http_errors():
        return [ItineraryItemResponse.model_validate(item)
                for item in itinerary.reorder_items(db, trip_id, current_user.id, payload)]


@router.get("/{item_id}", response_model=ItineraryItemResponse)
def detail(
    trip_id: TripID, item_id: TripID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> ItineraryItemResponse:
    with itinerary_http_errors():
        return ItineraryItemResponse.model_validate(
            itinerary.get_item(db, trip_id, current_user.id, item_id))


@router.patch("/{item_id}", response_model=ItineraryItemResponse)
def update(
    trip_id: TripID, item_id: TripID, payload: ItineraryItemUpdate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> ItineraryItemResponse:
    with itinerary_http_errors():
        return ItineraryItemResponse.model_validate(
            itinerary.update_item(db, trip_id, current_user.id, item_id, payload))


@router.delete("/{item_id}", status_code=204)
def delete(
    trip_id: TripID, item_id: TripID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    with itinerary_http_errors():
        itinerary.delete_item(db, trip_id, current_user.id, item_id)
    return Response(status_code=204)
