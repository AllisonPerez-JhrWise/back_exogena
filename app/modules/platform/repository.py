"""Consultas a las tablas de la plataforma. Solo lectura.

Este servicio no crea tenants, personas ni membresías: eso es de la plataforma (p. ej.
POST /tenant/miembros para invitar personas). Los clientes no son tenants: son registros
dentro de la firma.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Role,
    RolePermission,
    SystemRole,
    User,
)


class PlatformRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def has_permission(self, user_id: UUID, tenant_id: UUID, code: str) -> bool:
        """True si la persona tiene una membresía activa en el tenant con ese permiso."""
        query = (
            select(Membership.id)
            .join(MembershipRole, MembershipRole.membership_id == Membership.id)
            .join(RolePermission, RolePermission.role_id == MembershipRole.role_id)
            .where(
                Membership.user_id == user_id,
                Membership.tenant_id == tenant_id,
                Membership.status == MembershipStatus.ACTIVE,
                RolePermission.permission_code == code,
            )
            .limit(1)
        )
        return (await self.session.execute(query)).first() is not None

    def _members_with_role(self, tenant_id: UUID, role: SystemRole):
        """Personas con membresía activa en el tenant y ese rol del sistema."""
        return (
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .join(MembershipRole, MembershipRole.membership_id == Membership.id)
            .join(Role, Role.id == MembershipRole.role_id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.status == MembershipStatus.ACTIVE,
                Role.code == role,
                Role.tenant_id.is_(None),
                User.is_active.is_(True),
            )
        )

    async def list_members_with_role(self, tenant_id: UUID, role: SystemRole) -> Sequence[User]:
        result = await self.session.execute(
            self._members_with_role(tenant_id, role).order_by(User.full_name)
        )
        return result.scalars().unique().all()

    async def names_of(self, user_ids: set[UUID]) -> dict[UUID, str]:
        """Nombre de cada persona visible con el contexto actual (seguridad por filas)."""
        if not user_ids:
            return {}
        result = await self.session.execute(
            select(User.id, User.full_name).where(User.id.in_(user_ids))
        )
        return {user_id: name or "" for user_id, name in result.tuples().all()}

    async def get_member_with_role(
        self, user_id: UUID, tenant_id: UUID, role: SystemRole
    ) -> User | None:
        result = await self.session.execute(
            self._members_with_role(tenant_id, role).where(User.id == user_id)
        )
        return result.scalars().first()
