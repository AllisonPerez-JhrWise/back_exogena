from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator
from wise_comun.nit import digito_verificacion, separar

from app.modules.clients.models import NIT_PATTERN, CompanyStatus, PersonType, RutStatus
from app.modules.engagements.schemas import (
    EngagementIn,
    EngagementRead,
    PersonRef,
    check_no_repeated_engagements,
)
from app.shared.models import join_name_parts

ResponsibilityCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,2}$")]
GroupName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]


# ── Entrada: POST /clients (asistente "Nuevo cliente") ──────────────────────


class RutIn(BaseModel):
    """Datos del RUT (no editables en el front). Los extrae el microservicio del RUT y
    llegan a través del front: este servicio no procesa el PDF."""

    nit: str = Field(
        pattern=NIT_PATTERN,
        description="Sin dígito de verificación (con puntos o con el DV tras un guion, se limpia)",
    )
    check_digit: str = Field(pattern=r"^[0-9]$")
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

    @model_validator(mode="before")
    @classmethod
    def _clean_nit(cls, data):
        """El NIT como lo transcribe el RUT ("900.123.456-8") queda en solo dígitos y
        su dígito de verificación aparte, con la función común de la plataforma
        (wise_comun.nit.separar): así se escribe igual en todos los servicios."""
        if isinstance(data, dict) and isinstance(data.get("nit"), str):
            nit, dv = separar(data["nit"], data.get("check_digit"))
            data = {**data, "nit": nit, "check_digit": dv}
        return data

    @model_validator(mode="after")
    def _check_rut(self) -> "RutIn":
        if str(digito_verificacion(self.nit)) != self.check_digit:
            raise ValueError("The verification digit (check_digit) does not match the NIT")
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


class CompanyUserIn(BaseModel):
    """Paso 4: un usuario del cliente. Ve solo esta empresa."""

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

    # Paso 1, grupo (opcional): uno existente del catálogo (group_id) o uno nuevo
    # (group_name). Ninguno = la empresa no pertenece a un grupo.
    group_id: UUID | None = None
    group_name: GroupName | None = None
    rut: RutIn
    organization: OrganizationDataIn = Field(default_factory=OrganizationDataIn)
    engagements: list[EngagementIn] = Field(default_factory=list)
    users: list[CompanyUserIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_lists(self) -> "ClientCreate":
        if self.group_id and self.group_name:
            raise ValueError("Send group_id (existing group) or group_name (new group), not both")
        emails = [user.email.lower() for user in self.users]
        if len(set(emails)) != len(emails):
            raise ValueError("users has repeated emails")
        check_no_repeated_engagements(self.engagements)
        return self


class GroupIn(BaseModel):
    name: GroupName


# ── Salida ───────────────────────────────────────────────────────────────────


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool


class GroupListItem(GroupRead):
    companies: int = Field(description="Número de empresas del grupo")


class CompanyRead(BaseModel):
    id: UUID
    group: GroupRead | None = None
    display_name: str = Field(description="Razón social o nombre completo")
    trade_name: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    nit: str
    check_digit: str
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


class CompanyUserRead(BaseModel):
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

    company: CompanyRead
    engagements: list[EngagementRead]
    users: list[CompanyUserRead]


class CompanyListItem(BaseModel):
    """Una fila de la pantalla de clientes (una por empresa)."""

    id: UUID
    display_name: str = Field(description="Empresa: razón social o nombre completo")
    trade_name: str | None = None
    nit: str
    check_digit: str
    group_id: UUID | None = None
    group: str | None = Field(default=None, description="Nombre del grupo, si pertenece a uno")
    active_engagements: int = Field(description="Compromisos por iniciar o en curso")
    rut_generated_at: date | None = Field(default=None, description="RUT generado")
    rut_updated_at: date | None = Field(default=None, description="RUT actualizado")
    rut_date_unknown: bool = Field(description="'Fecha del RUT sin identificar'")
    status: CompanyStatus


class RutVersionRead(BaseModel):
    """Una versión del RUT de la empresa, con los años gravables que cubre."""

    id: UUID
    generated_at: date | None = Field(default=None, description="Fecha de generación del PDF")
    rut_updated_at: date | None = Field(default=None, description="Fecha de actualización")
    covers_from_year: int | None = Field(
        default=None, description="Primer año gravable que cubre (según la actualización)"
    )
    covers_to_year: int | None = Field(
        default=None,
        description="Último año gravable que cubre; vacío = hasta hoy (es la más reciente)",
    )
    is_historical: bool
    uploaded_by: PersonRef | None = Field(default=None, description="Quién la cargó")
    uploaded_at: datetime = Field(description="Cuándo se cargó")


class GroupCompanyItem(BaseModel):
    """Otra empresa del mismo grupo."""

    id: UUID
    display_name: str
    nit: str
    check_digit: str
    status: CompanyStatus


class CompanyDetail(BaseModel):
    """Ficha de la empresa."""

    company: CompanyRead
    status: CompanyStatus
    rut_date_unknown: bool = Field(description="'Fecha del RUT sin identificar'")
    group_companies: list[GroupCompanyItem] = Field(
        description="Las demás empresas del grupo (vacío si no tiene grupo)"
    )
    engagements: list[EngagementRead]
    rut_versions: list[RutVersionRead] = Field(description="De la más reciente a la más antigua")
    users: list[CompanyUserRead]


class NitCheck(BaseModel):
    """Si el NIT ya está registrado en la organización, no se crea un duplicado."""

    exists: bool
    company_id: UUID | None = None
    group_id: UUID | None = None
    display_name: str | None = None
