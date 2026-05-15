import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from app.core.security import hash_ip
from app.database import get_db
from app.models.customer import Customer
from app.models.scan_event import ScanEvent
from app.models.vendor import Vendor
from app.schemas.customer import (
    BUDGET_OPTIONS,
    BUY_IN_OPTIONS,
    PublicCustomerCreate,
    PublicVendorInfo,
)

router = APIRouter(prefix="/public", tags=["public"])
log = logging.getLogger(__name__)


async def _log_scan(
    db: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    request: Request,
) -> None:
    """Best-effort scan logging. Never fails the parent request."""
    try:
        ip = get_remote_address(request) or "0.0.0.0"
        ua = request.headers.get("user-agent")
        if ua and len(ua) > 512:
            ua = ua[:512]

        event = ScanEvent(
            vendor_id=vendor_id,
            ip_hash=hash_ip(ip),
            user_agent=ua,
        )
        db.add(event)
        await db.commit()
    except Exception:  # pragma: no cover - analytics must not break UX
        await db.rollback()
        log.warning("scan_event_log_failed", exc_info=True)


@router.get("/vendors/{vendor_id}", response_model=PublicVendorInfo)
async def get_public_vendor(
    vendor_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PublicVendorInfo:
    stmt = select(Vendor).where(
        Vendor.id == vendor_id, Vendor.is_deleted.is_(False)
    )
    vendor = (await db.execute(stmt)).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="vendor_not_found"
        )

    await _log_scan(db, vendor_id=vendor.id, request=request)

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
