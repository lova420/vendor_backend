import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


# Exact column names expected in the upload CSV — order is not required,
# but the set of headers must match exactly (case-sensitive, no extras,
# no missing).
EXPECTED_CSV_COLUMNS: tuple[str, ...] = (
    "Car Name",
    "Model",
    "Year",
    "KM Driven",
    "Cost",
    "Registration Year",
    "Transmission",
    "Fuel Type",
    "Owner Type",
)


class VendorCarOut(BaseModel):
    car_id: uuid.UUID
    car_name: str
    model: str
    year: int
    km_driven: int
    cost_lakh: Decimal
    registration_year: int
    transmission: str
    fuel_type: str
    owner_type: str
    created_at: datetime


class PaginatedVendorCars(BaseModel):
    items: list[VendorCarOut]
    total: int
    page: int
    page_size: int


class CarRowError(BaseModel):
    # 1-based row number in the source file (header is row 1, first data row is 2)
    row: int
    message: str


class CarUploadResult(BaseModel):
    total_rows: int
    inserted: int
    duplicates_in_file: int
    duplicates_in_db: int
    errors: list[CarRowError]
