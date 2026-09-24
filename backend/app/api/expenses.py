from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.errors import APIError, APIErrorResponse
from app.api.trips import TripID, trip_http_errors
from app.db.session import get_db
from app.models import User
from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate
from app.services import expenses


router = APIRouter(prefix="/trips/{trip_id}/expenses", tags=["expenses"], responses={
    401: {"model": APIErrorResponse}, 404: {"model": APIErrorResponse},
    409: {"model": APIErrorResponse}, 422: {"model": APIErrorResponse},
    503: {"model": APIErrorResponse},
})


@contextmanager
def expense_http_errors() -> Iterator[None]:
    with trip_http_errors():
        try:
            yield
        except expenses.ExpenseNotFoundError:
            raise APIError(status_code=404, detail="Expense not found", code="EXPENSE_NOT_FOUND") from None
        except expenses.InvalidExpenseError as error:
            raise APIError(status_code=422, detail=[{
                "loc": ["body"], "msg": str(error), "type": "value_error",
            }]) from None
        except expenses.ExpenseCurrencyConflictError:
            raise APIError(status_code=409, detail="Trip expenses must use one currency",
                           code="EXPENSE_CURRENCY_CONFLICT") from None
        except expenses.ExpenseUnavailableError:
            raise APIError(status_code=503, detail="Expenses temporarily unavailable",
                           code="EXPENSES_UNAVAILABLE") from None


@router.post("", response_model=ExpenseResponse, status_code=201)
def create(
    trip_id: TripID, payload: ExpenseCreate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> ExpenseResponse:
    with expense_http_errors():
        return expenses.create_expense(db, trip_id, current_user.id, payload)


@router.get("", response_model=list[ExpenseResponse])
def collection(
    trip_id: TripID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[ExpenseResponse]:
    with expense_http_errors():
        return expenses.list_expenses(db, trip_id, current_user.id)


@router.get("/{expense_id}", response_model=ExpenseResponse)
def detail(
    trip_id: TripID, expense_id: TripID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> ExpenseResponse:
    with expense_http_errors():
        return expenses.get_expense(db, trip_id, current_user.id, expense_id)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
def update(
    trip_id: TripID, expense_id: TripID, payload: ExpenseUpdate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> ExpenseResponse:
    with expense_http_errors():
        return expenses.update_expense(db, trip_id, current_user.id, expense_id, payload)


@router.delete("/{expense_id}", status_code=204)
def delete(
    trip_id: TripID, expense_id: TripID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    with expense_http_errors():
        expenses.delete_expense(db, trip_id, current_user.id, expense_id)
    return Response(status_code=204)
