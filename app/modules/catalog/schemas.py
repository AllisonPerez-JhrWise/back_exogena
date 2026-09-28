from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalog.models import ObligationNature


class ObligationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    nature: ObligationNature
    requires_due_date: bool = Field(
        description="Los compromisos de obligaciones tributarias exigen fecha de vencimiento"
    )


class ServiceTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None


class OfferedServiceTypeRead(ServiceTypeRead):
    """Tipo de servicio que se ofrece para una obligación, con su servicio."""

    service_id: UUID = Field(description="El servicio que se elige al crear el compromiso")
