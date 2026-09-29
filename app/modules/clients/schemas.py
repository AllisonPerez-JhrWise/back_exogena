from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.modules.clients.models import CompanyStatus, PersonType, RutStatus
from app.modules.clients.nit import calculate_dv
from app.modules.engagements.schemas import (
    EngagementIn,
    EngagementRead,
    check_no_repeated_engagements,
)
from app.shared.models import join_name_parts

ResponsibilityCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,2}$")]


# ── Entrada: POST /clients (asistente "Nuevo cliente") ──────────────────────


class RutIn(BaseModel):
    """Datos del RUT (no editables en el front). Los extrae el microservicio del RUT y
    llegan a través del front: este servicio no procesa el PDF."""

    nit: str = Field(
        pattern=r"^[0-9]{5,15}$",
        description="Sin dígito de verificación. En persona natural, el número de identificación",
    )
    dv: str = Field(pattern=r"^[0-9]$")
    person_type: PersonType
    taxpayer_type: str | None = Field(default=None, max_length=100)
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
    rut_phone: str | None = Field(default=None, max_length=30)
    main_activity_code: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    tax_responsibilities: list[ResponsibilityCode] = Field(default_factory=list)
    rut_status: RutStatus
    generated_at: date = Field(description="'Fecha generación documento PDF' (pie del RUT)")
    rut_updated_at: date | None = Field(default=None, description="Fecha de actualización")

    @model_validator(mode="after")
    def _check_rut(self) -> "RutIn":
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


class OrganizationDataIn(BaseModel):
    """Paso 2, datos propios de la organización (editables después)."""

    trade_name: str | None = Field(default=None, max_length=250)
    contact_name: str | None = Field(default=None, max_length=200, description="Contacto principal")
    contact_email: EmailStr | None = Field(default=None, description="Correo de contacto")
    contact_phone: str | None = Field(default=None, max_length=30, description="Teléfono")
    notes: str | None = Field(default=None, max_length=2000)


class ClientUserIn(BaseModel):
    """Paso 4: un usuario del cliente, con acceso a todas sus empresas."""

    email: EmailStr
    # La plataforma guarda un solo campo full_name; se arma con estas partes
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30, description="Celular")
    position: str | None = Field(default=None, max_length=100, description="Cargo en la empresa")

    @property
    def full_name(self) -> str:
        return join_name_parts(
            self.first_name, self.middle_name, self.last_name, self.second_last_name
        )


class ClientCreate(BaseModel):
    """Payload único del asistente "Nuevo cliente". Los pasos 3 y 4 son opcionales."""

    # Paso 1: vacío = cliente nuevo; un id = agregar la empresa a ese cliente (grupo)
    client_id: UUID | None = None
    # Solo para un cliente nuevo: el nombre del grupo (p. ej. "Grupo Sacyr"). Vacío = el
    # nombre de la empresa (un cliente con una sola empresa se comporta como ella)
    client_name: str | None = Field(default=None, min_length=1, max_length=250)
    rut: RutIn
    organization: OrganizationDataIn = Field(default_factory=OrganizationDataIn)
    engagements: list[EngagementIn] = Field(default_factory=list)
    users: list[ClientUserIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_lists(self) -> "ClientCreate":
        if self.client_id and self.client_name:
            raise ValueError("client_name only applies to a new client (without client_id)")
        emails = [user.email.lower() for user in self.users]
        if len(set(emails)) != len(emails):
            raise ValueError("users has repeated emails")
        check_no_repeated_engagements(self.engagements)
        return self


# ── Salida ───────────────────────────────────────────────────────────────────


class ClientRead(BaseModel):
    """El cliente o grupo."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str = Field(description="Nombre del cliente o del grupo")
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    is_active: bool


class CompanyRead(BaseModel):
    id: UUID
    client_id: UUID
    display_name: str = Field(description="Razón social o nombre completo")
    trade_name: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    nit: str
    dv: str
    person_type: PersonType
    taxpayer_type: str | None = None
    legal_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    second_last_name: str | None = None
    address: str | None = None
    department_code: str | None = None
    city_code: str | None = None
    rut_email: str | None = None
    rut_phone: str | None = None
    main_activity_code: str | None = None
    tax_responsibilities: list[str]
    rut_status: RutStatus | None = None
    rut_generated_at: date | None = Field(default=None, description="RUT generado")
    rut_updated_at: date | None = Field(default=None, description="RUT actualizado")
    is_active: bool
    created_at: datetime


class ClientUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    phone: str | None = None
    position: str | None = None
    user_id: UUID | None = Field(
        default=None,
        description="La persona en la plataforma. Vacío = pendiente de invitar",
    )


class ClientCreated(BaseModel):
    """Resultado del asistente: todo lo que se creó en la misma operación."""

    client: ClientRead
    company: CompanyRead
    engagements: list[EngagementRead]
    users: list[ClientUserRead]


class ClientSearchItem(BaseModel):
    """Para el buscador "Agregar a un cliente existente" (paso 1)."""

    id: UUID
    name: str
    companies: int = Field(description="Número de empresas del cliente")
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class CompanyListItem(BaseModel):
    """Una fila de la pantalla de clientes (una por empresa)."""

    id: UUID
    client_id: UUID
    display_name: str = Field(description="Empresa: razón social o nombre completo")
    trade_name: str | None = None
    nit: str
    dv: str
    group: str | None = Field(
        default=None, description="Nombre del cliente, solo si tiene varias empresas"
    )
    active_engagements: int = Field(description="Compromisos por iniciar o en curso")
    rut_generated_at: date | None = Field(default=None, description="RUT generado")
    rut_updated_at: date | None = Field(default=None, description="RUT actualizado")
    rut_date_unknown: bool = Field(description="'Fecha del RUT sin identificar'")
    status: CompanyStatus


class NitCheck(BaseModel):
    """Si el NIT ya está registrado en la organización, no se crea un duplicado."""

    exists: bool
    company_id: UUID | None = None
    client_id: UUID | None = None
    display_name: str | None = None
