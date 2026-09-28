from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=150)


class UserRead(BaseModel):
    """Representación pública del usuario. Nunca agregar hashed_password aquí."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserRead
    # También se envía como cookie HttpOnly. La copia en el body es para un BFF de Next.js
    # (lado servidor) o llamadas entre servicios usando Authorization: Bearer.
    access_token: str
    token_type: str = "bearer"


class GoogleUser(BaseModel):
    id: str
    email: EmailStr
    name: str | None = None
    picture: str | None = None
