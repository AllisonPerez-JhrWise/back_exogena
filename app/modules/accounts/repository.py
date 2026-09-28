from app.modules.accounts.models import User
from app.shared.repository import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(self.base_query().where(User.email == email.lower()))
        return result.scalars().first()
