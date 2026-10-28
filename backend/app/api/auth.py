from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.errors import APIError, APIErrorResponse
from app.api.dependencies import enforce_rate_limit, get_current_user, unauthorized
from app.core.config import JWTConfigurationError
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.user import (
    DemoLogin, DemoTokenResponse, TokenResponse, UserLogin, UserRegister, UserResponse,
)
from app.services.authentication import (
    AuthenticationUnavailableError,
    InvalidCredentialsError,
    authenticate_user,
)
from app.services.demo import DemoDisabledError, DemoUnavailableError, demo_session
from app.services.rate_limiting import RateLimitUnavailableError
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
        429: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def register(payload: UserRegister, request: Request, db: Session = Depends(get_db)) -> UserResponse:
    try:
        enforce_rate_limit("register", request, db)
        user = register_user(db, payload)
    except DuplicateUserError as error:
        raise APIError(status_code=409, detail=str(error), code=error.code) from None
    except (RegistrationUnavailableError, RateLimitUnavailableError):
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
        429: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def login(
    payload: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    try:
        enforce_rate_limit("login", request, db)
        user = authenticate_user(db, payload)
        token = create_access_token(user.id)
    except InvalidCredentialsError:
        raise unauthorized("Invalid email or password") from None
    except (AuthenticationUnavailableError, RateLimitUnavailableError, JWTConfigurationError):
        raise APIError(status_code=503, detail="Authentication temporarily unavailable",
                       code="AUTHENTICATION_UNAVAILABLE") from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(access_token=token)


@router.post(
    "/demo",
    response_model=DemoTokenResponse,
    summary="Sign in as a demo member",
    responses={
        404: {"model": APIErrorResponse},
        422: {"model": APIErrorResponse},
        429: {"model": APIErrorResponse},
        503: {"model": APIErrorResponse},
    },
)
def demo(
    payload: DemoLogin, request: Request, response: Response, db: Session = Depends(get_db),
) -> DemoTokenResponse:
    """Issues a session for one of three demo members sharing a ready-made trip.

    Only available when DEMO_MODE is set. The trip is rebuilt when it is more
    than six hours old, so visitors can edit freely. Counted against the login limit.
    """
    try:
        enforce_rate_limit("login", request, db)
        session = demo_session(db, payload.member)
        token = create_access_token(session.user.id)
    except DemoDisabledError:
        raise APIError(status_code=404, detail="The demo is not enabled", code="DEMO_DISABLED") from None
    except (DemoUnavailableError, RateLimitUnavailableError, JWTConfigurationError):
        raise APIError(status_code=503, detail="Demo temporarily unavailable",
                       code="DEMO_UNAVAILABLE") from None
    response.headers["Cache-Control"] = "no-store"
    return DemoTokenResponse(access_token=token, member=payload.member,
                             username=session.user.username, trip_id=session.trip_id)


@router.get(
    "/me", response_model=UserResponse,
    responses={401: {"model": APIErrorResponse}, 503: {"model": APIErrorResponse}},
)
def me(response: Response, current_user: User = Depends(get_current_user)) -> UserResponse:
    response.headers["Cache-Control"] = "no-store"
    return UserResponse.model_validate(current_user)
