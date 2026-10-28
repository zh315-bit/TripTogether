from datetime import date, datetime
from decimal import Decimal
import re
from typing import Annotated, Literal, Optional

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer,
    StringConstraints, field_validator, model_validator,
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
SplitMethod = Literal["equal", "shares", "exact"]
Weight = Annotated[int, Field(strict=True, ge=1, le=1_000_000)]


class SplitInput(BaseModel):
    """One participant's part: a weight for a `shares` split, an amount for `exact`."""
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    user_id: UserID
    weight: Optional[Weight] = None
    amount: Optional[Amount] = None

    @model_validator(mode="after")
    def weight_or_amount(self) -> "SplitInput":
        if (self.weight is None) == (self.amount is None):
            raise ValueError("Give each split either a weight or an amount, not both")
        return self


Splits = Annotated[list[SplitInput], Field(min_length=1, max_length=200)]


def split_kind(splits: list[SplitInput]) -> str:
    """'shares' when every split has a weight, 'exact' when every split has an amount."""
    kinds = {"shares" if split.weight is not None else "exact" for split in splits}
    if len(kinds) != 1:
        raise ValueError("Splits must all carry weights or all carry amounts")
    return kinds.pop()


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
    def unique_participants(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if value is None:
            return None
        if len(value) != len(set(value)):
            raise ValueError("Participants must be unique")
        return sorted(value)

    @field_validator("splits", check_fields=False)
    @classmethod
    def unique_split_users(cls, value: Optional[list[SplitInput]]) -> Optional[list[SplitInput]]:
        if value is None:
            return None
        if len({split.user_id for split in value}) != len(value):
            raise ValueError("Split participants must be unique")
        split_kind(value)
        return sorted(value, key=lambda split: split.user_id)

    @model_validator(mode="after")
    def consistent_split(self) -> "ExpenseInput":
        """`equal` takes participant_user_ids; `shares` and `exact` take splits."""
        method = getattr(self, "split_method", None)
        participants = getattr(self, "participant_user_ids", None)
        splits = getattr(self, "splits", None)
        if participants is not None and splits is not None:
            raise ValueError("Send either participant_user_ids or splits, not both")
        if method == "equal" and splits is not None:
            raise ValueError("An equal split takes participant_user_ids, not splits")
        if method in ("shares", "exact"):
            if participants is not None:
                raise ValueError(f"A {method} split takes splits, not participant_user_ids")
            if splits is not None and split_kind(splits) != method:
                raise ValueError("Shares need a weight per split; exact needs an amount per split")
        amount = getattr(self, "amount", None)
        if splits is not None and amount is not None and splits[0].amount is not None:
            total = sum((split.amount for split in splits), Decimal("0.00"))
            if total != amount:
                raise ValueError(f"Exact shares add up to {total:.2f}, not {amount:.2f}")
        return self


class ExpenseCreate(ExpenseInput):
    description: Description
    amount: Amount
    currency: Currency
    paid_by_user_id: UserID
    expense_date: CalendarDate
    split_method: SplitMethod = "equal"
    participant_user_ids: Optional[Participants] = None
    splits: Optional[Splits] = None

    @model_validator(mode="after")
    def complete_split(self) -> "ExpenseCreate":
        if self.split_method == "equal" and self.participant_user_ids is None:
            raise ValueError("An equal split needs participant_user_ids")
        if self.split_method != "equal" and self.splits is None:
            raise ValueError(f"A {self.split_method} split needs splits")
        return self


class ExpenseUpdate(ExpenseInput):
    description: Optional[Description] = None
    amount: Optional[Amount] = None
    currency: Optional[Currency] = None
    paid_by_user_id: Optional[UserID] = None
    expense_date: Optional[CalendarDate] = None
    split_method: Optional[SplitMethod] = None
    participant_user_ids: Optional[Participants] = None
    splits: Optional[Splits] = None

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
    weight: Optional[int]


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trip_id: int
    description: str
    amount: MoneyResponse
    currency: str
    paid_by_user_id: int
    expense_date: date
    split_method: SplitMethod
    created_by_user_id: int
    version: int
    created_at: datetime
    updated_at: datetime
    splits: list[ExpenseSplitResponse]
