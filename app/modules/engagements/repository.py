from collections.abc import Sequence
from uuid import UUID

from app.modules.engagements.models import Engagement
from app.shared.repository import BaseRepository


class EngagementRepository(BaseRepository[Engagement]):
    model = Engagement

    def list_for_company(self, company_id: UUID) -> Sequence[Engagement]:
        """Compromisos de la empresa, del año gravable más reciente al más antiguo."""
        result = self.session.execute(
            self.base_query()
            .where(Engagement.company_id == company_id)
            .order_by(Engagement.fiscal_year.desc(), Engagement.service_type)
        )
        return result.scalars().all()

    def exists(self, company_id: UUID, service_type: str, fiscal_year: int) -> bool:
        result = self.session.execute(
            self.base_query().where(
                Engagement.company_id == company_id,
                Engagement.service_type == service_type,
                Engagement.fiscal_year == fiscal_year,
            )
        )
        return result.first() is not None
