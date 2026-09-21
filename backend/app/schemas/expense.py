from datetime import date, datetime
from decimal import Decimal
import re
from typing import Annotated, Optional

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer,
    StringConstraints, field_validator,
)

from app.schemas.trip import CalendarDate


def money_input(value: object) -> Decimal:
    if isinstance(value, Decimal):
        if not value.is_finite() or value.as_tuple().exponent < -2:
            raise ValueError("Use a finite decimal with at most two decimal places")
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}(\.[0-9]{1,2})?", value):
        raise ValueError("Send amount as a decimal string with at most two decimal places")
    return Decimal(value)


Amount = Annotated[
    Decimal, BeforeValidator(money_input, json_schema_input_type=str),
    Field(gt=Decimal("0"), le=Decimal("9999999999.99"), allow_inf_nan=False),
]
MoneyResponse = Annotated[
    Decimal, PlainSerializer(lambda value: format(value, ".2f"), return_type=str, when_used="json"),
]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$", min_length=3, max_length=3)]
UserID = Annotated[int, Field(strict=True, ge=1, le=2147483647)]
Participants = Annotated[list[UserID], Field(min_length=1)]


class ExpenseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    @field_validator("description", check_fields=False)
    @classmethod
    def valid_description(cls, value: str) -> str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Text must contain valid Unicode characters") from None
        if "\x00" in value:
            raise ValueError("Text must not contain null characters")
        return value

    @field_validator("participant_user_ids", check_fields=False)
    @classmethod
    def unique_participants(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Participants must be unique")
        return sorted(value)


class ExpenseCreate(ExpenseInput):
    description: Description
    amount: Amount
    currency: Currency
    paid_by_user_id: UserID
    expense_date: CalendarDate
    participant_user_ids: Participants


class ExpenseUpdate(ExpenseInput):
    description: Optional[Description] = None
    amount: Optional[Amount] = None
    currency: Optional[Currency] = None
    paid_by_user_id: Optional[UserID] = None
    expense_date: Optional[CalendarDate] = None
    participant_user_ids: Optional[Participants] = None

    @field_validator("*", mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class ExpenseSplitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    share_amount: MoneyResponse


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trip_id: int
    description: str
    amount: MoneyResponse
    currency: str
    paid_by_user_id: int
    expense_date: date
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
    splits: list[ExpenseSplitResponse]
