from contextlib import contextmanager
from typing import Iterator, Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Trip, TripInvitation, TripMember, User
from app.services.trips import get_owned_trip


class InvitationNotFoundError(Exception):
    pass


class InviteeNotFoundError(Exception):
    pass


class InvitationConflictError(Exception):
    pass


class InvitationUnavailableError(Exception):
    pass


@contextmanager
def invitation_errors(db: Session) -> Iterator[None]:
    try:
        yield
    except IntegrityError as error:
        db.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if getattr(error.orig, "sqlstate", None) == "23505" and constraint in {
            "uq_trip_invitations_pending", "uq_trip_members_trip_user",
        }:
            raise InvitationConflictError("Invitation or membership already exists") from None
        raise InvitationUnavailableError() from None
    except SQLAlchemyError:
        db.rollback()
        raise InvitationUnavailableError() from None
    except (InvitationNotFoundError, InviteeNotFoundError, InvitationConflictError):
        db.rollback()
        raise


def member_exists(db: Session, trip_id: int, user_id: int) -> bool:
    return db.scalar(select(TripMember.id).where(
        TripMember.trip_id == trip_id, TripMember.user_id == user_id
    )) is not None


def create_invitation(
    db: Session, trip_id: int, inviter_id: int, email: str
) -> TripInvitation:
    # All membership mutations lock Trip first, consistent with Trip deletion.
    get_owned_trip(db, trip_id, inviter_id, for_update=True)
    with invitation_errors(db):
        invitee = db.scalar(select(User).where(User.email == email))
        if invitee is None:
            raise InviteeNotFoundError()
        if invitee.id == inviter_id:
            raise InvitationConflictError("Cannot invite yourself")
        if member_exists(db, trip_id, invitee.id):
            raise InvitationConflictError("User is already a trip member")
        pending = db.scalar(select(TripInvitation.id).where(
            TripInvitation.trip_id == trip_id,
            TripInvitation.invitee_id == invitee.id,
            TripInvitation.status == "pending",
        ))
        if pending is not None:
            raise InvitationConflictError("A pending invitation already exists")
        invitation = TripInvitation(
            trip_id=trip_id, inviter_id=inviter_id, invitee_id=invitee.id,
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
        return invitation


def list_invitations(db: Session, user_id: int) -> list[TripInvitation]:
    with invitation_errors(db):
        return list(db.scalars(select(TripInvitation).where(
            TripInvitation.invitee_id == user_id
        ).order_by(TripInvitation.id)))


def respond_to_invitation(
    db: Session, invitation_id: int, user_id: int,
    response: Literal["accepted", "rejected"],
) -> TripInvitation:
    if response not in ("accepted", "rejected"):
        raise ValueError("Unsupported invitation response")
    with invitation_errors(db):
        scope = (
            TripInvitation.id == invitation_id,
            TripInvitation.invitee_id == user_id,
        )
        trip_id = db.scalar(select(TripInvitation.trip_id).where(*scope))
        if trip_id is None:
            raise InvitationNotFoundError()
        trip = db.scalar(select(Trip).where(Trip.id == trip_id).with_for_update())
        if trip is None:
            raise InvitationNotFoundError()
        invitation = db.scalar(select(TripInvitation).where(*scope).with_for_update()
                               .execution_options(populate_existing=True))
        if invitation is None:
            raise InvitationNotFoundError()
        if invitation.status != "pending":
            raise InvitationConflictError("Invitation is no longer pending")
        if response == "accepted":
            if user_id == trip.owner_id or member_exists(db, trip_id, user_id):
                raise InvitationConflictError("User is already a trip member")
            db.add(TripMember(trip_id=trip_id, user_id=user_id, role="member"))
            db.flush()
        # Both changes belong to this transaction; a later failure rolls back the INSERT.
        invitation.status = response
        invitation.responded_at = func.statement_timestamp()
        db.commit()
        db.refresh(invitation)
        return invitation
