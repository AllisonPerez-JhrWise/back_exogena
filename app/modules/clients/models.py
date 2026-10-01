"""Registro de clientes, dentro de una organización (la firma, el tenant de la plataforma).

- Empresa: cada cliente, uno por NIT (Sacyr Concesiones, Dique, Pacífico…). Lleva los
  datos del RUT, que no se editan a mano (si algo está mal, se carga otro RUT), y sus
  propios datos de contacto y notas, que sí se editan.
- Grupo: opcional, junta varias empresas de un mismo cliente (p. ej. "Grupo Sacyr"). Es
  solo un nombre, sin NIT. Se elige de un catálogo de la firma, o se agrega si no está:
  así nadie escribe dos veces el mismo grupo con otra ortografía.

Nada se borra: se inactiva con motivo.
"""

import re
import unicodedata
from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field

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


def group_name_key(name: str) -> str:
    """Clave para comparar nombres de grupo: sin tildes, en minúsculas y con un solo
    espacio entre palabras. "  GRUPO   Sacýr " y "Grupo Sacyr" son el mismo grupo."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


class Group(BaseTable):
    """Catálogo de grupos de la firma: junta varias empresas de un mismo cliente."""

    __tablename__ = "groups"
    __table_args__ = (
        # El mismo grupo no se repite en la firma, aunque se escriba distinto
        _active_unique("ux_groups_organization_name_key", "organization_id", "name_key"),
    )

    # La firma (el tenant de la plataforma). IDs de Identidad sin FK: ese schema no es de
    # este servicio (así lo hacen todos los servicios de la plataforma)
    organization_id: UUID = Field(index=True)
    name: str = Field(max_length=250, description="Como lo escribió quien lo creó")
    # group_name_key(name): lo que se compara para no repetir el grupo
    name_key: str = Field(max_length=250)
    inactivation_reason: str | None = Field(default=None, max_length=500)


class Company(BaseTable):
    """Un cliente: una empresa (un NIT). El trabajo y la obligación son por NIT."""

    __tablename__ = "companies"
    __table_args__ = (
        # El NIT no se repite dentro de la organización (entre empresas no borradas)
        _active_unique("ux_companies_organization_nit", "organization_id", "nit"),
        CheckConstraint("nit ~ '^[0-9]{5,15}$'", name="nit_digits"),
        CheckConstraint("check_digit ~ '^[0-9]$'", name="check_digit_digit"),
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

    organization_id: UUID = Field(index=True)
    # Vacío = la empresa no pertenece a ningún grupo
    group_id: UUID | None = Field(default=None, foreign_key=f"{DB_SCHEMA}.groups.id", index=True)

    # ── Datos de la organización (editables) ──
    trade_name: str | None = Field(default=None, max_length=250, description="Nombre comercial")
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)

    # ── Datos del RUT vigente (no editables; vienen de la última versión cargada) ──
    # NIT sin DV. En persona natural es el número de identificación
    nit: str = Field(max_length=15)
    check_digit: str = Field(max_length=1, description="Dígito de verificación")
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


class CompanyUser(BaseTable):
    """Un usuario del cliente (paso 4): quién es, su cargo y su celular en esa empresa.

    Ve solo esa empresa, aunque pertenezca a un grupo; se le pueden dar otras después.
    Es la asignación persona ↔ empresa: el rol `cliente` de la plataforma define el menú, y
    esta asignación, qué empresas ve.

    Crear a la persona y su acceso a la firma lo hace Identidad (POST
    /organizacion/miembros): mientras no se integra, `user_id` queda vacío y la fila guarda
    los datos para invitarla. El cargo va aquí porque una persona (p. ej. un revisor
    fiscal) puede estar en varias empresas con un cargo distinto en cada una."""

    __tablename__ = "company_users"
    __table_args__ = (
        # Una persona una sola vez por empresa
        _active_unique("ux_company_users_company_email", "company_id", "email"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    company_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.companies.id", index=True)
    email: str = Field(max_length=320)
    full_name: str = Field(max_length=200)
    phone: str | None = Field(default=None, max_length=30, description="Celular")
    position: str | None = Field(default=None, max_length=100, description="Cargo en la empresa")
    # La persona en Identidad (sin FK). Vacío = todavía no invitada
    user_id: UUID | None = Field(default=None, index=True)
