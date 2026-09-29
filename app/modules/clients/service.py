from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.config import settings
from app.core.database import set_db_context
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.modules.clients.listing import CompanyFilters, CompanyScope, list_companies
from app.modules.clients.models import (
    Client,
    ClientMember,
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
    RutStatus,
    first_covered_tax_year,
)
from app.modules.clients.repository import (
    ClientMemberRepository,
    ClientRepository,
    CompanyRepository,
    CompanyRutVersionRepository,
    CompanyTaxResponsibilityRepository,
)
from app.modules.clients.schemas import (
    ClientCreate,
    ClientCreated,
    ClientRead,
    ClientSearchItem,
    ClientUserIn,
    ClientUserRead,
    CompanyListItem,
    CompanyRead,
    NitCheck,
    RutIn,
)
from app.modules.engagements.service import EngagementService
from app.modules.platform.models import MembershipStatus, Permission, SystemRole
from app.modules.platform.repository import PlatformRepository
from app.shared.pagination import Page, PageParams


class PlatformUser(BaseModel):
    id: UUID
    email: str
    full_name: str


class ClientService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.clients = ClientRepository(session)
        self.companies = CompanyRepository(session)
        self.responsibilities = CompanyTaxResponsibilityRepository(session)
        self.rut_versions = CompanyRutVersionRepository(session)
        self.members = ClientMemberRepository(session)
        self.platform = PlatformRepository(session)
        # Comparte la sesión: los compromisos quedan en esta misma transacción
        self.engagements = EngagementService(session)

    # ── Asistente "Nuevo cliente" ─────────────────────────────────────────

    async def create(
        self, data: ClientCreate, actor: Principal, organization_id: UUID
    ) -> ClientCreated:
        """Crea en UNA operación (si algo falla, no queda nada a medias):
        1. El cliente (su cuenta en la plataforma), o usa el existente si llega client_id.
        2. La empresa con los datos del RUT, sus responsabilidades y la primera versión
           del RUT con sus dos fechas.
        3. Los compromisos del paso 3 (opcional), en estado por_iniciar.
        4. Los usuarios del paso 4 (opcional): invitados con el rol `cliente`.

        organization_id es la firma de quien crea (X-Tenant-Id)."""
        self._check_rut(data.rut)
        existing = await self.companies.get_by_nit(organization_id, data.rut.nit)
        if existing:
            raise ConflictError(
                "A company with this NIT already exists in the organization",
                details={"cause": "nit_exists", "company_id": str(existing.id)},
            )
        # Se validan antes de crear nada, dentro de la firma (socio y gerente son de ella)
        await set_db_context(self.session, user_id=actor.id, tenant_id=organization_id)
        engagements = await self.engagements.prepare(data.engagements, organization_id, actor)

        company = Company(
            organization_id=organization_id,
            **data.rut.model_dump(
                exclude={"tax_responsibilities", "generated_at", "rut_updated_at"}
            ),
            rut_generated_at=data.rut.generated_at,
            rut_updated_at=data.rut.rut_updated_at,
            **data.organization.model_dump(mode="json"),
            created_by=actor.id,
        )
        client = await self._get_or_create_client(data, company, organization_id, actor)
        # De aquí en adelante se trabaja dentro de la cuenta del cliente (seguridad por filas)
        await set_db_context(self.session, user_id=actor.id, tenant_id=client.tenant_id)

        company.client_id = client.id
        company = await self.companies.add(company)
        for code in data.rut.tax_responsibilities:
            await self.responsibilities.add(
                CompanyTaxResponsibility(company_id=company.id, code=code, created_by=actor.id)
            )
        await self.rut_versions.add(
            CompanyRutVersion(
                company_id=company.id,
                generated_at=data.rut.generated_at,
                rut_updated_at=data.rut.rut_updated_at,
                covers_tax_year=(
                    first_covered_tax_year(data.rut.rut_updated_at)
                    if data.rut.rut_updated_at
                    else None
                ),
                created_by=actor.id,
            )
        )

        users = [await self._add_user(client, item, actor) for item in data.users]
        created_engagements = await self.engagements.add(engagements, company.id, actor)

        await self.session.commit()
        return ClientCreated(
            client=ClientRead.model_validate(client),
            company=self._company_read(company, data.rut.tax_responsibilities),
            engagements=created_engagements,
            users=users,
        )

    @staticmethod
    def _check_rut(rut: RutIn) -> None:
        """Validaciones bloqueantes del RUT actual que se pueden verificar aquí.
        `cause` le dice al front qué mensaje mostrar (ver la tarea)."""
        if rut.rut_status != RutStatus.ACTIVO:
            raise BusinessRuleError(
                "The RUT is not active",
                details={"cause": "rut_not_active", "status": rut.rut_status},
            )
        days = (date.today() - rut.generated_at).days
        if days < 0:
            raise BusinessRuleError(
                "The RUT generation date is in the future",
                details={"cause": "rut_generated_in_future"},
            )
        if days > settings.rut_max_generation_days:
            raise BusinessRuleError(
                f"The RUT was generated {days} days ago",
                details={
                    "cause": "rut_too_old",
                    "days": days,
                    "max_days": settings.rut_max_generation_days,
                },
            )

    async def _get_or_create_client(
        self, data: ClientCreate, company: Company, organization_id: UUID, actor: Principal
    ) -> Client:
        if data.client_id:
            client = await self.clients.get_in_organization(data.client_id, organization_id)
            if client is None or not client.is_active:
                raise NotFoundError("Client not found")
            return client

        # Cliente nuevo: su cuenta en la plataforma y sus datos (los de la primera empresa)
        tenant_id = uuid4()
        await set_db_context(self.session, user_id=actor.id, tenant_id=tenant_id)
        await self.platform.insert_client_tenant(
            tenant_id, slug=f"cliente-{tenant_id.hex}", name=company.display_name
        )
        return await self.clients.add(
            Client(
                organization_id=organization_id,
                tenant_id=tenant_id,
                name=company.display_name,
                contact_name=company.contact_name,
                contact_email=company.contact_email,
                contact_phone=company.contact_phone,
                notes=company.notes,
                created_by=actor.id,
            )
        )

    async def _add_user(
        self, client: Client, item: ClientUserIn, actor: Principal
    ) -> ClientUserRead:
        """Da acceso a la persona a la cuenta del cliente (invitada, rol `cliente`).
        Si ya tenía acceso, no se duplica; su cargo y celular se actualizan."""
        user = await self._get_or_create_user(item)
        membership = await self.platform.get_membership(user.id, client.tenant_id)
        if membership:
            membership_id = membership.id
        else:
            role = await self.platform.get_system_role(SystemRole.CLIENTE)
            membership_id = await self.platform.add_membership(
                user.id, client.tenant_id, role.id, MembershipStatus.INVITED
            )
        member = await self.members.get_by_membership(membership_id)
        if member:
            member = await self.members.update(
                member, {"position": item.position, "phone": item.phone, "updated_by": actor.id}
            )
        else:
            member = await self.members.add(
                ClientMember(
                    client_id=client.id,
                    membership_id=membership_id,
                    position=item.position,
                    phone=item.phone,
                    created_by=actor.id,
                )
            )
        return ClientUserRead(
            user_id=user.id,
            membership_id=membership_id,
            email=user.email,
            full_name=user.full_name,
            role=SystemRole.CLIENTE,
            phone=member.phone,
            position=member.position,
        )

    async def _get_or_create_user(self, item: ClientUserIn) -> PlatformUser:
        """Usa la persona si ya existe (sin cambiar sus datos); si no, la crea sin acceso.

        Limitación: la seguridad por filas no deja ver a una persona que ya está en otro
        tenant (p. ej. un revisor fiscal de otro cliente). Falta que la plataforma exponga
        una función para buscar por email (tipo app_usuario_por_email)."""
        existing = await self.platform.find_user_by_email(item.email)
        if existing:
            return PlatformUser(
                id=existing.id, email=existing.email, full_name=existing.full_name or ""
            )
        try:
            async with self.session.begin_nested():
                user_id = await self.platform.create_user(item.email, item.full_name)
        except IntegrityError:
            raise ConflictError(
                "This person already exists in another organization. Linking existing "
                "people is not available yet.",
                details={"email": item.email.lower()},
            ) from None
        return PlatformUser(id=user_id, email=item.email.lower(), full_name=item.full_name)

    @staticmethod
    def _company_read(company: Company, responsibilities: list[str]) -> CompanyRead:
        return CompanyRead(
            **company.model_dump(),
            display_name=company.display_name,
            tax_responsibilities=responsibilities,
        )

    # ── Pantalla de clientes ──────────────────────────────────────────────

    async def list_companies(
        self,
        actor: Principal,
        tenant_id: UUID | None,
        filters: CompanyFilters,
        params: PageParams,
    ) -> Page[CompanyListItem]:
        scope = await self._scope(actor, tenant_id)
        rows, total = await list_companies(self.session, scope, filters, params)
        items = [
            CompanyListItem(
                id=row.company.id,
                client_id=row.company.client_id,
                display_name=row.company.display_name,
                trade_name=row.company.trade_name,
                nit=row.company.nit,
                dv=row.company.dv,
                group=row.group,
                active_engagements=row.active_engagements,
                rut_generated_at=row.company.rut_generated_at,
                rut_updated_at=row.company.rut_updated_at,
                rut_date_unknown=row.company.rut_generated_at is None,
                status=row.status,
            )
            for row in rows
        ]
        return Page.create(items, total, params)

    async def _scope(self, actor: Principal, tenant_id: UUID | None) -> CompanyScope:
        """Alcance de la tarea (F0-02):
        - El Cliente (trabaja en la cuenta de su cliente): solo sus empresas.
        - El Administrador (clientes.crear en la firma): todas las de la organización.
        - Socio y Gerente: las empresas de sus compromisos. (Senior y Asociado, las de
          los compromisos donde están asignados, cuando exista el equipo del compromiso.)"""
        if tenant_id is None:  # solo AUTH_BYPASS sin DEV_TENANT_ID (pruebas locales)
            return CompanyScope()
        client = await self.clients.get_by_tenant(tenant_id)
        if client:
            return CompanyScope(client_id=client.id)
        if settings.auth_bypass and actor.id == settings.dev_user_id:
            return CompanyScope(organization_id=tenant_id)
        if await self.platform.has_permission(actor.id, tenant_id, Permission.CLIENTES_CREAR):
            return CompanyScope(organization_id=tenant_id)
        return CompanyScope(organization_id=tenant_id, engaged_user_id=actor.id)

    # ── Paso 1: buscador de clientes y NIT existente ──────────────────────

    async def search(self, organization_id: UUID, text: str | None) -> list[ClientSearchItem]:
        rows = await self.clients.search(organization_id, text)
        return [
            ClientSearchItem(
                id=client.id,
                name=client.name,
                companies=companies,
                contact_name=client.contact_name,
                contact_email=client.contact_email,
                contact_phone=client.contact_phone,
            )
            for client, companies in rows
        ]

    async def check_nit(self, organization_id: UUID, nit: str) -> NitCheck:
        company = await self.companies.get_by_nit(organization_id, nit)
        if company is None:
            return NitCheck(exists=False)
        return NitCheck(
            exists=True,
            company_id=company.id,
            client_id=company.client_id,
            display_name=company.display_name,
        )
