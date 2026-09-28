from uuid import UUID

from app.modules.accounts.models import AuthProvider, User, UserIdentity
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
