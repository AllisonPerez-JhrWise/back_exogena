from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import ColumnElement, func, select

from app.modules.catalog.models import Obligation, Service, ServiceType
from app.shared.repository import BaseRepository


def _of_tenant(column, tenant_id: UUID | None) -> list[ColumnElement[bool]]:
    """Filtro por organización. Sin tenant (solo AUTH_BYPASS en pruebas) no se filtra."""
    return [column == tenant_id] if tenant_id else []


class ObligationRepository(BaseRepository[Obligation]):
    model = Obligation

    def list_active(self, tenant_id: UUID | None) -> Sequence[Obligation]:
        result = self.session.execute(
            self.base_query()
            .where(*_of_tenant(Obligation.tenant_id, tenant_id), Obligation.is_active.is_(True))
            .order_by(func.lower(Obligation.name))
        )
        return result.scalars().all()

    def get_active(self, tenant_id: UUID | None, obligation_id: UUID) -> Obligation | None:
        return self.get(
            obligation_id,
            *_of_tenant(Obligation.tenant_id, tenant_id),
            Obligation.is_active.is_(True),
        )


class ServiceRepository(BaseRepository[Service]):
    model = Service

    def get_offered(self, service_id: UUID) -> tuple[Service, Obligation, ServiceType] | None:
        """El servicio con su obligación y tipo, solo si los tres están activos: lo que se
        puede elegir al crear un compromiso."""
        result = self.session.execute(
            select(Service, Obligation, ServiceType)
            .join(Obligation, Obligation.id == Service.obligation_id)
            .join(ServiceType, ServiceType.id == Service.service_type_id)
            .where(
                Service.id == service_id,
                *(
                    condition
                    for model in (Service, Obligation, ServiceType)
                    for condition in (model.is_active.is_(True), model.is_deleted.is_(False))
                ),
            )
        )
        return result.tuples().first()


class ServiceTypeRepository(BaseRepository[ServiceType]):
    model = ServiceType

    def list_active(self, tenant_id: UUID | None) -> Sequence[ServiceType]:
        result = self.session.execute(
            self.base_query()
            .where(*_of_tenant(ServiceType.tenant_id, tenant_id), ServiceType.is_active.is_(True))
            .order_by(func.lower(ServiceType.name))
        )
        return result.scalars().all()

    def list_offered_for(
        self, tenant_id: UUID | None, obligation_id: UUID
    ) -> Sequence[tuple[Service, ServiceType]]:
        """Tipos de servicio con un servicio activo para la obligación (ambos activos)."""
        result = self.session.execute(
            select(Service, ServiceType)
            .join(ServiceType, ServiceType.id == Service.service_type_id)
            .where(
                *_of_tenant(Service.tenant_id, tenant_id),
                Service.obligation_id == obligation_id,
                Service.is_active.is_(True),
                Service.is_deleted.is_(False),
                ServiceType.is_active.is_(True),
                ServiceType.is_deleted.is_(False),
            )
            .order_by(func.lower(ServiceType.name))
        )
        return result.tuples().all()
