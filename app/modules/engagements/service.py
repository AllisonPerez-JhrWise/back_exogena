from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.database import set_db_context
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.modules.clients.repository import CompanyRepository
from app.modules.engagements.models import Engagement, EngagementServiceType
from app.modules.engagements.repository import EngagementRepository
from app.modules.engagements.schemas import (
    EngagementIn,
    EngagementRead,
    EngagementSummary,
    PersonRef,
)
from app.modules.platform.models import SystemRole, User
from app.modules.platform.repository import PlatformRepository


@dataclass
class PreparedEngagement:
    """Un compromiso ya validado, listo para guardarse."""

    item: EngagementIn
    organization_id: UUID
    partner: User
    manager: User


class EngagementService:
    """Crea compromisos. Los métodos `prepare` y `add` NO hacen commit: los usa también
    la creación de clientes, dentro de su propia transacción."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.engagements = EngagementRepository(session)
        self.companies = CompanyRepository(session)
        self.platform = PlatformRepository(session)

    async def list_for_company(self, company_id: UUID) -> list[EngagementRead]:
        rows = await self.engagements.list_for_company(company_id)
        return [
            EngagementRead(
                id=e.id,
                company_id=e.company_id,
                service_type=e.service_type,
                fiscal_year=e.fiscal_year,
                start_date=e.start_date,
                due_date=e.due_date,
                status=e.status,
                partner=_person(e.partner_user_id, partner),
                manager=_person(e.manager_user_id, manager),
                created_at=e.created_at,
            )
            for e, partner, manager in rows
        ]

    async def get(self, engagement_id: UUID, organization_id: UUID | None) -> EngagementSummary:
        """404 si no existe o es de otra organización. Si quien consulta puede ver su
        empresa lo revisa el router (ClientService.ensure_visible)."""
        engagement = await self.engagements.get(engagement_id)
        if engagement is None or (
            organization_id and engagement.organization_id != organization_id
        ):
            raise NotFoundError("Engagement not found")
        return EngagementSummary(
            id=engagement.id,
            company_id=engagement.company_id,
            service_type=engagement.service_type,
            fiscal_year=engagement.fiscal_year,
            status=engagement.status,
        )

    async def create_for_company(
        self, company_id: UUID, item: EngagementIn, tenant_id: UUID | None, actor: Principal
    ) -> EngagementRead:
        """POST /companies/{company_id}/engagements. La empresa debe ser de la
        organización de quien crea y estar activa (un cliente inactivo no recibe
        compromisos nuevos)."""
        company = await self.companies.get(company_id)
        if company is None or (tenant_id and company.organization_id != tenant_id):
            raise NotFoundError("Company not found")
        if not company.is_active:
            raise BusinessRuleError("The company is inactive", details={"cause": "inactive"})
        prepared = await self.prepare([item], company.organization_id, actor)
        [created] = await self.add(prepared, company_id, actor)
        await self.session.commit()
        return created

    async def prepare(
        self, items: list[EngagementIn], organization_id: UUID, actor: Principal
    ) -> list[PreparedEngagement]:
        """Valida los compromisos antes de guardar nada.

        organization_id es la firma dueña de la empresa: el socio y el gerente deben ser
        personas de ella con ese rol. Los repetidos dentro de la misma petición los rechaza
        el esquema de entrada (check_no_repeated_engagements)."""
        # El equipo es de la firma: se consulta dentro de su organización (RLS)
        await set_db_context(self.session, user_id=actor.id, tenant_id=organization_id)
        prepared = []
        for index, item in enumerate(items):
            partner = await self.platform.get_member_with_role(
                item.partner_user_id, organization_id, SystemRole.SOCIO
            )
            manager = await self.platform.get_member_with_role(
                item.manager_user_id, organization_id, SystemRole.GERENTE
            )
            if partner is None or manager is None:
                field = "partner_user_id" if partner is None else "manager_user_id"
                role = SystemRole.SOCIO if partner is None else SystemRole.GERENTE
                raise BusinessRuleError(
                    f"The person is not an active {role} of the organization",
                    details={"engagement": index, "field": field},
                )
            prepared.append(PreparedEngagement(item, organization_id, partner, manager))
        return prepared

    async def add(
        self, prepared: list[PreparedEngagement], company_id: UUID, actor: Principal
    ) -> list[EngagementRead]:
        created = []
        for p in prepared:
            # Hoy el único tipo de servicio es exógena
            service_type = EngagementServiceType.EXOGENA
            await self._check_not_duplicated(company_id, service_type, p.item.fiscal_year)
            engagement = await self.engagements.add(
                Engagement(
                    organization_id=p.organization_id,
                    company_id=company_id,
                    service_type=service_type,
                    fiscal_year=p.item.fiscal_year,
                    start_date=p.item.start_date,
                    due_date=p.item.due_date,
                    partner_user_id=p.partner.id,
                    manager_user_id=p.manager.id,
                    created_by=actor.id,
                )
            )
            created.append(self._to_read(engagement, p))
        return created

    async def _check_not_duplicated(
        self, company_id: UUID, service_type: EngagementServiceType, year: int
    ) -> None:
        """REGLA DE NEGOCIO: una empresa no tiene dos compromisos del mismo tipo de servicio
        para el mismo año gravable. Si cambia, quitar esta validación, la de
        schemas.check_no_repeated_engagements y el índice de Engagement.__table_args__."""
        if await self.engagements.exists(company_id, service_type, year):
            raise ConflictError(
                "The company already has an engagement of this service type for this fiscal year"
            )

    @staticmethod
    def _to_read(engagement: Engagement, p: PreparedEngagement) -> EngagementRead:
        return EngagementRead(
            id=engagement.id,
            company_id=engagement.company_id,
            service_type=engagement.service_type,
            fiscal_year=engagement.fiscal_year,
            start_date=engagement.start_date,
            due_date=engagement.due_date,
            status=engagement.status,
            partner=PersonRef(user_id=p.partner.id, full_name=p.partner.full_name or ""),
            manager=PersonRef(user_id=p.manager.id, full_name=p.manager.full_name or ""),
            created_at=engagement.created_at,
        )


def _person(user_id: UUID | None, full_name: str | None) -> PersonRef | None:
    """Socio o gerente para mostrar; vacío si el compromiso no lo tiene."""
    return PersonRef(user_id=user_id, full_name=full_name or "") if user_id else None
