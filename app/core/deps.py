import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User, UserType
from app.models.vendor import Vendor


@dataclass
class CurrentUser:
    id: uuid.UUID
    email: str
    user_type: UserType


def _extract_token(request: Request) -> str:
    token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if token:
        return token

    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated"
    )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    token = _extract_token(request)
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token"
        )

    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token"
        )

    try:
        user_id = uuid.UUID(user_id_raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token"
        )

    stmt = select(User).where(User.id == user_id, User.is_deleted.is_(False))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found"
        )

    return CurrentUser(id=user.id, email=user.email, user_type=UserType(user.user_type))


def require_role(required: UserType):
    async def _guard(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.user_type != required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        return current

    return _guard


async def get_current_vendor(
    current: CurrentUser = Depends(require_role(UserType.VENDOR_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Vendor:
    stmt = select(Vendor).where(
        Vendor.user_id == current.id, Vendor.is_deleted.is_(False)
    )
    vendor = (await db.execute(stmt)).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="vendor_not_found"
        )
    return vendor
