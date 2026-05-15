import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_role
from app.core.security import hash_password
from app.database import get_db
from app.models.user import User, UserType
from app.models.vendor import Vendor
from app.schemas.vendor import (
    PaginatedVendors,
    VendorCreate,
    VendorDropdownItem,
    VendorListItem,
    VendorOut,
    VendorUpdate,
)

router = APIRouter(
    prefix="/admin/vendors",
    tags=["admin:vendors"],
    dependencies=[Depends(require_role(UserType.SUPER_ADMIN))],
)


async def _email_exists(db: AsyncSession, email: str, exclude_user_id: uuid.UUID | None = None) -> bool:
    stmt = select(User.id).where(User.email == email)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return (await db.execute(stmt)).first() is not None


async def _load_vendor_with_user(db: AsyncSession, vendor_id: uuid.UUID) -> tuple[Vendor, User]:
    stmt = (
        select(Vendor, User)
        .join(User, User.id == Vendor.user_id)
        .where(Vendor.id == vendor_id, Vendor.is_deleted.is_(False))
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vendor_not_found")
    return row[0], row[1]


def _vendor_to_out(vendor: Vendor, user: User) -> VendorOut:
    return VendorOut(
        id=vendor.id,
        user_id=vendor.user_id,
        name=vendor.name,
        email=user.email,
        location=vendor.location,
        city=vendor.city,
        state=vendor.state,
        pin_code=vendor.pin_code,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
    )


@router.post("", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_role(UserType.SUPER_ADMIN)),
) -> VendorOut:
    email = payload.email.lower()
    if await _email_exists(db, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_already_exists")

    user = User(
        email=email,
        password=hash_password(payload.password),
        user_type=UserType.VENDOR_ADMIN.value,
    )
    db.add(user)
    await db.flush()  # populate user.id

    vendor = Vendor(
        user_id=user.id,
        name=payload.name,
        location=payload.location,
        city=payload.city,
        state=payload.state,
        pin_code=payload.pin_code,
    )
    db.add(vendor)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(vendor)
    await db.refresh(user)
    return _vendor_to_out(vendor, user)


@router.get("", response_model=PaginatedVendors)
async def list_vendors(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
    sort_by: Literal["created_at", "name", "city"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
) -> PaginatedVendors:
    base = select(Vendor, User).join(User, User.id == Vendor.user_id).where(
        Vendor.is_deleted.is_(False)
    )

    if search:
        pattern = f"%{search.strip().lower()}%"
        base = base.where(
            or_(
                func.lower(Vendor.name).like(pattern),
                func.lower(User.email).like(pattern),
                func.lower(func.coalesce(Vendor.city, "")).like(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    sort_col = {
        "created_at": Vendor.created_at,
        "name": Vendor.name,
        "city": Vendor.city,
    }[sort_by]
    base = base.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).all()

    items = [
        VendorListItem(
            id=v.id,
            name=v.name,
            email=u.email,
            city=v.city,
            state=v.state,
            created_at=v.created_at,
        )
        for (v, u) in rows
    ]
    return PaginatedVendors(items=items, total=total, page=page, page_size=page_size)


@router.get("/dropdown", response_model=list[VendorDropdownItem])
async def vendor_dropdown(db: AsyncSession = Depends(get_db)) -> list[VendorDropdownItem]:
    stmt = (
        select(Vendor.id, Vendor.name)
        .where(Vendor.is_deleted.is_(False))
        .order_by(Vendor.name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [VendorDropdownItem(id=r.id, name=r.name) for r in rows]


@router.get("/{vendor_id}", response_model=VendorOut)
async def get_vendor(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> VendorOut:
    vendor, user = await _load_vendor_with_user(db, vendor_id)
    return _vendor_to_out(vendor, user)


@router.put("/{vendor_id}", response_model=VendorOut)
async def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    db: AsyncSession = Depends(get_db),
) -> VendorOut:
    vendor, user = await _load_vendor_with_user(db, vendor_id)

    if payload.email is not None:
        new_email = payload.email.lower()
        if new_email != user.email and await _email_exists(db, new_email, exclude_user_id=user.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="email_already_exists"
            )
        user.email = new_email

    if payload.password is not None:
        user.password = hash_password(payload.password)

    if payload.name is not None:
        vendor.name = payload.name
    if payload.location is not None:
        vendor.location = payload.location
    if payload.city is not None:
        vendor.city = payload.city
    if payload.state is not None:
        vendor.state = payload.state
    if payload.pin_code is not None:
        vendor.pin_code = payload.pin_code

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(vendor)
    await db.refresh(user)
    return _vendor_to_out(vendor, user)


@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    vendor, user = await _load_vendor_with_user(db, vendor_id)

    vendor.is_deleted = True
    user.is_deleted = True

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
