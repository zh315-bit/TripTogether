from datetime import date, datetime, time
import re
from typing import Annotated, Optional

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StringConstraints,
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
PlaceID = Annotated[int, Field(strict=True, ge=1, le=2147483647)]


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
    # Links a place from this Trip's pool; location defaults to its name.
    place_id: Optional[PlaceID] = None

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
    # null unlinks the place; location text is left as it is.
    place_id: Optional[PlaceID] = None

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
    # Optional optimistic check: the order the client last saw. A mismatch is 409.
    expected_item_ids: Optional[list[ItemID]] = None

    @field_validator("item_ids", "expected_item_ids")
    @classmethod
    def no_duplicates(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if value is not None and len(value) != len(set(value)):
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
    place_id: Optional[int]
    position: int
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime


class ItineraryOptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    date: CalendarDate
    # Keep the day's first item (often the hotel) as the fixed starting point.
    keep_first: StrictBool = True


class RouteStop(BaseModel):
    item_id: int
    place_id: int
    name: str
    latitude: float
    longitude: float


class RouteLeg(BaseModel):
    from_item_id: int
    to_item_id: int
    distance_km: float


class RouteResponse(BaseModel):
    """Straight-line distances between consecutive located items, in kilometres."""
    date: date
    stops: list[RouteStop]
    legs: list[RouteLeg]
    total_distance_km: float
    unlocated_item_ids: list[int]


class ItineraryOptimizeResponse(BaseModel):
    """A suggestion only; apply it with PATCH /reorder and expected_item_ids."""
    date: date
    keep_first: bool
    changed: bool
    original_item_ids: list[int]
    proposed_item_ids: list[int]
    anchored_item_ids: list[int]
    original_route: RouteResponse
    proposed_route: RouteResponse
