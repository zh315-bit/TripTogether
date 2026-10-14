from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Optional

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator,
)


def coordinate_input(value: object) -> Decimal:
    """Accept JSON numbers only and keep their exact decimal spelling."""
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            # repr() is the shortest round-trip spelling, so 35.7148 stays 35.7148.
            number = Decimal(repr(value))
        except InvalidOperation:
            raise ValueError("Send coordinates as finite JSON numbers") from None
    else:
        raise ValueError("Send coordinates as JSON numbers")
    if not number.is_finite() or number.as_tuple().exponent < -6:
        raise ValueError("Use a finite coordinate with at most six decimal places")
    return number


Latitude = Annotated[
    Decimal, BeforeValidator(coordinate_input, json_schema_input_type=float),
    Field(ge=Decimal("-90"), le=Decimal("90")),
]
Longitude = Annotated[
    Decimal, BeforeValidator(coordinate_input, json_schema_input_type=float),
    Field(ge=Decimal("-180"), le=Decimal("180")),
]
PlaceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Note = Annotated[str, StringConstraints(max_length=500)]


class PlaceInput(BaseModel):
    # extra="forbid" also rejects provider, proposer and timestamp injection.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    @field_validator("name", "address", "note", check_fields=False)
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


class TripPlaceCreate(PlaceInput):
    name: PlaceName
    latitude: Latitude
    longitude: Longitude
    address: Optional[Address] = None
    note: Optional[Note] = None


class TripPlaceUpdate(PlaceInput):
    """Coordinates are immutable: moving a place means deleting and recreating it."""
    name: Optional[PlaceName] = None
    address: Optional[Address] = None
    note: Optional[Note] = None

    @field_validator("name", mode="before")
    @classmethod
    def name_cannot_be_cleared(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class TripPlaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    proposed_by_user_id: int
    name: str
    address: Optional[str]
    # Stored as Numeric(9,6); exposed as JSON numbers for map clients.
    latitude: float
    longitude: float
    provider: str
    provider_place_id: Optional[str]
    note: Optional[str]
    created_at: datetime
    updated_at: datetime
