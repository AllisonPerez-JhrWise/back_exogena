from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.accounts.models import User
from app.modules.accounts.repository import UserRepository
from app.modules.accounts.schemas import GoogleUser, RegisterRequest


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)

    async def register(self, data: RegisterRequest) -> User:
        email = data.email.lower()
        if await self.users.get_by_email(email):
            raise ConflictError("A user with this email already exists")

        user = await self.users.add(
            User(
                email=email,
                full_name=data.full_name,
                hashed_password=hash_password(data.password),
            )
        )
        await self.session.commit()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        # verify_password se ejecuta aunque no exista el usuario,
        # así el tiempo de respuesta no revela qué emails existen
        valid = verify_password(password, user.hashed_password if user else None)
        if not user or not valid or not user.is_active:
            raise UnauthorizedError("Invalid credentials")
        return user

    async def login_with_google(self, google_user: GoogleUser) -> User:
        user = await self.users.get_by_email(google_user.email)

        if user is None:
            user = await self.users.add(
                User(
                    email=google_user.email.lower(),
                    google_id=google_user.id,
                    full_name=google_user.name,
                    avatar_url=google_user.picture,
                )
            )
        else:
            if not user.is_active:
                raise UnauthorizedError("Invalid credentials")
            changes = {}
            if not user.google_id:
                changes["google_id"] = google_user.id
            if not user.avatar_url and google_user.picture:
                changes["avatar_url"] = google_user.picture
            if changes:
                user = await self.users.update(user, changes)

        await self.session.commit()
        return user

    @staticmethod
    def issue_token(user: User) -> str:
        return create_access_token(subject=user.id, claims={"email": user.email})


class UserService:
    def __init__(self, session: AsyncSession):
        self.users = UserRepository(session)

    async def get_active(self, user_id: UUID) -> User:
        user = await self.users.get(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError()
        return user
