from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.engagements.models import EngagementStatus


class EngagementIn(BaseModel):
    """Un compromiso (fila del paso 3 del formulario, o POST /companies/{id}/engagements)."""

    service_id: UUID = Field(
        description="El service_id de GET /obligations/{id}/service-types (obligación + tipo)"
    )
    fiscal_year: int = Field(ge=2000, le=2100, description="Año gravable")
    due_date: date | None = Field(
        default=None, description="Vencimiento. Obligatorio si la obligación es tributaria"
    )
    partner_user_id: UUID = Field(description="Socio (GET /members?role=socio)")
    manager_user_id: UUID = Field(description="Gerente (GET /members?role=gerente)")


def check_no_repeated_engagements(items: list[EngagementIn]) -> None:
    """REGLA DE NEGOCIO: el mismo servicio no se repite para el mismo año gravable.
    Si cambia, quitar esta validación (ver también Engagement.__table_args__)."""
    keys = [(item.service_id, item.fiscal_year) for item in items]
    if len(set(keys)) != len(keys):
        raise ValueError("engagements has the same service repeated for the same fiscal year")


class NamedRef(BaseModel):
    id: UUID
    name: str


class PersonRef(BaseModel):
    user_id: UUID
    full_name: str


class EngagementRead(BaseModel):
    id: UUID
    company_id: UUID
    service_id: UUID
    obligation: NamedRef
    service_type: NamedRef
    fiscal_year: int
    due_date: date | None = None
    status: EngagementStatus
    partner: PersonRef = Field(description="Socio")
    manager: PersonRef = Field(description="Gerente")
    created_at: datetime
