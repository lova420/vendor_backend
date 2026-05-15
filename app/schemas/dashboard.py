import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ScanStats(BaseModel):
    total_scans: int               # raw event count (includes reloads)
    unique_visitors: int           # COUNT(DISTINCT ip_hash) — same window as total_scans
    conversion_rate: float         # customers / unique_visitors in same window; 0.0 if no visitors


class KpiCards(BaseModel):
    total_vendors: int
    total_customers: int
    customers_today: int
    customers_this_month: int
    scans: ScanStats               # all-time
    scans_this_month: ScanStats    # current calendar month


class VendorKpiCards(BaseModel):
    total_customers: int
    customers_today: int
    customers_this_week: int
    customers_this_month: int
    scans: ScanStats               # all-time, vendor-scoped
    scans_this_month: ScanStats    # current month, vendor-scoped


class DailyCount(BaseModel):
    day: date
    count: int


class TopVendor(BaseModel):
    vendor_id: uuid.UUID
    vendor_name: str
    customer_count: int


class CategoryCount(BaseModel):
    label: str
    count: int


class LatestCustomerRow(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_name: str
    name: str
    contact_number: str
    budget: str
    looking_to_buy_in: str
    created_at: datetime


class AdminDashboardStats(BaseModel):
    kpi: KpiCards
    daily_last_30_days: list[DailyCount]             # customer registrations
    daily_scans_last_30_days: list[DailyCount]       # raw scan events
    top_vendors: list[TopVendor]
    budget_distribution: list[CategoryCount]
    buy_in_distribution: list[CategoryCount]
    latest_customers: list[LatestCustomerRow]


class VendorLatestCustomerRow(BaseModel):
    id: uuid.UUID
    name: str
    contact_number: str
    budget: str
    looking_to_buy_in: str
    created_at: datetime


class VendorDashboardStats(BaseModel):
    kpi: VendorKpiCards
    daily_last_30_days: list[DailyCount]             # customer registrations (vendor-scoped)
    daily_scans_last_30_days: list[DailyCount]       # raw scan events (vendor-scoped)
    budget_distribution: list[CategoryCount]
    buy_in_distribution: list[CategoryCount]
    latest_customers: list[VendorLatestCustomerRow]
