"""¿Quién está haciendo la petición?

Solo valida el token (Authorization: Bearer), no consulta la base de datos. El login no
es de este servicio: lo hace la plataforma con Cognito. Los permisos dentro de un tenant
se revisan en app.modules.platform.dependencies.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    # id de public.users. Con Cognito, el token trae el cognito_sub y se traduce con
    # la función app_usuario_por_sub de la plataforma.
    id: UUID
    email: str | None = None


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    if not credentials:
        if settings.auth_bypass:  # solo pruebas locales (ver Settings.auth_bypass)
            return Principal(id=settings.dev_user_id)
        raise UnauthorizedError()

    claims = decode_access_token(credentials.credentials)
    try:
        return Principal(id=claims["sub"], email=claims.get("email"))
    except ValidationError:
        raise UnauthorizedError("Invalid token") from None


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]
