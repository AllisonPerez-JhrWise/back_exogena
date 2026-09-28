from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field

from app.shared.models import BaseTable, join_name_parts


class PersonType(StrEnum):
    """Tipo de persona según el RUT."""

    NATURAL = "natural"
    JURIDICA = "juridica"


class RutStatus(StrEnum):
    """Estado del RUT. Se confirma la lista completa cuando se implemente la validación del RUT."""

    ACTIVO = "activo"
    SUSPENDIDO = "suspendido"
    CANCELADO = "cancelado"


class Client(BaseTable):
    """El cliente: una persona jurídica (empresa) o natural. Los datos del RUT no son
    editables; `trade_name` sí."""

    __tablename__ = "clients"
    __table_args__ = (
        # NIT único solo entre clientes no borrados (borrado lógico)
        Index("ux_clients_nit", "nit", unique=True, postgresql_where=text("NOT is_deleted")),
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

    # ── Datos del RUT (no editables) ──
    nit: str = Field(max_length=15, description="NIT sin dígito de verificación")
    dv: str = Field(max_length=1, description="Dígito de verificación")
    person_type: str = Field(max_length=10)
    # Persona jurídica
    legal_name: str | None = Field(default=None, max_length=250, description="Razón social")
    # Persona natural: el nombre separado, como viene en el RUT
    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=250)
    # Códigos DANE: los formatos de exógena de la DIAN piden el código, no el nombre
    department_code: str | None = Field(default=None, max_length=2)
    city_code: str | None = Field(default=None, max_length=5)
    rut_email: str | None = Field(default=None, max_length=320)
    main_activity_code: str | None = Field(default=None, max_length=4, description="Código CIIU")
    rut_status: str | None = Field(default=None, max_length=20)
    rut_updated_at: date | None = None
    # Ubicación del PDF del RUT (se define cuando se implemente la validación del RUT)
    rut_file_key: str | None = Field(default=None, max_length=500)

    # ── Datos de la organización (editables) ──
    trade_name: str | None = Field(default=None, max_length=250, description="Nombre comercial")

    @property
    def display_name(self) -> str:
        """Razón social (jurídica) o nombre completo (natural), para mostrar."""
        if self.person_type == PersonType.JURIDICA:
            return self.legal_name or ""
        return join_name_parts(
            self.first_name, self.middle_name, self.last_name, self.second_last_name
        )


class ClientTaxResponsibility(BaseTable):
    """Responsabilidades tributarias del RUT (05 Renta, 48 IVA, 42 Contabilidad…)."""

    __tablename__ = "client_tax_responsibilities"
    __table_args__ = (
        Index(
            "ux_client_tax_responsibilities_client_code",
            "client_id",
            "code",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("code ~ '^[0-9]{1,2}$'", name="code_digits"),
    )

    client_id: UUID = Field(foreign_key="clients.clients.id", index=True)
    code: str = Field(max_length=2)


class ClientUser(BaseTable):
    """Une usuarios con clientes. El cargo va aquí porque una persona (p. ej. un revisor
    fiscal) puede estar en varios clientes con un cargo distinto en cada uno."""

    __tablename__ = "client_users"
    __table_args__ = (
        # Un usuario no se repite en el mismo cliente
        Index(
            "ux_client_users_client_user",
            "client_id",
            "user_id",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        # Cada cliente tiene un solo contacto principal
        Index(
            "ux_client_users_primary_contact",
            "client_id",
            unique=True,
            postgresql_where=text("is_primary_contact AND NOT is_deleted"),
        ),
    )

    client_id: UUID = Field(foreign_key="clients.clients.id", index=True)
    user_id: UUID = Field(foreign_key="accounts.users.id", index=True)
    position: str | None = Field(default=None, max_length=100, description="Cargo en la empresa")
    is_primary_contact: bool = Field(default=False)
