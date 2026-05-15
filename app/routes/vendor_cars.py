import csv
import hashlib
import io
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_vendor
from app.database import get_db
from app.models.vendor import Vendor
from app.models.vendor_car import VendorCar
from app.schemas.vendor_car import (
    EXPECTED_CSV_COLUMNS,
    CarRowError,
    CarUploadResult,
    PaginatedVendorCars,
    VendorCarOut,
)

router = APIRouter(prefix="/vendor/cars", tags=["vendor:cars"])


# Max upload size (bytes). The CSV is plain text and each row is ~100 bytes;
# 5 MB comfortably covers tens of thousands of rows without letting a bad
# actor stream a giant file.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _parse_int(raw: str, field: str) -> int:
    cleaned = re.sub(r"[^\d-]", "", raw or "")
    if not cleaned:
        raise ValueError(f"{field} is required")
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer, got {raw!r}") from exc


def _parse_cost_lakh(raw: str) -> Decimal:
    cleaned = re.sub(r"[^\d.]", "", raw or "")
    if not cleaned:
        raise ValueError("Cost is required")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Cost must be numeric, got {raw!r}") from exc


def _norm(raw: str | None) -> str:
    return (raw or "").strip()


def _row_hash(values: tuple[str, str, int, int, Decimal, int, str, str, str]) -> str:
    """Stable fingerprint of a normalized row, used as the uniqueness key.

    We hash a pipe-joined string rather than relying on a composite UNIQUE
    on every column so the DB index stays small (64 hex chars) regardless
    of how many fields we end up tracking.
    """
    joined = "|".join(
        [
            values[0].lower(),  # car_name
            values[1].lower(),  # model
            str(values[2]),     # year
            str(values[3]),     # km_driven
            f"{values[4]:.2f}", # cost_lakh
            str(values[5]),     # registration_year
            values[6].lower(),  # transmission
            values[7].lower(),  # fuel_type
            values[8].lower(),  # owner_type
        ]
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _validate_headers(actual: list[str]) -> None:
    expected = set(EXPECTED_CSV_COLUMNS)
    found = {h.strip() for h in actual}
    missing = expected - found
    extra = found - expected
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing columns: {sorted(missing)}")
        if extra:
            parts.append(f"unexpected columns: {sorted(extra)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid CSV header. {'; '.join(parts)}",
        )


@router.get("", response_model=PaginatedVendorCars)
async def list_cars(
    vendor: Vendor = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
    sort_order: Literal["asc", "desc"] = Query("desc"),
) -> PaginatedVendorCars:
    base = select(VendorCar).where(VendorCar.vendor_id == vendor.id)
    if search:
        pattern = f"%{search.strip().lower()}%"
        base = base.where(
            func.lower(VendorCar.car_name).like(pattern)
            | func.lower(VendorCar.model).like(pattern)
        )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    ordered = base.order_by(
        VendorCar.created_at.desc() if sort_order == "desc" else VendorCar.created_at.asc()
    )
    offset = (page - 1) * page_size
    rows = (await db.execute(ordered.offset(offset).limit(page_size))).scalars().all()

    items = [
        VendorCarOut(
            car_id=c.car_id,
            car_name=c.car_name,
            model=c.model,
            year=c.year,
            km_driven=c.km_driven,
            cost_lakh=c.cost_lakh,
            registration_year=c.registration_year,
            transmission=c.transmission,
            fuel_type=c.fuel_type,
            owner_type=c.owner_type,
            created_at=c.created_at,
        )
        for c in rows
    ]
    return PaginatedVendorCars(items=items, total=total, page=page, page_size=page_size)


@router.get("/sample")
async def sample_csv(_: Vendor = Depends(get_current_vendor)) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPECTED_CSV_COLUMNS)
    # A few illustrative rows so the user can see the expected formatting
    # (KM with commas + " km" suffix, Cost with " Lakh" suffix).
    writer.writerow(
        ["Maruti Suzuki Swift VXI", "Swift", 2022, "54,583 km", " 11.8 Lakh", 2022, "Manual", "Petrol", "1st Owner"]
    )
    writer.writerow(
        ["Hyundai Creta SX", "Creta", 2020, "85,079 km", " 6.1 Lakh", 2020, "Automatic", "Diesel", "2nd Owner"]
    )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="vendor-cars-sample.csv"'},
    )


@router.post("/upload", response_model=CarUploadResult)
async def upload_csv(
    file: UploadFile = File(...),
    vendor: Vendor = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db),
) -> CarUploadResult:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded text/CSV",
        )

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV is empty",
        )
    _validate_headers(reader.fieldnames)

    errors: list[CarRowError] = []
    parsed: list[tuple[str, dict, str]] = []  # (row_hash, values_dict, _) per valid row
    seen_hashes: set[str] = set()
    duplicates_in_file = 0
    total_rows = 0

    for idx, raw_row in enumerate(reader, start=2):  # row 2 = first data row
        total_rows += 1
        try:
            car_name = _norm(raw_row.get("Car Name"))
            model = _norm(raw_row.get("Model"))
            transmission = _norm(raw_row.get("Transmission"))
            fuel_type = _norm(raw_row.get("Fuel Type"))
            owner_type = _norm(raw_row.get("Owner Type"))
            if not all([car_name, model, transmission, fuel_type, owner_type]):
                raise ValueError("text fields must not be empty")

            year = _parse_int(raw_row.get("Year", ""), "Year")
            km_driven = _parse_int(raw_row.get("KM Driven", ""), "KM Driven")
            cost_lakh = _parse_cost_lakh(raw_row.get("Cost", ""))
            registration_year = _parse_int(
                raw_row.get("Registration Year", ""), "Registration Year"
            )

            values = (
                car_name, model, year, km_driven, cost_lakh,
                registration_year, transmission, fuel_type, owner_type,
            )
            h = _row_hash(values)
        except (ValueError, KeyError) as exc:
            errors.append(CarRowError(row=idx, message=str(exc)))
            continue

        if h in seen_hashes:
            duplicates_in_file += 1
            continue
        seen_hashes.add(h)
        parsed.append((h, {
            "car_name": car_name,
            "model": model,
            "year": year,
            "km_driven": km_driven,
            "cost_lakh": cost_lakh,
            "registration_year": registration_year,
            "transmission": transmission,
            "fuel_type": fuel_type,
            "owner_type": owner_type,
        }, ""))

    # Cross-check against rows this vendor has already uploaded.
    existing_hashes: set[str] = set()
    if parsed:
        hash_list = [h for h, _, _ in parsed]
        result = await db.execute(
            select(VendorCar.row_hash).where(
                VendorCar.vendor_id == vendor.id,
                VendorCar.row_hash.in_(hash_list),
            )
        )
        existing_hashes = {r[0] for r in result.all()}

    duplicates_in_db = 0
    inserted = 0
    for h, values, _ in parsed:
        if h in existing_hashes:
            duplicates_in_db += 1
            continue
        db.add(
            VendorCar(
                car_id=uuid.uuid4(),
                vendor_id=vendor.id,
                row_hash=h,
                **values,
            )
        )
        inserted += 1

    await db.commit()

    return CarUploadResult(
        total_rows=total_rows,
        inserted=inserted,
        duplicates_in_file=duplicates_in_file,
        duplicates_in_db=duplicates_in_db,
        errors=errors,
    )
