from typing import Optional

from pydantic import BaseModel

from app.schemas.expense import MoneyResponse


class MemberBalance(BaseModel):
    user_id: int
    username: str
    paid: MoneyResponse
    share: MoneyResponse
    # Net of recorded payments: positive when the member paid others more than received.
    settled: MoneyResponse
    # paid - share + settled: positive is owed money, negative owes.
    balance: MoneyResponse


class SettlementSuggestion(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: MoneyResponse


class SettlementSummary(BaseModel):
    """How the suggestions were made: how many transfers, for how many members."""
    transfers: int
    unsettled_members: int
    # True when the transfer count is provably the fewest possible (exact search);
    # False when the group was too large and a greedy plan was used instead.
    minimal: bool


class BalanceResponse(BaseModel):
    trip_id: int
    currency: Optional[str]
    members: list[MemberBalance]
    suggested_settlements: list[SettlementSuggestion]
    settlement: SettlementSummary
