import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


BUDGET_OPTIONS: tuple[str, ...] = ("₹3-5L", "₹5-8L", "₹8-12L", "₹12L+")
BUY_IN_OPTIONS: tuple[str, ...] = ("This week", "This month", "Just exploring")

BudgetLiteral = Literal["₹3-5L", "₹5-8L", "₹8-12L", "₹12L+"]
BuyInLiteral = Literal["This week", "This month", "Just exploring"]

_PHONE_PATTERN = re.compile(r"^\d{10}$")


class PublicCustomerCreate(BaseModel):
    vendor_id: uuid.UUID
    name: Annotated[str, Field(min_length=1, max_length=255)]
    contact_number: Annotated[str, Field(min_length=10, max_length=15)]
    budget: BudgetLiteral
    looking_to_buy_in: BuyInLiteral

    @field_validator("contact_number")
    @classmethod
    def _phone_10_digits(cls, v: str) -> str:
        cleaned = re.sub(r"\D", "", v)
        if not _PHONE_PATTERN.match(cleaned):
            raise ValueError("contact_number must be exactly 10 digits")
        return cleaned

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        return cleaned


class PublicVendorInfo(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None = None
    state: str | None = None


class CustomerOut(BaseModel):
    id: uuid.UUID
    name: str
    contact_number: str
    budget: str
    looking_to_buy_in: str
    created_at: datetime


class PaginatedCustomers(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    page_size: int
