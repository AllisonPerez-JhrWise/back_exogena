from typing import Annotated

from fastapi import Depends

from app.core.auth import Principal, PrincipalDep
from app.core.config import settings
from app.core.database import SessionDep
from app.core.exceptions import ForbiddenError, NotFoundError
from app.modules.accounts.google import GoogleOAuthClient
from app.modules.accounts.models import RoleCode, User
from app.modules.accounts.service import AuthService, UserService


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(session)


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


def get_google_client() -> GoogleOAuthClient:
    if not settings.google_enabled:
        raise NotFoundError("Google login is not enabled")
    return GoogleOAuthClient(settings)


async def get_active_user(
    principal: PrincipalDep,
    service: Annotated[UserService, Depends(get_user_service)],
) -> User:
    """Registro completo del usuario, verificando que siga existiendo y activo (consulta la BD)."""
    return await service.get_active(principal.id)


def require_roles(*codes: RoleCode):
    """Dependencia que deja pasar solo a quien tenga alguno de esos roles (si no, 403)."""

    async def dependency(
        principal: PrincipalDep,
        service: Annotated[UserService, Depends(get_user_service)],
    ) -> Principal:
        if not await service.has_any_role(principal.id, *codes):
            raise ForbiddenError()
        return principal

    return dependency


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
# Quien hace la petición, garantizando que es administrador
AdminDep = Annotated[Principal, Depends(require_roles(RoleCode.ADMIN))]
GoogleClientDep = Annotated[GoogleOAuthClient, Depends(get_google_client)]
ActiveUserDep = Annotated[User, Depends(get_active_user)]
