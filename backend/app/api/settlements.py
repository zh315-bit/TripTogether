from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, page_params
from app.api.errors import APIError, APIErrorResponse
from app.api.trips import TripID, trip_http_errors
from app.db.session import get_db
from app.models import User
from app.schemas.settlement import SettlementCreate, SettlementResponse
from app.services import settlements
from app.services.pagination import Page


router = APIRouter(prefix="/trips/{trip_id}/settlements", tags=["balances"], responses={
    401: {"model": APIErrorResponse}, 404: {"model": APIErrorResponse},
    409: {"model": APIErrorResponse}, 422: {"model": APIErrorResponse},
    503: {"model": APIErrorResponse},
})


@contextmanager
def settlement_http_errors() -> Iterator[None]:
    with trip_http_errors():
        try:
            yield
        except settlements.SettlementNotFoundError:
            raise APIError(status_code=404, detail="Payment not found", code="SETTLEMENT_NOT_FOUND") from None
        except settlements.InvalidSettlementError as error:
            raise APIError(status_code=422, detail=[{
                "loc": ["body"], "msg": str(error), "type": "value_error"}]) from None
        except settlements.SettlementCurrencyConflictError as error:
            raise APIError(status_code=409, detail=str(error), code="SETTLEMENT_CURRENCY_CONFLICT") from None
        except settlements.SettlementUnavailableError:
            raise APIError(status_code=503, detail="Payments temporarily unavailable",
                           code="SETTLEMENTS_UNAVAILABLE") from None


@router.post("", response_model=SettlementResponse, status_code=201, summary="Record a payment between members")
def create(
    trip_id: TripID, payload: SettlementCreate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> SettlementResponse:
    with settlement_http_errors():
        return SettlementResponse.model_validate(
            settlements.create_settlement(db, trip_id, current_user.id, payload))


@router.get("", response_model=list[SettlementResponse], summary="List recorded payments")
def collection(
    trip_id: TripID, response: Response, current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db), page: Page = Depends(page_params),
) -> list[SettlementResponse]:
    with settlement_http_errors():
        rows, total = settlements.list_settlements(db, trip_id, current_user.id, page)
    response.headers["X-Total-Count"] = str(total)
    return [SettlementResponse.model_validate(row) for row in rows]


@router.delete("/{settlement_id}", status_code=204, summary="Remove a recorded payment")
def delete(
    trip_id: TripID, settlement_id: TripID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    with settlement_http_errors():
        settlements.delete_settlement(db, trip_id, current_user.id, settlement_id)
    return Response(status_code=204)
