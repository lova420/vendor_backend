from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import CurrentUser, get_current_user
from app.core.rate_limit import limiter
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.user import User, UserType
from app.schemas.auth import LoginRequest, LoginResponse, LoginUser, MeResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.JWT_EXPIRY_MINUTES * 60,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    stmt = select(User).where(
        User.email == payload.email.lower(),
        User.is_deleted.is_(False),
    )
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials"
        )

    token = create_access_token(user_id=user.id, user_type=user.user_type)
    _set_auth_cookie(response, token)

    return LoginResponse(
        user=LoginUser(id=user.id, email=user.email, user_type=UserType(user.user_type)),
        access_token=token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    _clear_auth_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse)
async def me(current: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(id=current.id, email=current.email, user_type=current.user_type)
