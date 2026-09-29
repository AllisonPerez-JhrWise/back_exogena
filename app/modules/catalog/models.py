"""Catálogo con el que se crean los compromisos: obligaciones, tipos de servicio y
servicios (cada combinación de obligación y tipo de servicio que la firma presta).

Es por organización (tenant_id). Nada se borra: se inactiva (is_active = false) con motivo.
Por ahora solo lo necesario para listar; fases, etapas, roles requeridos y módulo del
servicio se agregan con la creación de compromisos.
"""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field

from app.shared.models import DB_SCHEMA, BaseTable


class ObligationNature(StrEnum):
    # Se presenta ante una autoridad en una fecha de ley: el compromiso exige vencimiento
    TRIBUTARIA = "tributaria"
    # Trabajo sin una fecha de ley única (outsourcing, nómina): no exige vencimiento
    SERVICIO_RECURRENTE = "servicio_recurrente"


def _unique_name_per_tenant(table: str) -> Index:
    """El nombre no se repite en la organización (sin distinguir mayúsculas)."""
    return Index(
        f"ux_{table}_tenant_name",
        "tenant_id",
        text("lower(name)"),
        unique=True,
        postgresql_where=text("NOT is_deleted"),
    )


class Obligation(BaseTable):
    """Lo que la empresa debe cumplir o el servicio recurrente que la firma le presta."""

    __tablename__ = "obligations"
    __table_args__ = (
        _unique_name_per_tenant("obligations"),
        CheckConstraint("nature IN ('tributaria', 'servicio_recurrente')", name="nature_valid"),
    )

    # La organización (la firma). ID de Identidad, sin FK
    tenant_id: UUID = Field(index=True)
    name: str = Field(max_length=150)
    description: str | None = Field(default=None, max_length=500)
    nature: str = Field(max_length=20)
    inactivation_reason: str | None = Field(default=None, max_length=500)

    @property
    def requires_due_date(self) -> bool:
        return self.nature == ObligationNature.TRIBUTARIA


class ServiceType(BaseTable):
    """Lo que hace la firma sobre una obligación (Elaboración, Revisión…).
    Un mismo tipo de servicio sirve para varias obligaciones."""

    __tablename__ = "service_types"
    __table_args__ = (_unique_name_per_tenant("service_types"),)

    tenant_id: UUID = Field(index=True)
    name: str = Field(max_length=150)
    description: str | None = Field(default=None, max_length=500)
    inactivation_reason: str | None = Field(default=None, max_length=500)


class Service(BaseTable):
    """Combinación de obligación y tipo de servicio que la firma presta. Es lo que se
    elige al crear un compromiso."""

    __tablename__ = "services"
    __table_args__ = (
        # No puede existir dos veces el mismo servicio en la organización
        Index(
            "ux_services_tenant_obligation_type",
            "tenant_id",
            "obligation_id",
            "service_type_id",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
    )

    tenant_id: UUID = Field(index=True)
    obligation_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.obligations.id", index=True)
    service_type_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.service_types.id", index=True)
    inactivation_reason: str | None = Field(default=None, max_length=500)
