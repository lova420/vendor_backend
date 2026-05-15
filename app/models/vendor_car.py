import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VendorCar(Base):
    __tablename__ = "vendor_cars"
    __table_args__ = (
        UniqueConstraint("vendor_id", "row_hash", name="uq_vendor_cars_vendor_row"),
    )

    car_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    car_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    km_driven: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_lakh: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    registration_year: Mapped[int] = mapped_column(Integer, nullable=False)
    transmission: Mapped[str] = mapped_column(String(20), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )
