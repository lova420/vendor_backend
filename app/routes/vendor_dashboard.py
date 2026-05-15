import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_vendor
from app.database import get_db
from app.models.customer import Customer
from app.models.scan_event import ScanEvent
from app.models.vendor import Vendor
from app.schemas.dashboard import (
    CategoryCount,
    DailyCount,
    ScanStats,
    VendorDashboardStats,
    VendorKpiCards,
    VendorLatestCustomerRow,
)

router = APIRouter(prefix="/vendor/dashboard", tags=["vendor:dashboard"])


def _dense_daily_series(rows, start: date, days: int = 30) -> list[DailyCount]:
    by_day = {r.day: r.count for r in rows}
    return [
        DailyCount(day=start + timedelta(days=i), count=by_day.get(start + timedelta(days=i), 0))
        for i in range(days)
    ]


async def _vendor_scan_stats(
    db: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    customer_count: int,
    since: date | None = None,
) -> ScanStats:
    scans_q = (
        select(func.count())
        .select_from(ScanEvent)
        .where(ScanEvent.vendor_id == vendor_id)
    )
    unique_q = (
        select(func.count(distinct(ScanEvent.ip_hash)))
        .where(ScanEvent.vendor_id == vendor_id)
    )
    if since is not None:
        scans_q = scans_q.where(ScanEvent.created_at >= since)
        unique_q = unique_q.where(ScanEvent.created_at >= since)

    total_scans = (await db.execute(scans_q)).scalar_one()
    unique_visitors = (await db.execute(unique_q)).scalar_one() or 0
    conversion = (customer_count / unique_visitors) if unique_visitors > 0 else 0.0

    return ScanStats(
        total_scans=total_scans,
        unique_visitors=unique_visitors,
        conversion_rate=round(conversion, 4),
    )


@router.get("/stats", response_model=VendorDashboardStats)
async def vendor_stats(
    vendor: Vendor = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db),
) -> VendorDashboardStats:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    month_start = today.replace(day=1)
    thirty_days_ago = today - timedelta(days=29)

    total = (
        await db.execute(
            select(func.count())
            .select_from(Customer)
            .where(Customer.vendor_id == vendor.id)
        )
    ).scalar_one()

    today_count = (
        await db.execute(
            select(func.count())
            .select_from(Customer)
            .where(Customer.vendor_id == vendor.id, func.date(Customer.created_at) == today)
        )
    ).scalar_one()

    week_count = (
        await db.execute(
            select(func.count())
            .select_from(Customer)
            .where(Customer.vendor_id == vendor.id, Customer.created_at >= week_start)
        )
    ).scalar_one()

    month_count = (
        await db.execute(
            select(func.count())
            .select_from(Customer)
            .where(Customer.vendor_id == vendor.id, Customer.created_at >= month_start)
        )
    ).scalar_one()

    scans_all_time = await _vendor_scan_stats(
        db, vendor_id=vendor.id, customer_count=total, since=None
    )
    scans_month = await _vendor_scan_stats(
        db, vendor_id=vendor.id, customer_count=month_count, since=month_start
    )

    daily_rows = (
        await db.execute(
            select(
                func.date(Customer.created_at).label("day"),
                func.count().label("count"),
            )
            .where(
                Customer.vendor_id == vendor.id,
                Customer.created_at >= thirty_days_ago,
            )
            .group_by(func.date(Customer.created_at))
            .order_by(func.date(Customer.created_at).asc())
        )
    ).all()
    daily_series = _dense_daily_series(daily_rows, thirty_days_ago)

    daily_scan_rows = (
        await db.execute(
            select(
                func.date(ScanEvent.created_at).label("day"),
                func.count().label("count"),
            )
            .where(
                ScanEvent.vendor_id == vendor.id,
                ScanEvent.created_at >= thirty_days_ago,
            )
            .group_by(func.date(ScanEvent.created_at))
            .order_by(func.date(ScanEvent.created_at).asc())
        )
    ).all()
    daily_scans_series = _dense_daily_series(daily_scan_rows, thirty_days_ago)

    budget_rows = (
        await db.execute(
            select(Customer.budget, func.count().label("count"))
            .where(Customer.vendor_id == vendor.id)
            .group_by(Customer.budget)
            .order_by(func.count().desc())
        )
    ).all()
    budget_distribution = [CategoryCount(label=r.budget, count=r.count) for r in budget_rows]

    buy_in_rows = (
        await db.execute(
            select(Customer.looking_to_buy_in, func.count().label("count"))
            .where(Customer.vendor_id == vendor.id)
            .group_by(Customer.looking_to_buy_in)
            .order_by(func.count().desc())
        )
    ).all()
    buy_in_distribution = [
        CategoryCount(label=r.looking_to_buy_in, count=r.count) for r in buy_in_rows
    ]

    latest_rows = (
        await db.execute(
            select(Customer)
            .where(Customer.vendor_id == vendor.id)
            .order_by(Customer.created_at.desc())
            .limit(10)
        )
    ).scalars().all()
    latest = [
        VendorLatestCustomerRow(
            id=c.id,
            name=c.name,
            contact_number=c.contact_number,
            budget=c.budget,
            looking_to_buy_in=c.looking_to_buy_in,
            created_at=c.created_at,
        )
        for c in latest_rows
    ]

    return VendorDashboardStats(
        kpi=VendorKpiCards(
            total_customers=total,
            customers_today=today_count,
            customers_this_week=week_count,
            customers_this_month=month_count,
            scans=scans_all_time,
            scans_this_month=scans_month,
        ),
        daily_last_30_days=daily_series,
        daily_scans_last_30_days=daily_scans_series,
        budget_distribution=budget_distribution,
        buy_in_distribution=buy_in_distribution,
        latest_customers=latest,
    )
