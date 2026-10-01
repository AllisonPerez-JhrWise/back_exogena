from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.config import settings
from app.core.database import set_db_context
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.modules.clients.listing import (
    CompanyFilters,
    CompanyRow,
    CompanyScope,
    list_companies,
)
from app.modules.clients.models import (
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
    CompanyUser,
    Group,
    RutStatus,
    first_covered_tax_year,
    group_name_key,
)
from app.modules.clients.repository import (
    CompanyRepository,
    CompanyRutVersionRepository,
    CompanyTaxResponsibilityRepository,
    CompanyUserRepository,
    GroupRepository,
)
from app.modules.clients.schemas import (
    ClientCreate,
    ClientCreated,
    CompanyDetail,
    CompanyListItem,
    CompanyRead,
    CompanyUserIn,
    CompanyUserRead,
    GroupCompanyItem,
    GroupListItem,
    GroupRead,
    NitCheck,
    RutIn,
    RutVersionRead,
)
from app.modules.engagements.schemas import PersonRef
from app.modules.engagements.service import EngagementService
from app.modules.platform.models import Permission
from app.modules.platform.repository import PlatformRepository
from app.shared.pagination import Page, PageParams


class GroupService:
    """Catálogo de grupos de la firma: se elige uno o se agrega si no está."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.groups = GroupRepository(session)

    async def search(self, organization_id: UUID, text: str | None) -> list[GroupListItem]:
        rows = await self.groups.search(organization_id, text)
        return [
            GroupListItem(id=g.id, name=g.name, is_active=g.is_active, companies=n) for g, n in rows
        ]

    async def create(self, organization_id: UUID, name: str, actor: Principal) -> Group:
        """Agrega el grupo al catálogo. Si ya existe (escrito como sea), no se duplica:
        responde 409 con el grupo existente para que se elija ese. No hace commit."""
        await self._check_name_is_free(organization_id, name)
        return await self.groups.add(
            Group(
                organization_id=organization_id,
                name=name,
                name_key=group_name_key(name),
                created_by=actor.id,
            )
        )

    async def create_and_commit(self, organization_id: UUID, name: str, actor: Principal) -> Group:
        group = await self.create(organization_id, name, actor)
        await self.session.commit()
        return group

    async def rename(
        self, organization_id: UUID, group_id: UUID, name: str, actor: Principal
    ) -> Group:
        group = await self.get(organization_id, group_id)
        await self._check_name_is_free(organization_id, name, except_id=group.id)
        group = await self.groups.update(
            group, {"name": name, "name_key": group_name_key(name), "updated_by": actor.id}
        )
        await self.session.commit()
        return group

    async def get(self, organization_id: UUID, group_id: UUID) -> Group:
        group = await self.groups.get_in_organization(group_id, organization_id)
        if group is None:
            raise NotFoundError("Group not found")
        return group

    async def _check_name_is_free(
        self, organization_id: UUID, name: str, except_id: UUID | None = None
    ) -> None:
        existing = await self.groups.get_by_name(organization_id, name)
        if existing and existing.id != except_id:
            raise ConflictError(
                "A group with this name already exists",
                details={
                    "cause": "group_exists",
                    "group_id": str(existing.id),
                    "name": existing.name,
                },
            )


class ClientService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.companies = CompanyRepository(session)
        self.responsibilities = CompanyTaxResponsibilityRepository(session)
        self.rut_versions = CompanyRutVersionRepository(session)
        self.users = CompanyUserRepository(session)
        self.groups = GroupService(session)
        self.platform = PlatformRepository(session)
        # Comparte la sesión: los compromisos quedan en esta misma transacción
        self.engagements = EngagementService(session)

    # ── Asistente "Nuevo cliente" ─────────────────────────────────────────

    async def create(
        self, data: ClientCreate, actor: Principal, organization_id: UUID
    ) -> ClientCreated:
        """Crea en UNA operación (si algo falla, no queda nada a medias):
        1. El grupo, si llega group_name (o usa el existente de group_id). Es opcional.
        2. La empresa (el cliente) con los datos del RUT, sus responsabilidades y la
           primera versión del RUT con sus dos fechas.
        3. Los compromisos del paso 3 (opcional), en estado por_iniciar.
        4. Los usuarios del paso 4 (opcional): ven solo esta empresa, y quedan pendientes
           de invitar (invitarlos a la firma es de Identidad: POST /organizacion/miembros).

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
        group = await self._resolve_group(data, organization_id, actor)

        company = await self.companies.add(
            Company(
                organization_id=organization_id,
                group_id=group.id if group else None,
                **data.rut.model_dump(
                    exclude={"tax_responsibilities", "generated_at", "rut_updated_at"}
                ),
                rut_generated_at=data.rut.generated_at,
                rut_updated_at=data.rut.rut_updated_at,
                **data.organization.model_dump(mode="json"),
                created_by=actor.id,
            )
        )
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

        users = [await self._add_user(company, item, actor) for item in data.users]
        created_engagements = await self.engagements.add(engagements, company.id, actor)

        await self.session.commit()
        return ClientCreated(
            company=self._company_read(company, group, data.rut.tax_responsibilities),
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

    async def _resolve_group(
        self, data: ClientCreate, organization_id: UUID, actor: Principal
    ) -> Group | None:
        if data.group_id:
            group = await self.groups.get(organization_id, data.group_id)
            if not group.is_active:
                raise NotFoundError("Group not found")
            return group
        if data.group_name:
            return await self.groups.create(organization_id, data.group_name, actor)
        return None

    async def _add_user(
        self, company: Company, item: CompanyUserIn, actor: Principal
    ) -> CompanyUserRead:
        """Asigna la persona a la empresa con su cargo y celular.

        PENDIENTE: invitarla a la firma con Identidad (POST /organizacion/miembros con el
        rol `cliente`), darle la empresa (PUT /usuarios/{id}/empresas) y guardar su
        user_id. Mientras tanto queda pendiente de invitar."""
        user = await self.users.add(
            CompanyUser(
                company_id=company.id,
                email=item.email.lower(),
                full_name=item.full_name,
                phone=item.phone,
                position=item.position,
                created_by=actor.id,
            )
        )
        return CompanyUserRead.model_validate(user)

    @staticmethod
    def _company_read(
        company: Company, group: Group | None, responsibilities: list[str]
    ) -> CompanyRead:
        return CompanyRead(
            **company.model_dump(),
            group=GroupRead.model_validate(group) if group else None,
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
                display_name=row.company.display_name,
                trade_name=row.company.trade_name,
                nit=row.company.nit,
                check_digit=row.company.check_digit,
                group_id=row.company.group_id,
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

    # ── Ficha de la empresa ───────────────────────────────────────────────

    async def get_detail(
        self, actor: Principal, tenant_id: UUID | None, company_id: UUID
    ) -> CompanyDetail:
        """Con el mismo alcance que la pantalla: si quien consulta no puede ver la
        empresa, responde 404 (no 403, para no confirmar que existe)."""
        scope = await self._scope(actor, tenant_id)
        row = await self._visible_row(scope, company_id)
        company = row.company

        group = await self.groups.groups.get(company.group_id) if company.group_id else None
        group_companies: list[GroupCompanyItem] = []
        if group:
            siblings, _ = await list_companies(
                self.session,
                scope,
                CompanyFilters(group_id=group.id),
                PageParams(page=1, size=100),
            )
            group_companies = [
                GroupCompanyItem(
                    id=s.company.id,
                    display_name=s.company.display_name,
                    nit=s.company.nit,
                    check_digit=s.company.check_digit,
                    status=s.status,
                )
                for s in siblings
                if s.company.id != company.id
            ]

        versions = await self.rut_versions.list_for(company.id)
        names = await self.platform.names_of({v.created_by for v in versions if v.created_by})
        return CompanyDetail(
            company=self._company_read(
                company, group, await self.responsibilities.codes_for(company.id)
            ),
            status=row.status,
            rut_date_unknown=company.rut_generated_at is None,
            group_companies=group_companies,
            engagements=await self.engagements.list_for_company(company.id),
            rut_versions=self._versions_read(versions, names),
            users=[
                CompanyUserRead.model_validate(u) for u in await self.users.list_for(company.id)
            ],
        )

    async def ensure_visible(
        self, actor: Principal, tenant_id: UUID | None, company_id: UUID
    ) -> None:
        """404 si quien consulta no puede ver la empresa, con el alcance de la pantalla.
        Lo usa también lo que cuelga de la empresa (p. ej. GET /engagements/{id})."""
        await self._visible_row(await self._scope(actor, tenant_id), company_id)

    async def _visible_row(self, scope: CompanyScope, company_id: UUID) -> CompanyRow:
        one = PageParams(page=1, size=1)
        rows, _ = await list_companies(
            self.session, scope, CompanyFilters(company_id=company_id), one
        )
        if not rows:
            raise NotFoundError("Company not found")
        return rows[0]

    @staticmethod
    def _versions_read(
        versions: Sequence[CompanyRutVersion], names: dict[UUID, str]
    ) -> list[RutVersionRead]:
        """Una versión cubre el año gravable N si su fecha de actualización es anterior o
        igual al 31 de diciembre de N; entre varias, la más reciente. Así, cubre desde el
        año de su actualización hasta el año anterior al que empieza a cubrir la siguiente
        más reciente, y la más reciente, hasta hoy. Si una más reciente empieza el mismo
        año, esta ya no cubre ninguno: covers_to_year queda menor que covers_from_year."""
        result = []
        newer_from: int | None = None
        for version in versions:  # de la más reciente a la más antigua
            covers_to = None
            if version.covers_tax_year is not None and newer_from is not None:
                covers_to = newer_from - 1
            result.append(
                RutVersionRead(
                    id=version.id,
                    generated_at=version.generated_at,
                    rut_updated_at=version.rut_updated_at,
                    covers_from_year=version.covers_tax_year,
                    covers_to_year=covers_to,
                    is_historical=version.is_historical,
                    uploaded_by=(
                        PersonRef(
                            user_id=version.created_by, full_name=names.get(version.created_by, "")
                        )
                        if version.created_by
                        else None
                    ),
                    uploaded_at=version.created_at,
                )
            )
            if version.covers_tax_year is not None:
                newer_from = version.covers_tax_year
        return result

    async def _scope(self, actor: Principal, tenant_id: UUID | None) -> CompanyScope:
        """Alcance de la tarea (F0-02). Todos trabajan dentro de la firma (X-Tenant-Id):
        - El Administrador (clientes.crear): todas las empresas de la organización.
        - Los demás: las empresas de sus compromisos (Socio y Gerente) y las que tienen
          asignadas (el Cliente, por company_users).
          Senior y Asociado verán las de los compromisos donde estén asignados cuando
          exista el equipo del compromiso."""
        if tenant_id is None:  # solo AUTH_BYPASS sin DEV_TENANT_ID (pruebas locales)
            return CompanyScope()
        if settings.auth_bypass and actor.id == settings.dev_user_id:
            return CompanyScope(organization_id=tenant_id)
        if await self.platform.has_permission(actor.id, tenant_id, Permission.CLIENTES_CREAR):
            return CompanyScope(organization_id=tenant_id)
        return CompanyScope(organization_id=tenant_id, user_id=actor.id)

    # ── Paso 1: NIT existente ─────────────────────────────────────────────

    async def check_nit(self, organization_id: UUID, nit: str) -> NitCheck:
        company = await self.companies.get_by_nit(organization_id, nit)
        if company is None:
            return NitCheck(exists=False)
        return NitCheck(
            exists=True,
            company_id=company.id,
            group_id=company.group_id,
            display_name=company.display_name,
        )
