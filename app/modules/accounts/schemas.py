from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)


class NewUserData(BaseModel):
    """Datos para crear un usuario que todavía no entra al sistema (p. ej. usuario de cliente)."""

    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)


class UserRead(BaseModel):
    """Representación pública del usuario. Nunca agregar contraseñas ni identidades aquí."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    first_name: str
    middle_name: str | None = None
    last_name: str
    second_last_name: str | None = None
    # Armado a partir de las partes (propiedad del modelo), listo para mostrar
    full_name: str
    phone: str | None = None
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
    given_name: str | None = None
    family_name: str | None = None
