from contextlib import contextmanager
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import page_params, etag, get_current_user, if_match_version
from app.api.errors import APIError, APIErrorResponse
from app.api.trips import TripID, trip_http_errors
from app.db.session import get_db
from app.services.pagination import Page
from app.models import User
from app.schemas.trip_place import TripPlaceCreate, TripPlaceResponse, TripPlaceUpdate
from app.services import trip_places
from app.services.geocoding import GeocodingService, get_geocoding_service


router = APIRouter(prefix="/trips/{trip_id}/places", tags=["places"], responses={
    401: {"model": APIErrorResponse}, 404: {"model": APIErrorResponse},
    409: {"model": APIErrorResponse}, 412: {"model": APIErrorResponse},
    422: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse},
})


@contextmanager
def place_http_errors() -> Iterator[None]:
    with trip_http_errors():
        try:
            yield
        except trip_places.PlaceNotFoundError:
            raise APIError(status_code=404, detail="Place not found", code="PLACE_NOT_FOUND") from None
        except trip_places.InvalidPlaceError as error:
            raise APIError(status_code=422, detail=[{
                "loc": ["body", "provider"], "msg": str(error), "type": "value_error",
            }]) from None
        except trip_places.PlaceDuplicateError:
            raise APIError(status_code=409, detail="This place is already in the trip",
                           code="PLACE_DUPLICATE") from None
        except trip_places.PlaceUnavailableError:
            raise APIError(status_code=503, detail="Places temporarily unavailable",
                           code="PLACES_UNAVAILABLE") from None


@router.post("", response_model=TripPlaceResponse, status_code=201)
def create(
    trip_id: TripID, payload: TripPlaceCreate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    # The same instance /geocode uses, so what can be searched is what can be saved.
    geocoder: GeocodingService = Depends(get_geocoding_service),
) -> TripPlaceResponse:
    configured = geocoder.provider.name if geocoder.provider is not None else None
    with place_http_errors():
        return TripPlaceResponse.model_validate(
            trip_places.create_place(db, trip_id, current_user.id, payload, configured))


@router.get("", response_model=list[TripPlaceResponse])
def collection(
    trip_id: TripID, response: Response, current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db), page: Page = Depends(page_params),
) -> list[TripPlaceResponse]:
    with place_http_errors():
        rows, total = trip_places.list_places(db, trip_id, current_user.id, page)
    response.headers["X-Total-Count"] = str(total)
    return [TripPlaceResponse.model_validate(place) for place in rows]


@router.get("/{place_id}", response_model=TripPlaceResponse)
def detail(
    trip_id: TripID, place_id: TripID, response: Response,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> TripPlaceResponse:
    with place_http_errors():
        place = TripPlaceResponse.model_validate(
            trip_places.get_place(db, trip_id, current_user.id, place_id))
    response.headers["ETag"] = etag(place.version)
    return place


@router.patch("/{place_id}", response_model=TripPlaceResponse)
def update(
    trip_id: TripID, place_id: TripID, payload: TripPlaceUpdate, response: Response,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    expected_version: Optional[int] = Depends(if_match_version),
) -> TripPlaceResponse:
    with place_http_errors():
        place = TripPlaceResponse.model_validate(trip_places.update_place(
            db, trip_id, current_user.id, place_id, payload, expected_version))
    response.headers["ETag"] = etag(place.version)
    return place


@router.delete("/{place_id}", status_code=204)
def delete(
    trip_id: TripID, place_id: TripID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    with place_http_errors():
        trip_places.delete_place(db, trip_id, current_user.id, place_id)
    return Response(status_code=204)
