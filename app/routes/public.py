import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from app.database import get_db
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.schemas.customer import (
    BUDGET_OPTIONS,
    BUY_IN_OPTIONS,
    PublicCustomerCreate,
    PublicVendorInfo,
)

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/vendors/{vendor_id}", response_model=PublicVendorInfo)
async def get_public_vendor(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PublicVendorInfo:
    # Scan-event logging lives on the /register redirect (app.routes.redirects),
    # which is what the QR actually points at. This endpoint just hydrates the
    # form once the user has already landed on the frontend.
    stmt = select(Vendor).where(
        Vendor.id == vendor_id, Vendor.is_deleted.is_(False)
    )
    vendor = (await db.execute(stmt)).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vendor_not_found"
        )

    return PublicVendorInfo(
        id=vendor.id, name=vendor.name, city=vendor.city, state=vendor.state
    )


@router.post("/customers", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_public_customer(
    request: Request,
    payload: PublicCustomerCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    # Re-validate vendor on the server.
    vendor_stmt = select(Vendor.id).where(
        Vendor.id == payload.vendor_id, Vendor.is_deleted.is_(False)
    )
    if (await db.execute(vendor_stmt)).first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vendor_not_found"
        )

    # Defense-in-depth: ensure budget and buy-in are still in the canonical list.
    # Pydantic Literal already enforces this; the check guards against any future drift.
    if payload.budget not in BUDGET_OPTIONS:
        raise HTTPException(status_code=400, detail="invalid_budget")
    if payload.looking_to_buy_in not in BUY_IN_OPTIONS:
        raise HTTPException(status_code=400, detail="invalid_looking_to_buy_in")

    customer = Customer(
        vendor_id=payload.vendor_id,
        name=payload.name,
        contact_number=payload.contact_number,
        budget=payload.budget,
        looking_to_buy_in=payload.looking_to_buy_in,
    )
    db.add(customer)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(customer)
    return {"id": str(customer.id), "message": "registered"}


@router.get("/options")
async def public_options() -> dict[str, list[str]]:
    """Canonical option lists for the public registration form."""
    return {
        "budget": list(BUDGET_OPTIONS),
        "looking_to_buy_in": list(BUY_IN_OPTIONS),
    }
