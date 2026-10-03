from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.modules.catalog.repository import ObligationRepository, ServiceTypeRepository
from app.modules.catalog.schemas import ObligationRead, OfferedServiceTypeRead, ServiceTypeRead


class CatalogService:
    """Lectura del catálogo de la organización: solo lo activo, que es lo que se ofrece
    al crear compromisos."""

    def __init__(self, session: Session):
        self.session = session
        self.obligations = ObligationRepository(session)
        self.service_types = ServiceTypeRepository(session)

    def list_obligations(self, tenant_id: UUID | None) -> list[ObligationRead]:
        items = self.obligations.list_active(tenant_id)
        return [ObligationRead.model_validate(item) for item in items]

    def list_service_types(self, tenant_id: UUID | None) -> list[ServiceTypeRead]:
        items = self.service_types.list_active(tenant_id)
        return [ServiceTypeRead.model_validate(item) for item in items]

    def list_service_types_for(
        self, tenant_id: UUID | None, obligation_id: UUID
    ) -> list[OfferedServiceTypeRead]:
        # Una obligación inactiva o de otra organización no existe para quien consulta
        if self.obligations.get_active(tenant_id, obligation_id) is None:
            raise NotFoundError("Obligation not found")
        rows = self.service_types.list_offered_for(tenant_id, obligation_id)
        return [
            OfferedServiceTypeRead(
                id=service_type.id,
                name=service_type.name,
                description=service_type.description,
                service_id=service.id,
            )
            for service, service_type in rows
        ]
