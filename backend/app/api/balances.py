from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.errors import APIError, ErrorResponse, ValidationErrorResponse
from app.api.trips import TripID, trip_http_errors
from app.db.session import get_db
from app.models import User
from app.schemas.balance import BalanceResponse
from app.services import balances


router = APIRouter(prefix="/trips/{trip_id}/balances", tags=["balances"], responses={
    401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
    409: {"model": ErrorResponse}, 422: {"model": ValidationErrorResponse},
    503: {"model": ErrorResponse},
})


@router.get("", response_model=BalanceResponse)
def detail(
    trip_id: TripID, response: Response,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> BalanceResponse:
    response.headers["Cache-Control"] = "no-store"
    with trip_http_errors():
        try:
            return balances.get_balances(db, trip_id, current_user.id)
        except balances.InconsistentLedgerError:
            raise APIError(status_code=409, detail="Trip expense ledger is inconsistent",
                           code="LEDGER_INCONSISTENT") from None
        except balances.BalanceUnavailableError:
            raise APIError(status_code=503, detail="Balances temporarily unavailable",
                           code="BALANCES_UNAVAILABLE") from None
