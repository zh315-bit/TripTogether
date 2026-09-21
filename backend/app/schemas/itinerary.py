from datetime import date, datetime, time
import re
from typing import Annotated, Optional

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints,
    field_validator, model_validator,
)

from app.schemas.trip import CalendarDate


def local_time(value: object) -> object:
    if type(value) is time and value.tzinfo is None:
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]{1,6})?)?", value
    ):
        raise ValueError("Use local HH:MM or HH:MM:SS time without a timezone")
    return value


LocalTime = Annotated[time, BeforeValidator(local_time)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Notes = Annotated[str, StringConstraints(max_length=2000)]
ItemID = Annotated[int, Field(strict=True, ge=1, le=2147483647)]


def validate_times(start: Optional[time], end: Optional[time]) -> None:
    if end is not None and (start is None or end < start):
        raise ValueError("end_time requires start_time and must be on or after it")


class ItineraryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    @field_validator("title", "location", "notes", check_fields=False)
    @classmethod
    def valid_text(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("Text must contain valid Unicode characters") from None
            if "\x00" in value:
                raise ValueError("Text must not contain null characters")
        return value


class ItineraryItemCreate(ItineraryInput):
    title: Title
    date: CalendarDate
    location: Optional[Location] = None
    start_time: Optional[LocalTime] = None
    end_time: Optional[LocalTime] = None
    notes: Optional[Notes] = None

    @model_validator(mode="after")
    def valid_times(self) -> "ItineraryItemCreate":
        validate_times(self.start_time, self.end_time)
        return self


class ItineraryItemUpdate(ItineraryInput):
    title: Optional[Title] = None
    date: Optional[CalendarDate] = None
    location: Optional[Location] = None
    start_time: Optional[LocalTime] = None
    end_time: Optional[LocalTime] = None
    notes: Optional[Notes] = None

    @field_validator("title", "date", mode="before")
    @classmethod
    def required_fields_cannot_be_cleared(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class ItineraryReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    date: CalendarDate
    item_ids: list[ItemID]

    @field_validator("item_ids")
    @classmethod
    def no_duplicates(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("item_ids must not contain duplicates")
        return value


class ItineraryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    title: str
    location: Optional[str]
    date: date
    start_time: Optional[time]
    end_time: Optional[time]
    notes: Optional[str]
    position: int
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
