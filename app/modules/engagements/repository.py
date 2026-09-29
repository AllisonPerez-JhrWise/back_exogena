from uuid import UUID

from app.modules.engagements.models import Engagement
from app.shared.repository import BaseRepository


class EngagementRepository(BaseRepository[Engagement]):
    model = Engagement

    async def exists(self, company_id: UUID, service_id: UUID, fiscal_year: int) -> bool:
        result = await self.session.execute(
            self.base_query().where(
                Engagement.company_id == company_id,
                Engagement.service_id == service_id,
                Engagement.fiscal_year == fiscal_year,
            )
        )
        return result.first() is not None
