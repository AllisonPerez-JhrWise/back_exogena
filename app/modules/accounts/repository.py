from collections.abc import Iterable
from uuid import UUID

from sqlmodel import select

from app.modules.accounts.models import AuthProvider, Role, User, UserIdentity, UserRole
from app.shared.repository import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(self.base_query().where(User.email == email.lower()))
        return result.scalars().first()


class UserIdentityRepository(BaseRepository[UserIdentity]):
    model = UserIdentity

    async def get_by_subject(self, provider: AuthProvider, subject: str) -> UserIdentity | None:
        result = await self.session.execute(
            self.base_query().where(
                UserIdentity.provider == provider, UserIdentity.subject == subject
            )
        )
        return result.scalars().first()

    async def get_for_user(self, user_id: UUID, provider: AuthProvider) -> UserIdentity | None:
        result = await self.session.execute(
            self.base_query().where(
                UserIdentity.user_id == user_id, UserIdentity.provider == provider
            )
        )
        return result.scalars().first()


class RoleRepository(BaseRepository[Role]):
    model = Role

    async def get_by_code(self, code: str) -> Role | None:
        result = await self.session.execute(self.base_query().where(Role.code == code))
        return result.scalars().first()


class UserRoleRepository(BaseRepository[UserRole]):
    model = UserRole

    async def has_any_role(self, user_id: UUID, codes: Iterable[str]) -> bool:
        """True si el usuario (activo y no borrado) tiene alguno de esos roles."""
        query = (
            select(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .join(User, User.id == UserRole.user_id)
            .where(
                UserRole.user_id == user_id,
                UserRole.is_deleted.is_(False),
                Role.is_deleted.is_(False),
                Role.code.in_(list(codes)),
                User.is_deleted.is_(False),
                User.is_active.is_(True),
            )
            .limit(1)
        )
        return (await self.session.execute(query)).first() is not None

    async def get_assignment(self, user_id: UUID, role_id: UUID) -> UserRole | None:
        result = await self.session.execute(
            self.base_query().where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        )
        return result.scalars().first()
