from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.accounts.models import AuthProvider, RoleCode, User, UserIdentity, UserRole
from app.modules.accounts.repository import (
    RoleRepository,
    UserIdentityRepository,
    UserRepository,
    UserRoleRepository,
)
from app.modules.accounts.schemas import GoogleUser, NewUserData, RegisterRequest
from app.shared.models import utc_now


class AuthService:
    """Login mínimo (contraseña y Google) sobre user_identities.
    La política de primer acceso (invitación o creación al entrar) está por definir."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.identities = UserIdentityRepository(session)

    async def register(self, data: RegisterRequest) -> User:
        email = data.email.lower()
        if await self.users.get_by_email(email):
            raise ConflictError("A user with this email already exists")

        user = await self.users.add(
            User(
                email=email,
                first_name=data.first_name,
                middle_name=data.middle_name,
                last_name=data.last_name,
                second_last_name=data.second_last_name,
                can_login=True,
            )
        )
        await self.identities.add(
            UserIdentity(
                user_id=user.id,
                provider=AuthProvider.PASSWORD,
                subject=email,
                password_hash=hash_password(data.password),
            )
        )
        await self.session.commit()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        identity = (
            await self.identities.get_for_user(user.id, AuthProvider.PASSWORD) if user else None
        )
        # verify_password se ejecuta aunque no exista el usuario,
        # así el tiempo de respuesta no revela qué emails existen
        valid = verify_password(password, identity.password_hash if identity else None)
        if not user or not valid or not self._can_enter(user):
            raise UnauthorizedError("Invalid credentials")

        await self._register_login(user)
        return user

    async def login_with_google(self, google_user: GoogleUser) -> User:
        identity = await self.identities.get_by_subject(AuthProvider.GOOGLE, google_user.id)

        if identity:
            user = await self.users.get(identity.user_id)
            if user is None:  # la cuenta de Google pertenece a un usuario borrado
                raise UnauthorizedError("Invalid credentials")
        else:
            user = await self.users.get_by_email(google_user.email)
            if user is None:
                # Comportamiento actual: se crea al entrar.
                # Cambiará según la política de primer acceso (por definir)
                user = await self.users.add(
                    User(
                        email=google_user.email.lower(),
                        first_name=google_user.given_name or google_user.email.split("@")[0],
                        last_name=google_user.family_name or "",
                        can_login=True,
                    )
                )
            await self.identities.add(
                UserIdentity(user_id=user.id, provider=AuthProvider.GOOGLE, subject=google_user.id)
            )

        if not self._can_enter(user):
            raise UnauthorizedError("Invalid credentials")

        await self._register_login(user)
        return user

    @staticmethod
    def issue_token(user: User) -> str:
        return create_access_token(subject=user.id, claims={"email": user.email})

    @staticmethod
    def _can_enter(user: User) -> bool:
        return user.is_active and user.can_login

    async def _register_login(self, user: User) -> None:
        await self.users.update(user, {"last_login_at": utc_now()})
        await self.session.commit()


class UserService:
    """Operaciones sobre usuarios. Los métodos que escriben NO hacen commit: se usan
    dentro de la transacción del service que los llama (p. ej. crear un cliente)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.user_roles = UserRoleRepository(session)

    async def get_active(self, user_id: UUID) -> User:
        user = await self.users.get(user_id)
        if user is None or not user.is_active or not user.can_login:
            raise UnauthorizedError()
        return user

    async def has_any_role(self, user_id: UUID, *codes: RoleCode) -> bool:
        return await self.user_roles.has_any_role(user_id, codes)

    async def get_or_create_client_user(self, data: NewUserData, actor: Principal) -> User:
        """Devuelve el usuario con ese email; si no existe lo crea sin acceso (can_login=False).
        Un usuario existente se reutiliza tal cual: sus datos no se sobrescriben."""
        user = await self.users.get_by_email(data.email)
        if user is None:
            values = data.model_dump()
            values["email"] = data.email.lower()
            user = await self.users.add(User(**values, created_by=actor.id))
        await self.assign_role(user, RoleCode.USUARIO_CLIENTE, actor)
        return user

    async def assign_role(self, user: User, code: RoleCode, actor: Principal) -> None:
        """Asigna el rol si el usuario aún no lo tiene."""
        role = await self.roles.get_by_code(code)
        if role is None:
            # Los roles se cargan con la migración: si falta, la base está mal configurada
            raise RuntimeError(f"Role '{code}' does not exist; run the migrations")
        if await self.user_roles.get_assignment(user.id, role.id) is None:
            await self.user_roles.add(
                UserRole(user_id=user.id, role_id=role.id, created_by=actor.id)
            )
