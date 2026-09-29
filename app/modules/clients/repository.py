from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from app.modules.clients.models import (
    Client,
    ClientMember,
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
)
from app.shared.repository import BaseRepository


class ClientRepository(BaseRepository[Client]):
    model = Client

    async def get_in_organization(self, client_id: UUID, organization_id: UUID) -> Client | None:
        return await self.get(client_id, Client.organization_id == organization_id)

    async def get_by_tenant(self, tenant_id: UUID) -> Client | None:
        """El cliente cuya cuenta en la plataforma es ese tenant."""
        result = await self.session.execute(self.base_query().where(Client.tenant_id == tenant_id))
        return result.scalars().first()

    async def search(
        self, organization_id: UUID, text: str | None, limit: int = 20
    ) -> Sequence[tuple[Client, int]]:
        """Clientes activos de la organización cuyo nombre, o el de una de sus empresas
        (razón social, nombre comercial o NIT), contiene el texto. Con su número de empresas."""
        companies = (
            select(func.count(Company.id))
            .where(Company.client_id == Client.id, Company.is_deleted.is_(False))
            .scalar_subquery()
        )
        query = select(Client, companies).where(
            Client.organization_id == organization_id,
            Client.is_active.is_(True),
            Client.is_deleted.is_(False),
        )
        if text:
            pattern = f"%{text.strip()}%"
            matches_company = (
                select(Company.id)
                .where(
                    Company.client_id == Client.id,
                    Company.is_deleted.is_(False),
                    Company.legal_name.ilike(pattern)
                    | Company.trade_name.ilike(pattern)
                    | Company.nit.ilike(pattern),
                )
                .exists()
            )
            query = query.where(Client.name.ilike(pattern) | matches_company)
        result = await self.session.execute(query.order_by(func.lower(Client.name)).limit(limit))
        return result.tuples().all()


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def get_by_nit(self, organization_id: UUID, nit: str) -> Company | None:
        result = await self.session.execute(
            self.base_query().where(Company.organization_id == organization_id, Company.nit == nit)
        )
        return result.scalars().first()


class CompanyTaxResponsibilityRepository(BaseRepository[CompanyTaxResponsibility]):
    model = CompanyTaxResponsibility


class CompanyRutVersionRepository(BaseRepository[CompanyRutVersion]):
    model = CompanyRutVersion


class ClientMemberRepository(BaseRepository[ClientMember]):
    model = ClientMember

    async def get_by_membership(self, membership_id: UUID) -> ClientMember | None:
        result = await self.session.execute(
            self.base_query().where(ClientMember.membership_id == membership_id)
        )
        return result.scalars().first()
