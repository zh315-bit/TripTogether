from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.errors import APIError, APIErrorResponse
from app.db.session import get_db
from app.models import User
from app.services import geocoding


router = APIRouter(prefix="/geocode", tags=["geocoding"], responses={
    401: {"model": APIErrorResponse}, 422: {"model": APIErrorResponse},
    429: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse},
})


class GeocodeResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    provider_place_id: str
    name: str
    address: Optional[str]
    latitude: float
    longitude: float


def query_error(message: str) -> APIError:
    return APIError(status_code=422, detail=[{
        "loc": ["query", "q"], "msg": message, "type": "value_error",
    }])


@router.get("", response_model=list[GeocodeResultResponse])
def search(
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: geocoding.GeocodingService = Depends(geocoding.get_geocoding_service),
) -> list[GeocodeResultResponse]:
    """Explicit search only: clients must not call this per keystroke (no autocomplete)."""
    if "\x00" in q:
        raise query_error("Query must not contain null characters")
    if len(geocoding.clean_query(q)) < 2:
        raise query_error("Query must contain at least two non-space characters")
    try:
        results = service.search(db, q, limit)
    except geocoding.GeocoderDisabledError:
        raise APIError(status_code=503, detail="Place search is turned off",
                       code="GEOCODER_DISABLED") from None
    except geocoding.GeocoderBusyError:
        raise APIError(status_code=429, detail="Place search is busy; retry shortly",
                       headers={"Retry-After": "1"}, code="GEOCODER_BUSY") from None
    except geocoding.GeocoderUnavailableError:
        raise APIError(status_code=503, detail="Place search temporarily unavailable",
                       code="GEOCODER_UNAVAILABLE") from None
    return [GeocodeResultResponse.model_validate(result) for result in results]
