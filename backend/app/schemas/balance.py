from typing import Optional

from pydantic import BaseModel

from app.schemas.expense import MoneyResponse


class MemberBalance(BaseModel):
    user_id: int
    username: str
    paid: MoneyResponse
    share: MoneyResponse
    balance: MoneyResponse


class SettlementSuggestion(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: MoneyResponse


class BalanceResponse(BaseModel):
    trip_id: int
    currency: Optional[str]
    members: list[MemberBalance]
    suggested_settlements: list[SettlementSuggestion]
