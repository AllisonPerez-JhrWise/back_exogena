from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.modules.catalog.models import Obligation, ServiceType
from app.modules.engagements.models import Engagement
from app.modules.platform.models import User
from app.shared.repository import BaseRepository


class EngagementRepository(BaseRepository[Engagement]):
    model = Engagement

    async def list_for_company(
        self, company_id: UUID
    ) -> Sequence[tuple[Engagement, str, str, str | None, str | None]]:
        """Compromisos de la empresa, del año gravable más reciente al más antiguo, con
        los nombres de la obligación, el tipo de servicio, el socio y el gerente."""
        partner, manager = aliased(User), aliased(User)
        result = await self.session.execute(
            select(
                Engagement, Obligation.name, ServiceType.name, partner.full_name, manager.full_name
            )
            .join(Obligation, Obligation.id == Engagement.obligation_id)
            .join(ServiceType, ServiceType.id == Engagement.service_type_id)
            .outerjoin(partner, partner.id == Engagement.partner_user_id)
            .outerjoin(manager, manager.id == Engagement.manager_user_id)
            .where(Engagement.company_id == company_id, Engagement.is_deleted.is_(False))
            .order_by(Engagement.fiscal_year.desc(), Obligation.name)
        )
        return result.tuples().all()

    async def exists(self, company_id: UUID, service_id: UUID, fiscal_year: int) -> bool:
        result = await self.session.execute(
            self.base_query().where(
                Engagement.company_id == company_id,
                Engagement.service_id == service_id,
                Engagement.fiscal_year == fiscal_year,
            )
        )
        return result.first() is not None
