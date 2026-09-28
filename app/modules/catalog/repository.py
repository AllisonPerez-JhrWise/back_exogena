from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from app.modules.catalog.models import Obligation, Service, ServiceType
from app.shared.repository import BaseRepository


class ObligationRepository(BaseRepository[Obligation]):
    model = Obligation

    async def list_active(self, tenant_id: UUID) -> Sequence[Obligation]:
        result = await self.session.execute(
            self.base_query()
            .where(Obligation.tenant_id == tenant_id, Obligation.is_active.is_(True))
            .order_by(func.lower(Obligation.name))
        )
        return result.scalars().all()

    async def get_active(self, tenant_id: UUID, obligation_id: UUID) -> Obligation | None:
        return await self.get(
            obligation_id, Obligation.tenant_id == tenant_id, Obligation.is_active.is_(True)
        )


class ServiceTypeRepository(BaseRepository[ServiceType]):
    model = ServiceType

    async def list_active(self, tenant_id: UUID) -> Sequence[ServiceType]:
        result = await self.session.execute(
            self.base_query()
            .where(ServiceType.tenant_id == tenant_id, ServiceType.is_active.is_(True))
            .order_by(func.lower(ServiceType.name))
        )
        return result.scalars().all()

    async def list_offered_for(
        self, tenant_id: UUID, obligation_id: UUID
    ) -> Sequence[tuple[Service, ServiceType]]:
        """Tipos de servicio con un servicio activo para la obligación (ambos activos)."""
        result = await self.session.execute(
            select(Service, ServiceType)
            .join(ServiceType, ServiceType.id == Service.service_type_id)
            .where(
                Service.tenant_id == tenant_id,
                Service.obligation_id == obligation_id,
                Service.is_active.is_(True),
                Service.is_deleted.is_(False),
                ServiceType.is_active.is_(True),
                ServiceType.is_deleted.is_(False),
            )
            .order_by(func.lower(ServiceType.name))
        )
        return result.tuples().all()
