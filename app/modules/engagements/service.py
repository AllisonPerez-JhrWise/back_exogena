from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.database import set_db_context
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.modules.catalog.models import Obligation, Service, ServiceType
from app.modules.catalog.repository import ServiceRepository
from app.modules.clients.repository import CompanyRepository
from app.modules.engagements.models import Engagement
from app.modules.engagements.repository import EngagementRepository
from app.modules.engagements.schemas import (
    EngagementIn,
    EngagementRead,
    EngagementSummary,
    NamedRef,
    PersonRef,
)
from app.modules.platform.models import SystemRole, User
from app.modules.platform.repository import PlatformRepository


@dataclass
class PreparedEngagement:
    """Un compromiso ya validado, listo para guardarse."""

    item: EngagementIn
    service: Service
    obligation: Obligation
    service_type: ServiceType
    partner: User
    manager: User


class EngagementService:
    """Crea compromisos. Los métodos `prepare` y `add` NO hacen commit: los usa también
    la creación de clientes, dentro de su propia transacción."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.engagements = EngagementRepository(session)
        self.services = ServiceRepository(session)
        self.companies = CompanyRepository(session)
        self.platform = PlatformRepository(session)

    async def list_for_company(self, company_id: UUID) -> list[EngagementRead]:
        rows = await self.engagements.list_for_company(company_id)
        return [
            EngagementRead(
                id=e.id,
                company_id=e.company_id,
                service_id=e.service_id,
                obligation=NamedRef(id=e.obligation_id, name=obligation),
                service_type=NamedRef(id=e.service_type_id, name=service_type),
                fiscal_year=e.fiscal_year,
                due_date=e.due_date,
                status=e.status,
                partner=PersonRef(user_id=e.partner_user_id, full_name=partner or ""),
                manager=PersonRef(user_id=e.manager_user_id, full_name=manager or ""),
                created_at=e.created_at,
            )
            for e, obligation, service_type, partner, manager in rows
        ]

    async def get(self, engagement_id: UUID, tenant_id: UUID | None) -> EngagementSummary:
        """404 si no existe o es de otra organización. Si quien consulta puede ver su
        empresa lo revisa el router (ClientService.ensure_visible)."""
        row = await self.engagements.get_with_names(engagement_id)
        if row is None or (tenant_id and row[0].tenant_id != tenant_id):
            raise NotFoundError("Engagement not found")
        engagement, obligation, service_type = row
        return EngagementSummary(
            id=engagement.id,
            company_id=engagement.company_id,
            fiscal_year=engagement.fiscal_year,
            status=engagement.status,
            obligation=NamedRef(id=engagement.obligation_id, name=obligation),
            service_type=NamedRef(id=engagement.service_type_id, name=service_type),
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
        prepared = await self.prepare([item], tenant_id or company.organization_id, actor)
        [created] = await self.add(prepared, company_id, actor)
        await self.session.commit()
        return created

    async def prepare(
        self, items: list[EngagementIn], tenant_id: UUID | None, actor: Principal
    ) -> list[PreparedEngagement]:
        """Valida los compromisos antes de guardar nada.

        tenant_id es la organización en la que trabaja quien crea (la firma): el servicio
        debe ser suyo, y el socio y el gerente, personas de ella con ese rol. Sin tenant
        (solo AUTH_BYPASS en pruebas) se usa la organización del servicio.
        Los repetidos dentro de la misma petición los rechaza el esquema de entrada
        (check_no_repeated_engagements)."""
        prepared = []
        for index, item in enumerate(items):
            offered = await self.services.get_offered(item.service_id)
            if offered is None or (tenant_id and offered[0].tenant_id != tenant_id):
                raise BusinessRuleError(
                    "The service does not exist or is not available",
                    details={"engagement": index, "field": "service_id"},
                )
            service, obligation, service_type = offered
            if obligation.requires_due_date and item.due_date is None:
                raise BusinessRuleError(
                    f"due_date is required for '{obligation.name}' (tributaria)",
                    details={"engagement": index, "field": "due_date"},
                )

            # El equipo es de la firma: se consulta dentro de su organización (RLS)
            await set_db_context(self.session, user_id=actor.id, tenant_id=service.tenant_id)
            partner = await self._member(item.partner_user_id, service, SystemRole.SOCIO)
            manager = await self._member(item.manager_user_id, service, SystemRole.GERENTE)
            if partner is None or manager is None:
                field = "partner_user_id" if partner is None else "manager_user_id"
                role = SystemRole.SOCIO if partner is None else SystemRole.GERENTE
                raise BusinessRuleError(
                    f"The person is not an active {role} of the organization",
                    details={"engagement": index, "field": field},
                )
            prepared.append(
                PreparedEngagement(item, service, obligation, service_type, partner, manager)
            )
        return prepared

    async def add(
        self, prepared: list[PreparedEngagement], company_id: UUID, actor: Principal
    ) -> list[EngagementRead]:
        created = []
        for p in prepared:
            await self._check_not_duplicated(company_id, p.service.id, p.item.fiscal_year)
            engagement = await self.engagements.add(
                Engagement(
                    tenant_id=p.service.tenant_id,
                    company_id=company_id,
                    service_id=p.service.id,
                    obligation_id=p.obligation.id,
                    service_type_id=p.service_type.id,
                    fiscal_year=p.item.fiscal_year,
                    due_date=p.item.due_date,
                    partner_user_id=p.partner.id,
                    manager_user_id=p.manager.id,
                    created_by=actor.id,
                )
            )
            created.append(self._to_read(engagement, p))
        return created

    async def _check_not_duplicated(self, company_id: UUID, service_id: UUID, year: int) -> None:
        """REGLA DE NEGOCIO: una empresa no tiene dos compromisos del mismo servicio para el
        mismo año gravable. Si cambia, quitar esta validación, la de
        schemas.check_no_repeated_engagements y el índice de Engagement.__table_args__."""
        if await self.engagements.exists(company_id, service_id, year):
            raise ConflictError(
                "The company already has an engagement for this service and fiscal year"
            )

    async def _member(self, user_id: UUID, service: Service, role: SystemRole) -> User | None:
        return await self.platform.get_member_with_role(user_id, service.tenant_id, role)

    @staticmethod
    def _to_read(engagement: Engagement, p: PreparedEngagement) -> EngagementRead:
        return EngagementRead(
            id=engagement.id,
            company_id=engagement.company_id,
            service_id=engagement.service_id,
            obligation=NamedRef(id=p.obligation.id, name=p.obligation.name),
            service_type=NamedRef(id=p.service_type.id, name=p.service_type.name),
            fiscal_year=engagement.fiscal_year,
            due_date=engagement.due_date,
            status=engagement.status,
            partner=PersonRef(user_id=p.partner.id, full_name=p.partner.full_name or ""),
            manager=PersonRef(user_id=p.manager.id, full_name=p.manager.full_name or ""),
            created_at=engagement.created_at,
        )
