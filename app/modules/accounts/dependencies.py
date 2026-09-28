from typing import Annotated

from fastapi import Depends

from app.core.auth import PrincipalDep
from app.core.config import settings
from app.core.database import SessionDep
from app.core.exceptions import NotFoundError
from app.modules.accounts.google import GoogleOAuthClient
from app.modules.accounts.models import User
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


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
GoogleClientDep = Annotated[GoogleOAuthClient, Depends(get_google_client)]
ActiveUserDep = Annotated[User, Depends(get_active_user)]
