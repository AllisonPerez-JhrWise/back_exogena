"""Clientes y empresas, dentro de una organización (la firma).

La jerarquía es: Firma (el tenant de la plataforma) → Clientes → Empresas → Compromisos.
Un cliente NO es un tenant: es un registro de la firma, y los equipos de la firma lo ven.

- Cliente (grupo): un nombre que pone quien lo crea (p. ej. "Grupo Sacyr"), con datos de
  contacto y notas. No tiene NIT. Con una sola empresa, se comporta como ella.
- Empresa: una por NIT (Sacyr Concesiones, Dique, Pacífico…). Lleva los datos del RUT,
  que no se editan a mano (si algo está mal, se carga otro RUT), y sus propios datos de
  contacto y notas, que sí se editan.

Nada se borra: se inactiva con motivo.
"""

from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field

from app.modules.platform.models import platform_fk
from app.shared.models import DB_SCHEMA, BaseTable, join_name_parts


class PersonType(StrEnum):
    """Tipo de persona según el RUT."""

    NATURAL = "natural"
    JURIDICA = "juridica"


class RutStatus(StrEnum):
    """Estado del RUT. La lista se ajusta a los valores que entregue el microservicio del RUT."""

    ACTIVO = "activo"
    SUSPENDIDO = "suspendido"
    CANCELADO = "cancelado"


class CompanyStatus(StrEnum):
    """Estado que muestra la pantalla de clientes (se calcula, no se guarda)."""

    ACTIVO = "activo"
    INACTIVO = "inactivo"
    # RUT generado hace más de rut_renewal_months, o con fecha sin identificar
    RUT_POR_RENOVAR = "rut_por_renovar"


def _active_unique(name: str, *columns: str, where: str = "NOT is_deleted") -> Index:
    """Índice único solo entre filas no borradas (borrado lógico)."""
    return Index(name, *columns, unique=True, postgresql_where=text(where))


class Client(BaseTable):
    """El cliente o grupo de empresas de la firma."""

    __tablename__ = "clients"

    # La firma que atiende al cliente (el tenant de la plataforma)
    organization_id: UUID = Field(foreign_key=platform_fk("tenants"), index=True)
    name: str = Field(max_length=250, description="Nombre del cliente o del grupo")
    # ── Datos de contacto (editables). Se proponen al agregar empresas al grupo ──
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)
    inactivation_reason: str | None = Field(default=None, max_length=500)


class Company(BaseTable):
    """Una empresa (un NIT) de un cliente. El trabajo y la obligación son por NIT."""

    __tablename__ = "companies"
    __table_args__ = (
        # El NIT no se repite dentro de la organización (entre empresas no borradas)
        _active_unique("ux_companies_organization_nit", "organization_id", "nit"),
        CheckConstraint("nit ~ '^[0-9]{5,15}$'", name="nit_digits"),
        CheckConstraint("dv ~ '^[0-9]$'", name="dv_digit"),
        CheckConstraint("person_type IN ('natural', 'juridica')", name="person_type_valid"),
        CheckConstraint("department_code ~ '^[0-9]{2}$'", name="department_code_dane"),
        CheckConstraint("city_code ~ '^[0-9]{5}$'", name="city_code_dane"),
        CheckConstraint("main_activity_code ~ '^[0-9]{4}$'", name="main_activity_code_ciiu"),
        # Jurídica: razón social obligatoria. Natural: primer nombre y primer apellido
        CheckConstraint(
            "(person_type = 'juridica' AND legal_name IS NOT NULL)"
            " OR (person_type = 'natural' AND first_name IS NOT NULL AND last_name IS NOT NULL)",
            name="name_matches_person_type",
        ),
    )

    client_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.clients.id", index=True)
    organization_id: UUID = Field(foreign_key=platform_fk("tenants"), index=True)

    # ── Datos de la organización (editables) ──
    trade_name: str | None = Field(default=None, max_length=250, description="Nombre comercial")
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)

    # ── Datos del RUT vigente (no editables; vienen de la última versión cargada) ──
    # NIT sin DV. En persona natural es el número de identificación
    nit: str = Field(max_length=15)
    dv: str = Field(max_length=1, description="Dígito de verificación")
    person_type: str = Field(max_length=10)
    taxpayer_type: str | None = Field(
        default=None, max_length=100, description="Tipo de contribuyente"
    )
    legal_name: str | None = Field(default=None, max_length=250, description="Razón social")
    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=250)
    # Códigos DANE: los formatos de exógena de la DIAN piden el código, no el nombre
    department_code: str | None = Field(default=None, max_length=2)
    city_code: str | None = Field(default=None, max_length=5)
    rut_email: str | None = Field(default=None, max_length=320)
    rut_phone: str | None = Field(default=None, max_length=30)
    main_activity_code: str | None = Field(default=None, max_length=4, description="Código CIIU")
    rut_status: str | None = Field(default=None, max_length=20)
    # Cuándo se descargó el PDF de la DIAN. NULL = "Fecha del RUT sin identificar"
    rut_generated_at: date | None = None
    # Cuándo el contribuyente actualizó su RUT: desde cuándo rigen estos datos
    rut_updated_at: date | None = None

    inactivation_reason: str | None = Field(default=None, max_length=500)

    @property
    def display_name(self) -> str:
        """Razón social (jurídica) o nombre completo (natural), para mostrar."""
        if self.person_type == PersonType.JURIDICA:
            return self.legal_name or ""
        return join_name_parts(
            self.first_name, self.middle_name, self.last_name, self.second_last_name
        )


