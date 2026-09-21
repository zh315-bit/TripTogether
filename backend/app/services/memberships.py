from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import TripMember, User
from app.schemas.membership import TripMemberResponse
from app.services.trips import database_errors, get_accessible_trip


def list_members(db: Session, trip_id: int, user_id: int) -> list[TripMemberResponse]:
    trip = get_accessible_trip(db, trip_id, user_id)
    with database_errors(db):
        # Display role, like write authorization, follows the authoritative owner_id.
        role = case((TripMember.user_id == trip.owner_id, "owner"), else_="member")
        rows = db.execute(select(
            TripMember.user_id, User.username, User.email,
            role.label("role"), TripMember.joined_at,
        ).join(User, User.id == TripMember.user_id).where(
            TripMember.trip_id == trip_id
        ).order_by(TripMember.id)).mappings()
        return [TripMemberResponse.model_validate(row) for row in rows]
