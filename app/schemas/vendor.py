import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$"
)


def _validate_password_strength(value: str) -> str:
    if not _PASSWORD_PATTERN.match(value):
        raise ValueError(
            "password must be ≥8 chars and include uppercase, lowercase, digit, and special character"
        )
    return value


def _validate_pin_code(value: float | int | None) -> float | None:
    if value is None:
        return None
    int_val = int(value)
    if int_val != value:
        raise ValueError("pin_code must be a whole number")
    if not (100000 <= int_val <= 999999):
        raise ValueError("pin_code must be 6 digits")
    return float(int_val)


class VendorCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=255)]
    confirm_password: Annotated[str, Field(min_length=8, max_length=255)]
    location: Annotated[str | None, Field(default=None, max_length=255)]
    city: Annotated[str | None, Field(default=None, max_length=100)]
    state: Annotated[str | None, Field(default=None, max_length=100)]
    pin_code: float | int | None = None

    @field_validator("password")
    @classmethod
    def _password_strong(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("pin_code")
    @classmethod
    def _pin_six_digits(cls, v: float | int | None) -> float | None:
        return _validate_pin_code(v)

    @model_validator(mode="after")
    def _passwords_match(self) -> "VendorCreate":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password must match")
        return self


class VendorUpdate(BaseModel):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]
    email: EmailStr | None = None
    password: Annotated[str | None, Field(default=None, min_length=8, max_length=255)]
    confirm_password: Annotated[str | None, Field(default=None, min_length=8, max_length=255)]
    location: Annotated[str | None, Field(default=None, max_length=255)]
    city: Annotated[str | None, Field(default=None, max_length=100)]
    state: Annotated[str | None, Field(default=None, max_length=100)]
    pin_code: float | int | None = None

    @field_validator("password")
    @classmethod
    def _password_strong(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_password_strength(v)

    @field_validator("pin_code")
    @classmethod
    def _pin_six_digits(cls, v: float | int | None) -> float | None:
        return _validate_pin_code(v)

    @model_validator(mode="after")
    def _passwords_match(self) -> "VendorUpdate":
        if self.password is not None and self.password != self.confirm_password:
            raise ValueError("password and confirm_password must match")
        return self


class VendorOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: EmailStr
    location: str | None = None
    city: str | None = None
    state: str | None = None
    pin_code: float | None = None
    created_at: datetime
    updated_at: datetime


class VendorListItem(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    city: str | None = None
    state: str | None = None
    created_at: datetime


class PaginatedVendors(BaseModel):
    items: list[VendorListItem]
    total: int
    page: int
    page_size: int


class VendorDropdownItem(BaseModel):
    id: uuid.UUID
    name: str
