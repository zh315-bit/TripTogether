from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.user import NormalizedEmail


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    email: NormalizedEmail


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    inviter_id: int
    invitee_id: int
    status: Literal["pending", "accepted", "rejected"]
    created_at: datetime
    responded_at: Optional[datetime]


class TripMemberResponse(BaseModel):
    user_id: int
    username: str
    email: str
    role: Literal["owner", "member"]
    joined_at: datetime
