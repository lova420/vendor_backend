import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.database import get_db
from app.models.customer import Customer
from app.models.scan_event import ScanEvent
from app.models.user import UserType
from app.models.vendor import Vendor
from app.schemas.dashboard import (
    AdminDashboardStats,
    CategoryCount,
    DailyCount,
    KpiCards,
    LatestCustomerRow,
    ScanStats,
    TopVendor,
)

router = APIRouter(
    prefix="/admin/dashboard",
    tags=["admin:dashboard"],
    dependencies=[Depends(require_role(UserType.SUPER_ADMIN))],
)


def _dense_daily_series(rows, start: date, days: int = 30) -> list[DailyCount]:
    by_day = {r.day: r.count for r in rows}
    return [
        DailyCount(day=start + timedelta(days=i), count=by_day.get(start + timedelta(days=i), 0))
        for i in range(days)
    ]


async def _scan_stats(
    db: AsyncSession,
    *,
    customer_count: int,
    since: date | None = None,
    vendor_id: uuid.UUID | None = None,
) -> ScanStats:
    scans_q = select(func.count()).select_from(ScanEvent)
    unique_q = select(func.count(distinct(ScanEvent.ip_hash)))
    if since is not None:
        scans_q = scans_q.where(ScanEvent.created_at >= since)
        unique_q = unique_q.where(ScanEvent.created_at >= since)
    if vendor_id is not None:
        scans_q = scans_q.where(ScanEvent.vendor_id == vendor_id)
        unique_q = unique_q.where(ScanEvent.vendor_id == vendor_id)

    total_scans = (await db.execute(scans_q)).scalar_one()
    unique_visitors = (await db.execute(unique_q)).scalar_one() or 0
    conversion = (customer_count / unique_visitors) if unique_visitors > 0 else 0.0

    return ScanStats(
        total_scans=total_scans,
        unique_visitors=unique_visitors,
        conversion_rate=round(conversion, 4),
    )


@router.get("/stats", response_model=AdminDashboardStats)
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    # Optional vendor filter. When set, every aggregation (KPIs, charts,
    # latest registrations) scopes to that vendor only. top_vendors is
    # returned empty in that case — it's a cross-vendor view by nature.
    vendor_id: uuid.UUID | None = Query(None),
) -> AdminDashboardStats:
    today = date.today()
    month_start = today.replace(day=1)
    thirty_days_ago = today - timedelta(days=29)

    if vendor_id is not None:
        exists = (
            await db.execute(
                select(Vendor.id).where(
                    Vendor.id == vendor_id, Vendor.is_deleted.is_(False)
                )
            )
        ).first()
        if exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="vendor_not_found"
            )

    def _scope_customers(stmt):
        if vendor_id is not None:
            return stmt.where(Customer.vendor_id == vendor_id)
        return stmt

    if vendor_id is None:
        total_vendors = (
            await db.execute(
                select(func.count()).select_from(Vendor).where(Vendor.is_deleted.is_(False))
            )
        ).scalar_one()
    else:
        total_vendors = 1

    total_customers = (
        await db.execute(_scope_customers(select(func.count()).select_from(Customer)))
    ).scalar_one()

    customers_today = (
        await db.execute(
            _scope_customers(
                select(func.count())
                .select_from(Customer)
                .where(func.date(Customer.created_at) == today)
            )
        )
    ).scalar_one()

    customers_this_month = (
        await db.execute(
            _scope_customers(
                select(func.count())
                .select_from(Customer)
                .where(Customer.created_at >= month_start)
            )
        )
    ).scalar_one()

    scans_all_time = await _scan_stats(
        db, customer_count=total_customers, since=None, vendor_id=vendor_id
    )
    scans_month = await _scan_stats(
        db, customer_count=customers_this_month, since=month_start, vendor_id=vendor_id
    )

    daily_stmt = (
        select(
            func.date(Customer.created_at).label("day"),
            func.count().label("count"),
        )
        .where(Customer.created_at >= thirty_days_ago)
        .group_by(func.date(Customer.created_at))
        .order_by(func.date(Customer.created_at).asc())
    )
    daily_rows = (await db.execute(_scope_customers(daily_stmt))).all()
    daily_series = _dense_daily_series(daily_rows, thirty_days_ago)

    daily_scan_stmt = (
        select(
            func.date(ScanEvent.created_at).label("day"),
            func.count().label("count"),
        )
        .where(ScanEvent.created_at >= thirty_days_ago)
        .group_by(func.date(ScanEvent.created_at))
        .order_by(func.date(ScanEvent.created_at).asc())
    )
    if vendor_id is not None:
        daily_scan_stmt = daily_scan_stmt.where(ScanEvent.vendor_id == vendor_id)
    daily_scan_rows = (await db.execute(daily_scan_stmt)).all()
    daily_scans_series = _dense_daily_series(daily_scan_rows, thirty_days_ago)

    if vendor_id is None:
        top_rows = (
            await db.execute(
                select(
                    Vendor.id,
                    Vendor.name,
                    func.count(Customer.id).label("count"),
                )
                .join(Customer, Customer.vendor_id == Vendor.id, isouter=True)
                .where(Vendor.is_deleted.is_(False))
                .group_by(Vendor.id, Vendor.name)
                .order_by(func.count(Customer.id).desc())
                .limit(5)
            )
        ).all()
        top_vendors = [
            TopVendor(vendor_id=r.id, vendor_name=r.name, customer_count=r.count)
            for r in top_rows
        ]
    else:
        top_vendors = []

    budget_rows = (
        await db.execute(
            _scope_customers(
                select(Customer.budget, func.count().label("count"))
                .group_by(Customer.budget)
                .order_by(func.count().desc())
            )
        )
    ).all()
    budget_distribution = [
        CategoryCount(label=r.budget, count=r.count) for r in budget_rows
    ]

    buy_in_rows = (
        await db.execute(
            _scope_customers(
                select(Customer.looking_to_buy_in, func.count().label("count"))
                .group_by(Customer.looking_to_buy_in)
                .order_by(func.count().desc())
            )
        )
    ).all()
    buy_in_distribution = [
        CategoryCount(label=r.looking_to_buy_in, count=r.count) for r in buy_in_rows
    ]

    latest_stmt = (
        select(Customer, Vendor.name)
        .join(Vendor, Vendor.id == Customer.vendor_id)
        .order_by(Customer.created_at.desc())
        .limit(10)
    )
    if vendor_id is not None:
        latest_stmt = latest_stmt.where(Customer.vendor_id == vendor_id)
    latest_rows = (await db.execute(latest_stmt)).all()
    latest_customers = [
        LatestCustomerRow(
            id=c.id,
            vendor_id=c.vendor_id,
            vendor_name=vname,
            name=c.name,
            contact_number=c.contact_number,
            budget=c.budget,
            looking_to_buy_in=c.looking_to_buy_in,
            created_at=c.created_at,
        )
        for (c, vname) in latest_rows
    ]

    return AdminDashboardStats(
        kpi=KpiCards(
            total_vendors=total_vendors,
            total_customers=total_customers,
            customers_today=customers_today,
            customers_this_month=customers_this_month,
            scans=scans_all_time,
            scans_this_month=scans_month,
        ),
        daily_last_30_days=daily_series,
        daily_scans_last_30_days=daily_scans_series,
        top_vendors=top_vendors,
        budget_distribution=budget_distribution,
        buy_in_distribution=buy_in_distribution,
        latest_customers=latest_customers,
    )
