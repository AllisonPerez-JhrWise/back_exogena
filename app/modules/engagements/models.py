"""Compromisos: el trabajo de un año gravable sobre una empresa (un NIT), de un tipo de
servicio. En este MVP el único tipo de servicio es exógena (tarea A1, acuerdo de datos).

Por ahora solo lo necesario para crearlos desde el formulario "Nuevo cliente": fases,
etapas, documentos y el resto del equipo (senior, asociados) se agregan después.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, text
from sqlmodel import Field

from app.shared.models import DB_SCHEMA, BaseTable


class EngagementServiceType(StrEnum):
    """Tipo de servicio del compromiso. Lista fija: agregar uno es una migración que
    amplía el CHECK service_type_valid."""

    EXOGENA = "exogena"


class EngagementStatus(StrEnum):
    """Estados del compromiso. Se guarda el código; el front muestra la etiqueta."""

    CREATED = "created"  # Creado
    LOADING_DOCUMENTS = "loading_documents"  # En carga de documentos
    READY_TO_VALIDATE = "ready_to_validate"  # Listo para validar
    VALIDATING = "validating"  # En validación
    IN_REVIEW = "in_review"  # En revisión
    CLOSED = "closed"  # Cerrado


class Engagement(BaseTable):
    __tablename__ = "engagements"
    __table_args__ = (
        # ── REGLA DE NEGOCIO: una empresa no tiene dos compromisos del mismo tipo de
        # servicio para el mismo año gravable. Si en algún momento se permiten repetidos,
        # quitar este índice (y crear una migración que lo borre) y las validaciones
        # EngagementService._check_not_duplicated y schemas.check_no_repeated_engagements.
        Index(
            "ux_engagements_company_service_type_year",
            "company_id",
            "service_type",
            "fiscal_year",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint("fiscal_year BETWEEN 2000 AND 2100", name="fiscal_year_range"),
        CheckConstraint("service_type IN ('exogena')", name="service_type_valid"),
        CheckConstraint(
            "status IN ('created', 'loading_documents', 'ready_to_validate', 'validating',"
            " 'in_review', 'closed')",
            name="status_valid",
        ),
    )

    # La organización dueña del compromiso (la firma). Los IDs de Identidad van sin FK
    organization_id: UUID = Field(index=True)
    company_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.companies.id", index=True)
    service_type: str = Field(default=EngagementServiceType.EXOGENA, max_length=30)
    fiscal_year: int = Field(description="Año gravable")
    start_date: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True), description="Fecha de inicio"
    )
    # Obligatoria al crear (lo exige el esquema de entrada); vacía solo en filas viejas
    due_date: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True), description="Fecha de vencimiento"
    )
    status: str = Field(default=EngagementStatus.CREATED, max_length=20)
    # Equipo mínimo: socio y gerente. Personas de Identidad (sin FK). Hoy la creación los
    # pide y valida; quedarán sin usar cuando el equipo viva en identidad.compromiso_equipo
    partner_user_id: UUID | None = Field(default=None, description="Socio")
    manager_user_id: UUID | None = Field(default=None, description="Gerente")

    # ── Sin usar desde la tarea A1 (el compromiso ya no se crea con un servicio del
    # catálogo). Se conservan, opcionales, por si se vuelve a elegir un servicio ──
    service_id: UUID | None = Field(
        default=None, foreign_key=f"{DB_SCHEMA}.services.id", index=True
    )
    obligation_id: UUID | None = Field(default=None, foreign_key=f"{DB_SCHEMA}.obligations.id")
    service_type_id: UUID | None = Field(default=None, foreign_key=f"{DB_SCHEMA}.service_types.id")


class FigureConcept(StrEnum):
    """Conceptos de las cifras del compromiso. Se guarda el código; el front muestra la
    etiqueta."""

    GROSS_INCOME = "gross_income"  # Ingresos brutos
    GROSS_EQUITY = "gross_equity"  # Patrimonio bruto
    ANNUAL_VAT_INCOME = "annual_vat_income"  # Ingresos de IVA del año
    # Rentas de capital y no laborales
    CAPITAL_AND_NON_LABOR_INCOME = "capital_and_non_labor_income"


class EngagementFigure(BaseTable):
    """Las cifras que usan las reglas (p. ej. si los ingresos brutos superan el tope), ya
    calculadas. Su año puede no ser el del compromiso: para la exógena de 2025 se usan los
    ingresos de 2024, de la renta del año anterior."""

    __tablename__ = "engagement_figures"
    __table_args__ = (
        # Una sola cifra por concepto y año en el compromiso: si se recalcula, se reemplaza
        Index(
            "ux_engagement_figures_engagement_concept_year",
            "engagement_id",
            "concept",
            "tax_year",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
        ),
        CheckConstraint(
            "concept IN ('gross_income', 'gross_equity', 'annual_vat_income',"
            " 'capital_and_non_labor_income')",
            name="concept_valid",
        ),
        CheckConstraint("tax_year BETWEEN 2000 AND 2100", name="tax_year_range"),
    )

    # La firma. ID de Identidad, sin FK
    organization_id: UUID = Field(index=True)
    engagement_id: UUID = Field(foreign_key=f"{DB_SCHEMA}.engagements.id", index=True)
    concept: str = Field(max_length=40)
    tax_year: int = Field(description="Año gravable de la cifra")
    # Entero en pesos, sin decimales (regla del acuerdo)
    value: int = Field(sa_type=BigInteger, description="Valor en pesos")
    # De dónde salió. La tarea no define sus valores: texto libre por ahora
    source: str | None = Field(default=None, max_length=100, description="Origen")
    # El documento en extracción (otro servicio): sin FK
    document_id: UUID | None = None
