import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserType


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=255)


class LoginUser(BaseModel):
    id: uuid.UUID
    email: EmailStr
    user_type: UserType


class LoginResponse(BaseModel):
    user: LoginUser
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    user_type: UserType