class CompanyTaxResponsibility(BaseTable):
    """Responsabilidades tributarias del RUT vigente (05 Renta, 48 IVA, 42 Contabilidad…)."""

    __tablename__ = "company_tax_responsibilities"
    __table_args__ = (
        _active_unique("ux_company_tax_responsibilities_company_code", "company_id", "code"),
        CheckConstraint("code ~ '^[0-9]{1,2}$'", name="code_digits"),
    )

    company_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.companies.id", index=True)
    code: str = Field(max_length=2)


def first_covered_tax_year(rut_updated_at: date) -> int:
    """Año gravable desde el que sirve una versión del RUT: el año de su fecha de
    actualización, o el anterior si cae el 1 de enero (regla de la tarea)."""
    if (rut_updated_at.month, rut_updated_at.day) == (1, 1):
        return rut_updated_at.year - 1
    return rut_updated_at.year


class CompanyRutVersion(BaseTable):
    """Cada RUT cargado de una empresa. El RUT tiene vigencia: para saber qué formatos
    aplican a un año gravable se usa la versión vigente en ese año, no la de hoy."""

    __tablename__ = "company_rut_versions"
    __table_args__ = (
        CheckConstraint("covers_tax_year BETWEEN 1990 AND 2100", name="covers_tax_year_range"),
    )

    company_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.companies.id", index=True)
    # Cuándo se descargó el PDF (valida los 30 días al cargar el RUT actual). NULL = ilegible
    generated_at: date | None = None
    # Cuándo el contribuyente actualizó el RUT (dice para qué años gravables sirve)
    rut_updated_at: date | None = None
    # first_covered_tax_year(rut_updated_at): cubre ese año gravable y los siguientes
    covers_tax_year: int | None = None
    # Histórica: cargada desde la ficha para cubrir un año anterior (sin la regla de 30 días)
    is_historical: bool = Field(default=False)
    # Resultado del microservicio del RUT (public.extracciones) y archivo guardado (F0-05)
    extraction_id: UUID | None = None
    file_key: str | None = Field(default=None, max_length=500)


class ClientUser(BaseTable):
    """Un usuario del cliente (paso 4): quién es, su cargo y su celular en ese cliente.

    Es también la asignación persona ↔ cliente: el rol `cliente` de la plataforma define
    el menú, y esta asignación define qué clientes ve la persona.

    Crear a la persona y su acceso a la firma lo hace la plataforma (POST /tenant/miembros):
    mientras no se integra, `user_id` queda vacío y la fila guarda los datos para invitarla.
    El cargo va aquí porque una persona (p. ej. un revisor fiscal) puede estar en varios
    clientes con un cargo distinto en cada uno."""

    __tablename__ = "client_users"
    __table_args__ = (
        # Una persona una sola vez por cliente
        _active_unique("ux_client_users_client_email", "client_id", "email"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    client_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.clients.id", index=True)
    email: str = Field(max_length=320)
    full_name: str = Field(max_length=200)
    phone: str | None = Field(default=None, max_length=30, description="Celular")
    position: str | None = Field(default=None, max_length=100, description="Cargo en la empresa")
    # La persona en la plataforma (public.users). Vacío = todavía no invitada
    user_id: UUID | None = Field(default=None, foreign_key=platform_fk("users"), index=True)
