"""Compromisos: un servicio (obligación + tipo de servicio) que la firma presta a una
empresa (un NIT) para un año gravable.

Por ahora solo lo necesario para crearlos desde el formulario "Nuevo cliente": fases,
etapas, documentos y el resto del equipo (senior, asociados) se agregan después.
"""

from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field

from app.shared.models import DB_SCHEMA, BaseTable


class EngagementStatus(StrEnum):
    POR_INICIAR = "por_iniciar"
    # Cuando se cumplen los documentos obligatorios (F1-02)
    EN_CURSO = "en_curso"
    CERRADO = "cerrado"


class Engagement(BaseTable):
    __tablename__ = "engagements"
    __table_args__ = (
        # ── REGLA DE NEGOCIO: una empresa no tiene dos compromisos del mismo servicio para
        # el mismo año gravable. Si en algún momento se permiten repetidos, quitar este
        # índice (y crear una migración que lo borre) y la validación
        # EngagementService._check_not_duplicated.
        Index(
            "ux_engagements_company_service_year",
            "company_id",
            "service_id",
            "fiscal_year",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("fiscal_year BETWEEN 2000 AND 2100", name="fiscal_year_range"),
        CheckConstraint("status IN ('por_iniciar', 'en_curso', 'cerrado')", name="status_valid"),
    )

    # La organización dueña del servicio (la firma). Los IDs de Identidad van sin FK
    tenant_id: UUID = Field(index=True)
    company_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.companies.id", index=True)
    service_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.services.id", index=True)
    # Se copian del servicio: el compromiso los conserva aunque el servicio cambie después
    obligation_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.obligations.id")
    service_type_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.service_types.id")
    fiscal_year: int = Field(description="Año gravable")
    # Obligatorio si la obligación es tributaria (lo valida el service)
    due_date: date | None = Field(default=None, description="Fecha de vencimiento")
    status: str = Field(default=EngagementStatus.POR_INICIAR, max_length=20)
    # Equipo mínimo: socio y gerente siempre son requeridos (F1-03). Personas de Identidad
    # (sin FK): que existan y tengan el rol lo valida el service al crear
    partner_user_id: UUID = Field(description="Socio")
    manager_user_id: UUID = Field(description="Gerente")
