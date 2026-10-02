from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from app.modules.engagements.models import EngagementServiceType, EngagementStatus


class EngagementIn(BaseModel):
    """Un compromiso (fila del paso 3 del formulario, o POST /companies/{id}/engagements).

    El tipo de servicio no se envía: hoy todos son de exógena. Si el front todavía manda
    service_id, se ignora."""

    fiscal_year: int = Field(ge=2000, le=2100, description="Año gravable")
    # Con zona horaria (p. ej. 2026-05-15T23:59:00-05:00): sin ella la hora sería ambigua
    start_date: AwareDatetime | None = Field(default=None, description="Fecha de inicio")
    due_date: AwareDatetime = Field(description="Fecha de vencimiento")
    partner_user_id: UUID = Field(description="Socio (GET /members?role=socio)")
    manager_user_id: UUID = Field(description="Gerente (GET /members?role=gerente)")


def check_no_repeated_engagements(items: list[EngagementIn]) -> None:
    """REGLA DE NEGOCIO: el mismo tipo de servicio no se repite para el mismo año gravable.
    Como hoy solo existe exógena, basta con que no se repita el año.
    Si cambia, quitar esta validación (ver también Engagement.__table_args__)."""
    years = [item.fiscal_year for item in items]
    if len(set(years)) != len(years):
        raise ValueError("engagements has the same fiscal year repeated")


class PersonRef(BaseModel):
    user_id: UUID
    full_name: str


class EngagementRead(BaseModel):
    id: UUID
    company_id: UUID
    service_type: EngagementServiceType
    fiscal_year: int
    start_date: datetime | None = None
    due_date: datetime | None = None
    status: EngagementStatus
    # Vacíos solo en compromisos sin equipo registrado aquí
    partner: PersonRef | None = Field(default=None, description="Socio")
    manager: PersonRef | None = Field(default=None, description="Gerente")
    created_at: datetime


class EngagementSummary(BaseModel):
    """GET /engagements/{id}: el compromiso con su tipo de servicio."""

    id: UUID
    company_id: UUID
    service_type: EngagementServiceType
    fiscal_year: int = Field(description="Año gravable")
    status: EngagementStatus
