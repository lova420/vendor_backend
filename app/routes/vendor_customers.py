import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_vendor
from app.database import get_db
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.schemas.customer import (
    BUDGET_OPTIONS,
    BUY_IN_OPTIONS,
    CustomerOut,
    PaginatedCustomers,
)

router = APIRouter(prefix="/vendor/customers", tags=["vendor:customers"])


BudgetFilter = Literal["₹3-5L", "₹5-8L", "₹8-12L", "₹12L+"]
BuyInFilter = Literal["This week", "This month", "Just exploring"]


def _apply_filters(
    stmt,
    vendor_id,
    *,
    search: str | None,
    budget: BudgetFilter | None,
    looking_to_buy_in: BuyInFilter | None,
):
    stmt = stmt.where(Customer.vendor_id == vendor_id)
    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Customer.name).like(pattern),
                func.lower(Customer.contact_number).like(pattern),
            )
        )
    if budget:
        stmt = stmt.where(Customer.budget == budget)
    if looking_to_buy_in:
        stmt = stmt.where(Customer.looking_to_buy_in == looking_to_buy_in)
    return stmt


@router.get("", response_model=PaginatedCustomers)
async def list_customers(
    vendor: Vendor = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
    budget: BudgetFilter | None = Query(None),
    looking_to_buy_in: BuyInFilter | None = Query(None),
    sort_order: Literal["asc", "desc"] = Query("desc"),
) -> PaginatedCustomers:
    base = _apply_filters(
        select(Customer),
        vendor.id,
        search=search,
        budget=budget,
        looking_to_buy_in=looking_to_buy_in,
    )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    ordered = base.order_by(
        Customer.created_at.desc() if sort_order == "desc" else Customer.created_at.asc()
    )
    offset = (page - 1) * page_size
    rows = (await db.execute(ordered.offset(offset).limit(page_size))).scalars().all()

    items = [
        CustomerOut(
            id=c.id,
            name=c.name,
            contact_number=c.contact_number,
            budget=c.budget,
            looking_to_buy_in=c.looking_to_buy_in,
            created_at=c.created_at,
        )
        for c in rows
    ]
    return PaginatedCustomers(items=items, total=total, page=page, page_size=page_size)


@router.get("/export")
async def export_customers_csv(
    vendor: Vendor = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None, max_length=255),
    budget: BudgetFilter | None = Query(None),
    looking_to_buy_in: BuyInFilter | None = Query(None),
) -> StreamingResponse:
    stmt = _apply_filters(
        select(Customer),
        vendor.id,
        search=search,
        budget=budget,
        looking_to_buy_in=looking_to_buy_in,
    ).order_by(Customer.created_at.desc())

    rows = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Contact Number", "Budget", "Looking to Buy In", "Created At"])
    for c in rows:
        writer.writerow([
            c.name,
            c.contact_number,
            c.budget,
            c.looking_to_buy_in,
            c.created_at.isoformat(),
        ])

    buf.seek(0)
    filename = f"customers-{vendor.id}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/filter-options")
async def filter_options() -> dict[str, list[str]]:
    return {
        "budget": list(BUDGET_OPTIONS),
        "looking_to_buy_in": list(BUY_IN_OPTIONS),
    }
