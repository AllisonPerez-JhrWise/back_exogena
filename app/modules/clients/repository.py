from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from app.modules.clients.models import (
    Company,
    CompanyRutVersion,
    CompanyTaxResponsibility,
    CompanyUser,
    Group,
    group_name_key,
)
from app.shared.repository import BaseRepository


class GroupRepository(BaseRepository[Group]):
    model = Group

    def get_in_organization(self, group_id: UUID, organization_id: UUID) -> Group | None:
        return self.get(group_id, Group.organization_id == organization_id)

    def get_by_name(self, organization_id: UUID, name: str) -> Group | None:
        """El grupo con ese nombre, escrito como sea (ver group_name_key)."""
        result = self.session.execute(
            self.base_query().where(
                Group.organization_id == organization_id,
                Group.name_key == group_name_key(name),
            )
        )
        return result.scalars().first()

    def search(
        self, organization_id: UUID, text: str | None, limit: int = 20
    ) -> Sequence[tuple[Group, int]]:
        """Grupos activos de la firma cuyo nombre contiene el texto, con su número de
        empresas. Sin texto, todos (el selector del paso 1)."""
        companies = (
            select(func.count(Company.id))
            .where(Company.group_id == Group.id, Company.is_deleted.is_(False))
            .scalar_subquery()
        )
        query = select(Group, companies).where(
            Group.organization_id == organization_id,
            Group.is_active.is_(True),
            Group.is_deleted.is_(False),
        )
        if text and text.strip():
            query = query.where(Group.name_key.contains(group_name_key(text)))
        result = self.session.execute(query.order_by(Group.name_key).limit(limit))
        return result.tuples().all()


class CompanyRepository(BaseRepository[Company]):
    model = Company

    def get_by_nit(self, organization_id: UUID, nit: str) -> Company | None:
        result = self.session.execute(
            self.base_query().where(Company.organization_id == organization_id, Company.nit == nit)
        )
        return result.scalars().first()


class CompanyTaxResponsibilityRepository(BaseRepository[CompanyTaxResponsibility]):
    model = CompanyTaxResponsibility

    def codes_for(self, company_id: UUID) -> list[str]:
        result = self.session.execute(
            select(CompanyTaxResponsibility.code)
            .where(
                CompanyTaxResponsibility.company_id == company_id,
                CompanyTaxResponsibility.is_deleted.is_(False),
            )
            .order_by(CompanyTaxResponsibility.created_at, CompanyTaxResponsibility.code)
        )
        return list(result.scalars().all())


class CompanyRutVersionRepository(BaseRepository[CompanyRutVersion]):
    model = CompanyRutVersion

    def list_for(self, company_id: UUID) -> Sequence[CompanyRutVersion]:
        """De la más reciente a la más antigua, por fecha de actualización."""
        result = self.session.execute(
            self.base_query()
            .where(CompanyRutVersion.company_id == company_id)
            .order_by(
                CompanyRutVersion.rut_updated_at.desc().nulls_last(),
                CompanyRutVersion.created_at.desc(),
            )
        )
        return result.scalars().all()


class CompanyUserRepository(BaseRepository[CompanyUser]):
    model = CompanyUser

    def list_for(self, company_id: UUID) -> Sequence[CompanyUser]:
        result = self.session.execute(
            self.base_query()
            .where(CompanyUser.company_id == company_id)
            .order_by(CompanyUser.created_at, CompanyUser.email)
        )
        return result.scalars().all()

    def get_by_email(self, company_id: UUID, email: str) -> CompanyUser | None:
        result = self.session.execute(
            self.base_query().where(
                CompanyUser.company_id == company_id, CompanyUser.email == email.lower()
            )
        )
        return result.scalars().first()
