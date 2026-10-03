from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.identity import Identity, IdentityRejected, IdentityUnavailable
from app.modules.clients.repository import CompanyRepository
from app.modules.engagements.models import (
    TEAM_MANAGER_ROLE,
    TEAM_PARTNER_ROLE,
    Engagement,
    EngagementServiceType,
)
from app.modules.engagements.repository import EngagementRepository
from app.modules.engagements.schemas import (
    EngagementIn,
    EngagementRead,
    EngagementSummary,
    PersonRef,
)


@dataclass
class PreparedEngagement:
    """Un compromiso ya validado, listo para guardarse."""

    item: EngagementIn
    organization_id: UUID


class EngagementService:
    """Crea compromisos. Los métodos `prepare` y `add` NO hacen commit: los usa también
    la creación de clientes, dentro de su propia transacción.

    Al crear uno se registra su equipo (socio y gerente) en Identidad: es lo que decide
    quién lo ve. Si Identidad lo rechaza o no responde, no se guarda nada."""

    def __init__(self, session: Session):
        self.session = session
        self.engagements = EngagementRepository(session)
        self.companies = CompanyRepository(session)

    def list_for_company(self, company_id: UUID) -> list[EngagementRead]:
        rows = self.engagements.list_for_company(company_id)
        return [
            EngagementRead(
                id=e.id,
                company_id=e.company_id,
                service_type=e.service_type,
                fiscal_year=e.fiscal_year,
                start_date=e.start_date,
                due_date=e.due_date,
                status=e.status,
                partner=_person(e.partner_user_id),
                manager=_person(e.manager_user_id),
                created_at=e.created_at,
            )
            for e in rows
        ]

    def get(self, engagement_id: UUID, organization_id: UUID | None) -> EngagementSummary:
        """404 si no existe o es de otra organización. Si quien consulta puede ver su
        empresa lo revisa el router (ClientService.ensure_visible)."""
        engagement = self.engagements.get(engagement_id)
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

    def create_for_company(
        self,
        company_id: UUID,
        item: EngagementIn,
        organization_id: UUID,
        actor: Principal,
        identity: Identity,
    ) -> EngagementRead:
        """POST /companies/{company_id}/engagements. La empresa debe ser de la
        organización de quien crea y estar activa (un cliente inactivo no recibe
        compromisos nuevos)."""
        company = self.companies.get(company_id)
        if company is None or company.organization_id != organization_id:
            raise NotFoundError("Company not found")
        if not company.is_active:
            raise BusinessRuleError("The company is inactive", details={"cause": "inactive"})
        prepared = self.prepare([item], company.organization_id, actor)
        [created] = self.add(prepared, company_id, actor, identity)
        self.session.commit()
        return created

    def prepare(
        self, items: list[EngagementIn], organization_id: UUID, actor: Principal
    ) -> list[PreparedEngagement]:
        """Valida los compromisos antes de guardar nada. Los repetidos dentro de la misma
        petición los rechaza el esquema de entrada (check_no_repeated_engagements).

        Que socio y gerente sean personas de la firma lo valida Identidad al registrarlos
        en el equipo del compromiso (ver add), que es quien sabe quién pertenece a ella."""
        return [PreparedEngagement(item, organization_id) for item in items]

    def add(
        self,
        prepared: list[PreparedEngagement],
        company_id: UUID,
        actor: Principal,
        identity: Identity,
    ) -> list[EngagementRead]:
        created = []
        for index, p in enumerate(prepared):
            # Hoy el único tipo de servicio es exógena
            service_type = EngagementServiceType.EXOGENA
            self._check_not_duplicated(company_id, service_type, p.item.fiscal_year)
            engagement = self.engagements.add(
                Engagement(
                    organization_id=p.organization_id,
                    company_id=company_id,
                    service_type=service_type,
                    fiscal_year=p.item.fiscal_year,
                    start_date=p.item.start_date,
                    due_date=p.item.due_date,
                    partner_user_id=p.item.partner_user_id,
                    manager_user_id=p.item.manager_user_id,
                    created_by=actor.id,
                )
            )
            self._register_team(engagement, identity, index)
            created.append(self._to_read(engagement))
        return created

    @staticmethod
    def _register_team(engagement: Engagement, identity: Identity, index: int) -> None:
        """Informa a Identidad el socio y el gerente (PUT /compromisos/{id}/equipo/...).
        Si son la misma persona, va una sola vez con los dos roles. Identidad valida que
        sean personas de la firma y que quien crea tenga el permiso."""
        team: dict[UUID, list[str]] = {}
        for user_id, role in (
            (engagement.partner_user_id, TEAM_PARTNER_ROLE),
            (engagement.manager_user_id, TEAM_MANAGER_ROLE),
        ):
            if user_id:
                team.setdefault(user_id, []).append(role)
        for user_id, roles in team.items():
            field = "partner_user_id" if TEAM_PARTNER_ROLE in roles else "manager_user_id"
            try:
                identity.set_engagement_team(engagement.id, engagement.company_id, user_id, roles)
            except IdentityUnavailable:
                raise ServiceUnavailableError(
                    "Could not reach the identity service", details={"cause": "identity"}
                ) from None
            except IdentityRejected as exc:
                if exc.status == 403:
                    raise ForbiddenError() from None
                details = {"engagement": index, "field": field}
                if exc.status == 404:
                    raise BusinessRuleError(
                        "The person is not a member of the organization",
                        details={**details, "cause": "not_a_member"},
                    ) from None
                raise BusinessRuleError(
                    f"Identity rejected the team: {exc.detail}", details=details
                ) from None

    def _check_not_duplicated(
        self, company_id: UUID, service_type: EngagementServiceType, year: int
    ) -> None:
        """REGLA DE NEGOCIO: una empresa no tiene dos compromisos del mismo tipo de servicio
        para el mismo año gravable. Si cambia, quitar esta validación, la de
        schemas.check_no_repeated_engagements y el índice de Engagement.__table_args__."""
        if self.engagements.exists(company_id, service_type, year):
            raise ConflictError(
                "The company already has an engagement of this service type for this fiscal year"
            )

    @staticmethod
    def _to_read(engagement: Engagement) -> EngagementRead:
        return EngagementRead(
            id=engagement.id,
            company_id=engagement.company_id,
            service_type=engagement.service_type,
            fiscal_year=engagement.fiscal_year,
            start_date=engagement.start_date,
            due_date=engagement.due_date,
            status=engagement.status,
            partner=_person(engagement.partner_user_id),
            manager=_person(engagement.manager_user_id),
            created_at=engagement.created_at,
        )


def _person(user_id: UUID | None) -> PersonRef | None:
    """Socio o gerente; vacío si el compromiso no lo tiene. El nombre lo tiene Identidad:
    el front lo toma de los miembros de la organización."""
    return PersonRef(user_id=user_id) if user_id else None
