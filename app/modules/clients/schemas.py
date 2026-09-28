from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, StringConstraints, model_validator

from app.modules.accounts.schemas import NewUserData
from app.modules.clients.models import PersonType, RutStatus
from app.modules.clients.nit import calculate_dv

ResponsibilityCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,2}$")]


# ── Entrada: POST /clients ──────────────────────────────────────────────────


class ClientRutIn(BaseModel):
    """Datos del RUT (no editables en el front).
    Los extrae el microservicio del RUT y llegan a través del front: este servicio no
    procesa el PDF."""

    nit: str = Field(pattern=r"^[0-9]{5,15}$", description="Sin dígito de verificación")
    dv: str = Field(pattern=r"^[0-9]$")
    person_type: PersonType
    # Persona jurídica
    legal_name: str | None = Field(default=None, min_length=1, max_length=250)
    # Persona natural
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=250)
    department_code: str | None = Field(default=None, pattern=r"^[0-9]{2}$")
    city_code: str | None = Field(default=None, pattern=r"^[0-9]{5}$")
    rut_email: EmailStr | None = None
    main_activity_code: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    tax_responsibilities: list[ResponsibilityCode] = Field(default_factory=list)
    rut_status: RutStatus | None = None
    rut_updated_at: date | None = None

    @model_validator(mode="after")
    def _check_rut(self) -> "ClientRutIn":
        if calculate_dv(self.nit) != self.dv:
            raise ValueError("The verification digit (dv) does not match the NIT")
        if self.person_type == PersonType.JURIDICA and not self.legal_name:
            raise ValueError("legal_name is required for a juridica client")
        if self.person_type == PersonType.NATURAL and not (self.first_name and self.last_name):
            raise ValueError("first_name and last_name are required for a natural client")
        # En los códigos DANE, los 2 primeros dígitos del municipio son el departamento
        if self.department_code and self.city_code and self.city_code[:2] != self.department_code:
            raise ValueError("city_code does not belong to department_code")
        if len(set(self.tax_responsibilities)) != len(self.tax_responsibilities):
            raise ValueError("tax_responsibilities has repeated codes")
        return self


class ClientOrganizationIn(BaseModel):
    """Datos de la organización (editables)."""

    trade_name: str | None = Field(default=None, max_length=250)


class ClientUserIn(NewUserData):
    """Un usuario del cliente (paso 4). El contacto principal viene del paso 2."""

    position: str | None = Field(default=None, max_length=100, description="Cargo en la empresa")
    is_primary_contact: bool = False


class ClientCreate(BaseModel):
    """Payload único del formulario "Nuevo cliente"."""

    rut: ClientRutIn
    organization: ClientOrganizationIn = Field(default_factory=ClientOrganizationIn)
    users: list[ClientUserIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_users(self) -> "ClientCreate":
        emails = [user.email.lower() for user in self.users]
        if len(set(emails)) != len(emails):
            raise ValueError("users has repeated emails")
        if sum(user.is_primary_contact for user in self.users) > 1:
            raise ValueError("Only one user can be the primary contact")
        return self


# ── Salida ───────────────────────────────────────────────────────────────────


class ClientUserRead(BaseModel):
    user_id: UUID
    email: EmailStr
    full_name: str
    phone: str | None = None
    position: str | None = None
    is_primary_contact: bool


class ClientRead(BaseModel):
    id: UUID
    nit: str
    dv: str
    person_type: PersonType
    display_name: str = Field(description="Razón social o nombre completo")
    legal_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    second_last_name: str | None = None
    trade_name: str | None = None
    address: str | None = None
    department_code: str | None = None
    city_code: str | None = None
    rut_email: str | None = None
    main_activity_code: str | None = None
    tax_responsibilities: list[str]
    rut_status: RutStatus | None = None
    rut_updated_at: date | None = None
    users: list[ClientUserRead]
    created_at: datetime
