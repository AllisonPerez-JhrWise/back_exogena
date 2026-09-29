"""Acceso a las tablas de la plataforma. Nunca hace commit.

Crear tenants y usuarios pasa por las funciones app_* de la plataforma (SECURITY DEFINER):
la seguridad por filas no deja insertarlos directamente. Solo wiseerp_app puede usarlas.
"""

from collections.abc import Sequence
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
    Tenant,
    TenantKind,
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

    async def get_member_with_role(
        self, user_id: UUID, tenant_id: UUID, role: SystemRole
    ) -> User | None:
        result = await self.session.execute(
            self._members_with_role(tenant_id, role).where(User.id == user_id)
        )
        return result.scalars().first()

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

    async def insert_client_tenant(self, tenant_id: UUID, slug: str, name: str) -> None:
        """Crea la cuenta (tenant kind='client') de un cliente, sin administrador.

        La seguridad por filas solo deja insertar el tenant que se declara como contexto:
        antes de llamar esto, set_db_context(..., tenant_id=tenant_id).
        (app_crear_organizacion exige un administrador, y el paso de usuarios es opcional.)"""
        await self.session.execute(
            insert(Tenant).values(
                id=tenant_id, slug=slug, name=name, kind=TenantKind.CLIENT, status="active"
            )
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
