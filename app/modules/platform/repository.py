"""Acceso a las tablas de la plataforma. Nunca hace commit.

Crear tenants y usuarios pasa por las funciones app_* de la plataforma (SECURITY DEFINER):
la seguridad por filas no deja insertarlos directamente. Solo wiseerp_app puede usarlas.
"""

from uuid import UUID, uuid4

from sqlalchemy import insert, select, text
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

    async def find_user_by_email(self, email: str) -> User | None:
        """Solo encuentra usuarios visibles con el contexto actual (RLS)."""
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalars().first()

    async def create_user(self, email: str, full_name: str) -> UUID:
        """Crea el usuario sin cognito_sub: todavía no ha entrado con Cognito."""
        return await self.session.scalar(
            text("SELECT public.app_crear_usuario(:email, :full_name, NULL)"),
            {"email": email.lower(), "full_name": full_name},
        )

    async def create_organization(self, slug: str, name: str, admin_id: UUID) -> UUID:
        """Crea el tenant (kind=client) y deja a admin_id como administrador invitado."""
        return await self.session.scalar(
            text("SELECT public.app_crear_organizacion(:slug, :name, :admin_id)"),
            {"slug": slug, "name": name, "admin_id": admin_id},
        )

    async def get_system_role(self, code: SystemRole) -> Role:
        result = await self.session.execute(
            select(Role).where(Role.code == code, Role.tenant_id.is_(None))
        )
        role = result.scalars().first()
        if role is None:
            raise RuntimeError(f"System role '{code}' does not exist in public.roles")
        return role

    async def get_membership(self, user_id: UUID, tenant_id: UUID) -> Membership | None:
        result = await self.session.execute(
            select(Membership).where(
                Membership.user_id == user_id, Membership.tenant_id == tenant_id
            )
        )
        return result.scalars().first()

    async def add_membership(
        self, user_id: UUID, tenant_id: UUID, role_id: UUID, status: MembershipStatus
    ) -> UUID:
        membership_id = uuid4()
        # created_at y updated_at los pone la base de datos (DEFAULT now())
        await self.session.execute(
            insert(Membership).values(
                id=membership_id, user_id=user_id, tenant_id=tenant_id, status=status
            )
        )
        await self.session.execute(
            insert(MembershipRole).values(membership_id=membership_id, role_id=role_id)
        )
        return membership_id
