from datetime import date, datetime
import re
from typing import Annotated, Optional

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, StringConstraints,
    field_validator, model_validator,
)


def calendar_date(value: object) -> object:
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Use a calendar date in YYYY-MM-DD format")
    return value


CalendarDate = Annotated[date, BeforeValidator(calendar_date)]
TripName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Destination = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class TripInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    @field_validator("name", "destination", check_fields=False)
    @classmethod
    def valid_text(cls, value: str) -> str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Text must contain valid Unicode characters") from None
        if "\x00" in value:
            raise ValueError("Text must not contain null characters")
        return value


class TripCreate(TripInput):
    name: TripName
    destination: Destination
    start_date: CalendarDate
    end_date: CalendarDate

    @model_validator(mode="after")
    def valid_date_range(self) -> "TripCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class TripUpdate(TripInput):
    name: Optional[TripName] = None
    destination: Optional[Destination] = None
    start_date: Optional[CalendarDate] = None
    end_date: Optional[CalendarDate] = None

    @field_validator("name", "destination", "start_date", "end_date", mode="before")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        # Omission means preserve the stored value; null cannot clear required fields.
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class TripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    destination: str
    start_date: date
    end_date: date
    owner_id: int
    created_at: datetime
    updated_at: datetime
