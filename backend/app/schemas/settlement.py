from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from app.schemas.expense import Amount, Currency, MoneyResponse, UserID
from app.schemas.trip import CalendarDate


Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SettlementCreate(BaseModel):
    """A payment made outside the app, recorded so the balances reflect it."""
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    from_user_id: UserID
    to_user_id: UserID
    amount: Amount
    currency: Currency
    paid_on: CalendarDate
    note: Optional[Note] = None

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and "\x00" in value:
            raise ValueError("Text must not contain null characters")
        return value

    @model_validator(mode="after")
    def distinct_parties(self) -> "SettlementCreate":
        if self.from_user_id == self.to_user_id:
            raise ValueError("A payment needs two different members")
        return self


class SettlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trip_id: int
    from_user_id: int
    to_user_id: int
    amount: MoneyResponse
    currency: str
    paid_on: date
    note: Optional[str]
    recorded_by_user_id: int
    created_at: datetime
