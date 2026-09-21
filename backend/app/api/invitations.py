from contextlib import contextmanager
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.errors import APIError, ErrorResponse, ValidationErrorResponse
from app.api.trips import TripID, trip_http_errors
from app.db.session import get_db
from app.models import User
from app.schemas.membership import InvitationCreate, InvitationResponse
from app.services import invitations


router = APIRouter(tags=["invitations"], responses={
    401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
    409: {"model": ErrorResponse}, 422: {"model": ValidationErrorResponse},
    503: {"model": ErrorResponse},
})
InvitationID = Annotated[int, Path(ge=1, le=2147483647)]


@contextmanager
def invitation_http_errors() -> Iterator[None]:
    with trip_http_errors():
        try:
            yield
        except invitations.InvitationNotFoundError:
            raise APIError(status_code=404, detail="Invitation not found", code="INVITATION_NOT_FOUND") from None
        except invitations.InviteeNotFoundError:
            raise APIError(status_code=404, detail="Registered user not found", code="INVITEE_NOT_FOUND") from None
        except invitations.InvitationConflictError as error:
            raise APIError(status_code=409, detail=str(error), code="INVITATION_CONFLICT") from None
        except invitations.InvitationUnavailableError:
            raise APIError(status_code=503, detail="Invitations temporarily unavailable",
                           code="INVITATIONS_UNAVAILABLE") from None


@router.post("/trips/{trip_id}/invitations", response_model=InvitationResponse, status_code=201)
def create(
    trip_id: TripID, payload: InvitationCreate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> InvitationResponse:
    with invitation_http_errors():
        return InvitationResponse.model_validate(invitations.create_invitation(
            db, trip_id, current_user.id, payload.email,
        ))


@router.get("/invitations", response_model=list[InvitationResponse])
def collection(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[InvitationResponse]:
    with invitation_http_errors():
        return [InvitationResponse.model_validate(row)
                for row in invitations.list_invitations(db, current_user.id)]


@router.post("/invitations/{invitation_id}/accept", response_model=InvitationResponse)
def accept(
    invitation_id: InvitationID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> InvitationResponse:
    with invitation_http_errors():
        return InvitationResponse.model_validate(invitations.respond_to_invitation(
            db, invitation_id, current_user.id, "accepted",
        ))


@router.post("/invitations/{invitation_id}/reject", response_model=InvitationResponse)
def reject(
    invitation_id: InvitationID,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> InvitationResponse:
    with invitation_http_errors():
        return InvitationResponse.model_validate(invitations.respond_to_invitation(
            db, invitation_id, current_user.id, "rejected",
        ))
