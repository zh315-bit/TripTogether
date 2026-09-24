from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.errors import APIError, APIErrorResponse
from app.api.dependencies import get_current_user, unauthorized
from app.core.config import JWTConfigurationError
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.user import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.authentication import (
    AuthenticationUnavailableError,
    InvalidCredentialsError,
    authenticate_user,
)
from app.services.registration import (
    DuplicateUserError,
    RegistrationUnavailableError,
    register_user,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": APIErrorResponse},
        422: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> UserResponse:
    try:
        user = register_user(db, payload)
    except DuplicateUserError as error:
        raise APIError(status_code=409, detail=str(error), code=error.code) from None
    except RegistrationUnavailableError:
        raise APIError(
            status_code=503, detail="Registration temporarily unavailable", code="REGISTRATION_UNAVAILABLE",
        ) from None
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": APIErrorResponse},
        422: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def login(
    payload: UserLogin, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    try:
        user = authenticate_user(db, payload)
        token = create_access_token(user.id)
    except InvalidCredentialsError:
        raise unauthorized("Invalid email or password") from None
    except (AuthenticationUnavailableError, JWTConfigurationError):
        raise APIError(status_code=503, detail="Authentication temporarily unavailable",
                       code="AUTHENTICATION_UNAVAILABLE") from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(access_token=token)


@router.get(
    "/me", response_model=UserResponse,
    responses={401: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def me(response: Response, current_user: User = Depends(get_current_user)) -> UserResponse:
    response.headers["Cache-Control"] = "no-store"
    return UserResponse.model_validate(current_user)
